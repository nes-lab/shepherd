import os
import subprocess
import threading
from types import TracebackType

import h5py
import orjson
from shepherd_core.data_models.content.enum_datatypes import Compression

from .h5_monitor_abc import Monitor
from .logger import log


class PTPLogMonitor(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
        backlog: int = 60,
    ) -> None:
        super().__init__(target, compression, poll_interval=0.51)

        self.ds_message = self.data.create_dataset(
            name="message",
            shape=(self.ds_size,),
            dtype=h5py.special_dtype(vlen=str),
            maxshape=(None,),
            chunks=(self.chunk_size,),
        )
        self.ds_priority = self.data.create_dataset(
            name="priority",
            shape=(self.ds_size,),
            dtype="uint8",
            maxshape=(None,),
            chunks=(self.chunk_size,),
        )
        self.ds_priority.attrs["unit"] = "n"
        self.ds_priority.attrs["description"] = (
            "0=emerg, 1=alert, 2=crit, 3=err, 4=warning, 5=notice, 6=info, 7=debug"
        )
        self.report_errors = False
        # gets activated with .check_status()

        command = [
            "/usr/bin/sudo",  # sheep runs with sudo, but it can't hurt
            "/usr/bin/journalctl",
            "--unit=ptp4l@eth0",
            "--follow",
            f"--lines={backlog}",
            "--boot",  # filter for current boot
            "--output=short-iso-precise",
        ]  # for client
        # TODO: switch to json (see kernel-monitor) to receive priority & warnings
        self.process = subprocess.Popen(  # noqa: S603
            command,
            stdout=subprocess.PIPE,
            universal_newlines=True,
        )
        if (not hasattr(self.process, "stdout")) or (self.process.stdout is None):
            log.error("[%s] Setup failed -> prevents logging", type(self).__name__)
            return
        os.set_blocking(self.process.stdout.fileno(), False)

        self.thread = threading.Thread(
            target=self.thread_fn,
            daemon=True,
            name="Shp.H5Mon.PTP.Log",
        )
        self.thread.start()

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.shutdown_thread()
        self.process.terminate()
        self.ds_message.resize((self.position,))
        self.ds_priority.resize((self.position,))
        super().__exit__()

    def thread_fn(self) -> None:
        # example:
        # 2026-07-02T12:13:15.865238+0200 sheep10 ptp4l[408]:
        # [83308.751] main offset         62 s2 freq +129116 path delay      9749
        while not self.event.is_set():
            self.event.wait(self.rate_limit_interval)
            line = self.process.stdout.readline()
            if len(line) < 1:
                self.event.wait(self.poll_interval)  # rate limiter
                continue
            data = orjson.loads(line)
            prio = int(data.get("PRIORITY", 6))
            try:
                if self.position >= self.ds_size:
                    self.ds_size += self.increment_size
                    self.ds_time.resize((self.ds_size,))
                    self.ds_message.resize((self.ds_size,))
                    self.ds_priority.resize((self.ds_size,))
            except RuntimeError:
                log.error("[%s] HDF5-File unavailable - will stop", type(self).__name__)
                break
            try:
                self.ds_time[self.position] = int(data.get("__REALTIME_TIMESTAMP", 0)) * 1000
                self.ds_message[self.position] = data.get("MESSAGE", "")
                self.ds_priority[self.position] = prio
                self.position += 1
                # TODO: lots of potential here -> batch writes (collect for 1..10 s)
            except OSError:
                log.error(
                    "[%s] Caught a Write Error for Line: %s",
                    type(self).__name__,
                    data.get("MESSAGE", ""),
                )
            if prio < 4 and self.report_errors:
                log.error("[%s] received error: %s", type(self).__name__, data["MESSAGE"])
        log.debug("[%s] thread ended itself", type(self).__name__)

    def check_status(self) -> None:
        if self.position == 0:
            log.warning("[%s] Service not running? No data collected yet", type(self).__name__)
            return
        self.report_errors = True

    def preshape_by_runtime(self, value_s: float) -> None:
        """Reshape some datasets with predictable length."""
        runtime_addition = 30
        datarate_sps = 1
        self.ds_size = max(
            len(self.ds_time),
            self.increment_size,
            round(datarate_sps * (runtime_addition + value_s)),
        )
        self.ds_time.resize((self.ds_size,))
        self.ds_message.resize((self.ds_size,))
