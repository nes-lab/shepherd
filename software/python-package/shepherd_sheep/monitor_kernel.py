import subprocess  # noqa: S404
import threading
import time
from typing import Optional

import h5py
from shepherd_core import Compression

from .logger import log
from .monitor_abc import Monitor


class KernelMonitor(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Optional[Compression] = Compression.default,
        backlog: int = 60,
    ):
        super().__init__(target, compression, poll_intervall=0.23)
        self.backlog = backlog

        self.data.create_dataset(
            "message",
            (self.increment,),
            dtype=h5py.special_dtype(vlen=str),
            maxshape=(None,),
            chunks=True,
        )

        self.thread = threading.Thread(target=self.thread_fn, daemon=True)
        self.thread.start()

    def __exit__(self, *exc):  # type: ignore
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=self.poll_intervall)
            self.thread = None
        self.data["message"].resize((self.position,))
        super().__exit__()

    def thread_fn(self) -> None:
        # var1: ['dmesg', '--follow'] -> not enough control
        cmd_dmesg = [
            "sudo",
            "journalctl",
            "--dmesg",
            "--follow",
            f"--lines={self.backlog}",
            "--output=short-precise",
        ]
        proc_dmesg = subprocess.Popen(  # noqa: S603
            cmd_dmesg,
            stdout=subprocess.PIPE,
            universal_newlines=True,
        )
        if (not hasattr(proc_dmesg, "stdout")) or (proc_dmesg.stdout is None):
            log.error("[%s] Setup failed -> prevents logging", type(self).__name__)
            return
        for line in iter(proc_dmesg.stdout.readline, ""):  # type: ignore
            if self.event.is_set():
                break
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
            self.event.wait(self.poll_intervall)  # rate limiter
        log.debug("[%s] thread ended itself", type(self).__name__)
