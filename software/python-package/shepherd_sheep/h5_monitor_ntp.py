import os
import subprocess
import threading
from datetime import datetime
from types import TracebackType

import h5py
from shepherd_core.data_models.content.enum_datatypes import Compression

from .h5_monitor_abc import Monitor
from .logger import log


class NTPMonitor(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
        backlog: int = 60,
    ) -> None:
        super().__init__(target, compression, poll_interval=0.99)
        self.ds_message = self.data.create_dataset(
            name="message",
            shape=(self.increment_size,),
            dtype=h5py.special_dtype(vlen=str),
            maxshape=(None,),
            chunks=(self.chunk_size,),
        )
        command = [
            "/usr/bin/sudo",  # sheep runs with sudo, but it can't hurt
            "/usr/bin/journalctl",
            "--unit=systemd-timesyncd.service",
            "--follow",
            f"--lines={backlog}",
            "--boot",  # filter for current boot
            "--output=short-iso-precise",
        ]  # for client
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
            name="Shp.H5Mon.NTP",
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
        super().__exit__()

    def thread_fn(self) -> None:
        # example:
        #
        while not self.event.is_set():
            self.event.wait(self.rate_limit_interval)
            line = self.process.stdout.readline()
            if len(line) < 1:
                self.event.wait(self.poll_interval)  # rate limiter
                continue
            first_space = line.find(" ")
            time_str = line[:first_space]
            time_str = time_str[:-2] + ":" + time_str[-2:]
            # TODO: workaround for py < 3.11, .fromisoformat() can handle
            #       YYYY-MM-DDTHH:MM:SS+HH:MM, BUT NOT
            #       YYYY-MM-DDTHH:MM:SS+HHMM (default from --output=short-iso-precise
            time_ts = datetime.fromisoformat(time_str)
            time_ns = int(datetime.timestamp(time_ts) * 1e9)

            msg_begin = line.find("]: ") + 3
            line = line[msg_begin:].strip()[:128]

            try:
                data_length = len(self.ds_time)  # a faster .shape[0]
                if self.position >= data_length:
                    data_length += self.increment_size
                    self.ds_time.resize((data_length,))
                    self.ds_message.resize((data_length,))
            except RuntimeError:
                log.error("[%s] HDF5-File unavailable - will stop", type(self).__name__)
                break
            try:
                self.ds_time[self.position] = time_ns
                self.ds_message[self.position] = line
                self.position += 1
            except (OSError, KeyError):
                log.error(
                    "[%s] Caught a Write Error for Line: [%s] %s",
                    type(self).__name__,
                    type(line),
                    line,
                )
        log.debug("[%s] thread ended itself", type(self).__name__)

    def check_status(self) -> None:
        return

    def preshape_by_runtime(self, value_s: float) -> None:
        """Reshape some datasets with predictable length."""
        runtime_addition = 30
        datarate_sps = 1
        data_length = max(
            len(self.ds_time),
            self.increment_size,
            round(datarate_sps * (runtime_addition + value_s)),
        )
        self.ds_time.resize((data_length,))
        self.ds_message.resize((data_length,))
