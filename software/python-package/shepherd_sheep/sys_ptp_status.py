import os
import subprocess
import threading
from datetime import datetime
from datetime import timedelta
from types import TracebackType

from .logger import log


class PTPStatus:
    def __init__(
        self,
        sync_threshold_ns: int = 1000,
        timeout_s: float = 300,
    ) -> None:

        self.timeout_sync: timedelta = timedelta(seconds=timeout_s)
        self.timeout_output: timedelta = timedelta(seconds=min(timeout_s, 30))
        self.poll_interval: float = 0.51
        self.sync_threshold_ns: int = sync_threshold_ns
        command = [
            "/usr/bin/sudo",  # sheep runs with sudo, but it can't hurt
            "/usr/bin/journalctl",
            "--unit=ptp4l@eth0",
            "--follow",
            "--lines=1",
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

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.process.terminate()

    def wait_4_sync(self) -> bool:
        # example:
        # 2026-07-02T12:13:15.865238+0200 sheep10 ptp4l[408]:
        # [83308.751] main offset         62 s2 freq +129116 path delay      9749
        time_last = datetime.now()  # noqa: DTZ005
        time_stop = time_last + self.timeout_sync
        log.info(
            "[%s] sync-goal = %d ns, timeout = %.0f s",
            type(self).__name__,
            self.sync_threshold_ns,
            self.timeout_sync.total_seconds(),
        )
        event = threading.Event()
        while True:
            line = self.process.stdout.readline()
            time_now = datetime.now()  # noqa: DTZ005

            if time_now > time_stop:
                log.debug("[%s] timeout while waiting for sync", type(self).__name__)
                return False
            if time_now > time_last + self.timeout_output:
                log.debug(
                    "[%s] %.0f s timeout while waiting for PTP (is it running?)",
                    type(self).__name__,
                    self.timeout_output.total_seconds(),
                )
                return False
            if not isinstance(line, str) or len(line) < 1:
                event.wait(self.poll_interval)  # rate limiter
                continue

            words = str(line).split()
            if "offset" not in words:
                log.warning("Stdout-line contains no 'offset'")
                event.wait(self.poll_interval)
                continue
            offset_index = words.index("offset")
            if len(words) <= offset_index + 1:
                log.warning("Stdout-line too short after offset")
                event.wait(self.poll_interval)
                continue
            offset_str = words[offset_index + 1]
            if not offset_str.isnumeric():
                log.warning("offset not numerical")
                event.wait(self.poll_interval)
                continue
            time_last = time_now
            offset_value = int(offset_str)
            log.info("[%s] current sync-offset = %d ns", type(self).__name__, offset_value)
            if abs(offset_value) < self.sync_threshold_ns:
                log.info("[%s] goal reached!", type(self).__name__)
                return True

        return False
