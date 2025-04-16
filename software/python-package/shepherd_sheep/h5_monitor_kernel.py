import os
import subprocess
import threading
from datetime import datetime
from types import TracebackType

import h5py
from shepherd_core import Compression

from .h5_monitor_abc import Monitor
from .logger import log


class KernelMonitor(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
        backlog: int = 60,
    ) -> None:
        super().__init__(target, compression, poll_intervall=0.52)
        self.backlog = backlog

        self.data.create_dataset(
            name="message",
            shape=(self.increment,),
            dtype=h5py.special_dtype(vlen=str),
            maxshape=(None,),
            chunks=True,
            compression=compression,
        )

        command = [
            "sudo",
            "/usr/bin/journalctl",
            "--dmesg",
            "--follow",
            f"--lines={self.backlog}",
            "--output=short-iso-precise",
        ]
        self.process = subprocess.Popen(  # noqa: S603
            command,
            stdout=subprocess.PIPE,
            universal_newlines=True,
        )
        if (not hasattr(self.process, "stdout")) or (self.process.stdout is None):
            log.error("[%s] Setup failed -> prevents logging", type(self).__name__)
            return
        os.set_blocking(self.process.stdout.fileno(), False)

        self.thread = threading.Thread(target=self.thread_fn, daemon=True, name="Shp.H5Mon.KMod")
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
            self.thread.join(timeout=2 * self.poll_intervall)
            if self.thread.is_alive():
                log.error(
                    "[%s] thread failed to end itself - will delete that instance",
                    type(self).__name__,
                )
            self.thread = None
        self.process.terminate()
        self.data["message"].resize((self.position,))
        super().__exit__()

    def thread_fn(self) -> None:
        while not self.event.is_set():
            line = self.process.stdout.readline()
            if len(line) < 1:
                self.event.wait(self.poll_intervall)  # rate limiter
                continue
            first_space = line.find(" ")
            time_str = line[:first_space]
            time_ts = datetime.fromisoformat(time_str)
            time_ns = int(datetime.timestamp(time_ts) * 1e9)
            line = line[first_space:].strip()[:128]
            try:
                data_length = self.data["time"].shape[0]
                if self.position >= data_length:
                    data_length += self.increment
                    self.data["time"].resize((data_length,))
                    self.data["message"].resize((data_length,))
            except RuntimeError:
                log.error("[%s] HDF5-File unavailable - will stop", type(self).__name__)
                break
            try:
                self.data["time"][self.position] = time_ns
                self.data["message"][self.position] = line
                self.position += 1
            except OSError:
                log.error(
                    "[%s] Caught a Write Error for Line: [%s] %s",
                    type(self).__name__,
                    type(line),
                    line,
                )
        log.debug("[%s] thread ended itself", type(self).__name__)
