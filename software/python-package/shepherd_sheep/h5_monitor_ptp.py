import os
import subprocess
import threading
from datetime import datetime
from types import TracebackType

import h5py
from shepherd_core import Compression

from .h5_monitor_abc import Monitor
from .logger import log


class PTPMonitor(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
    ) -> None:
        super().__init__(target, compression, poll_interval=0.51)
        self.data.create_dataset(
            name="values",
            shape=(self.increment, 3),
            dtype="i8",
            maxshape=(None, 3),
            chunks=True,
        )
        self.data["values"].attrs["unit"] = "ns, Hz, ns"
        self.data["values"].attrs["description"] = "main offset [ns], s2 freq [Hz], path delay [ns]"

        command = [
            "sudo",
            "/usr/bin/journalctl",
            "--unit=ptp4l@eth0",
            "--follow",
            "--lines=60",  # backlog
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
            name="Shp.H5Mon.PTP",
        )
        self.thread.start()

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=2 * self.poll_interval)
            if self.thread.is_alive():
                log.error(
                    "[%s] thread failed to end itself - will delete that instance",
                    type(self).__name__,
                )
            self.thread = None
        self.process.terminate()
        self.data["values"].resize((self.position, 3))
        super().__exit__()

    def thread_fn(self) -> None:
        # example:
        # sheep1 ptp4l[378]: [821.629] main offset -4426 s2 freq +285889 path delay 12484
        while not self.event.is_set():
            line = self.process.stdout.readline()
            if len(line) < 1:
                self.event.wait(self.poll_interval)  # rate limiter
                continue
            try:
                words = str(line).split()
                i_start = words.index("offset")
                values = [
                    int(words[i_start + 1]),
                    int(words[i_start + 4]),
                    int(words[i_start + 7]),
                ]
                time_ts = datetime.fromisoformat(words[0])
                time_ns = int(datetime.timestamp(time_ts) * 1e9)
            except ValueError:
                continue
            try:
                data_length = self.data["time"].shape[0]
                if self.position >= data_length:
                    data_length += self.increment
                    self.data["time"].resize((data_length,))
                    self.data["values"].resize((data_length, 3))
            except RuntimeError:
                log.error("[%s] HDF5-File unavailable - will stop", type(self).__name__)
                break
            try:
                self.data["time"][self.position] = time_ns
                self.data["values"][self.position, :] = values[0:3]
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
        if self.position == 0:
            log.warning("[%s] Service not running? No data collected yet", type(self).__name__)
            return
        offset_ns, freq_Hz, _ = self.data["values"][self.position - 1, :]
        if abs(offset_ns) > 500_000:
            log.warning(
                "[%s] Sync-Offset is unexpected high (%d us)",
                type(self).__name__,
                offset_ns // 1000,
            )
        if abs(freq_Hz) > 50_000_000:
            log.warning(
                "[%s] Sync-Compensation is unexpected high (%.3f MHz)",
                type(self).__name__,
                freq_Hz * 1e-6,
            )
