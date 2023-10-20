import os
import subprocess  # noqa: S404
import threading
import time
from types import TracebackType

import h5py
from shepherd_core import Compression

from .logger import log
from .monitor_abc import Monitor


class PTPMonitor(Monitor):  # TODO: also add phc2sys
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
    ) -> None:
        super().__init__(target, compression, poll_intervall=0.51)
        self.data.create_dataset(
            "values",
            (self.increment, 3),
            dtype="i8",
            maxshape=(None, 3),
            chunks=True,
        )
        self.data["values"].attrs["unit"] = "ns, Hz, ns"
        self.data["values"].attrs[
            "description"
        ] = "main offset [ns], s2 freq [Hz], path delay [ns]"

        command = [
            "sudo",
            "journalctl",
            "--unit=ptp4l@eth0",
            "--follow",
            "--lines=60",
            "--output=short-precise",
        ]  # for client
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
        self.data["values"].resize((self.position, 3))
        super().__exit__()

    def thread_fn(self) -> None:
        # example:
        # sheep1 ptp4l[378]: [821.629] main offset -4426 s2 freq +285889 path delay 12484
        while not self.event.is_set():
            line = self.process.stdout.readline()
            if len(line) < 1:
                self.event.wait(self.poll_intervall)  # rate limiter
                continue
            try:
                words = str(line).split()
                i_start = words.index("offset")
                values = [
                    int(words[i_start + 1]),
                    int(words[i_start + 4]),
                    int(words[i_start + 7]),
                ]
            except ValueError:
                continue
            try:
                data_length = self.data["time"].shape[0]
                if self.position >= data_length:
                    data_length += self.increment
                    self.data["time"].resize((data_length,))
                    self.data["values"].resize((data_length, 3))
                self.data["time"][self.position] = int(time.time() * 1e9)
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
