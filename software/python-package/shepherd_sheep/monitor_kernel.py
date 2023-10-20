import os
import subprocess  # noqa: S404
import threading
import time
from types import TracebackType

import h5py
from shepherd_core import Compression

from .logger import log
from .monitor_abc import Monitor


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
            "message",
            (self.increment,),
            dtype=h5py.special_dtype(vlen=str),
            maxshape=(None,),
            chunks=True,
        )

        command = [
            "sudo",
            "/usr/bin/journalctl",
            "--dmesg",
            "--follow",
            f"--lines={self.backlog}",
            "--output=short-precise",
        ]
        self.process = subprocess.Popen(
            command,  # noqa: S603
            stdout=subprocess.PIPE,
            universal_newlines=True,
        )
        if (not hasattr(self.process, "stdout")) or (self.process.stdout is None):
            log.error("[%s] Setup failed -> prevents logging", type(self).__name__)
            return
        os.set_blocking(self.process.stdout.fileno(), False)

        self.thread = threading.Thread(target=self.thread_fn, daemon=True)
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
            self.thread.join(timeout=self.poll_intervall)
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
            line = str(line).strip()[:128]
            try:
                data_length = self.data["time"].shape[0]
                if self.position >= data_length:
                    data_length += self.increment
                    self.data["time"].resize((data_length,))
                    self.data["message"].resize((data_length,))
                self.data["time"][self.position] = int(time.time() * 1e9)
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
