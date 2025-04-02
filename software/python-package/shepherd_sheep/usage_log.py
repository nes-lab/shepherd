import os
from datetime import datetime
from pathlib import Path

path_log = Path("/var/shepherd/log.csv")


def usage_logger(ts_start: datetime, cmd: str) -> None:
    ts_now = datetime.now().astimezone()
    existed = path_log.exists()
    with path_log.open("a", encoding="utf-8") as fh:
        if not existed:
            fh.write("time_start, time_stop, runtime [s], command\n")
        fh.write(f"{ts_start}, {ts_now}, {(ts_now - ts_start).total_seconds()}, {cmd}\n")


def get_last_usage() -> str | None:
    """Equivalent CLI call is `tail -n 1 file`"""
    if not path_log.exists():
        return None
    with path_log.open("rb") as fh:
        try:  # catch OSError in case of a one line file
            fh.seek(-2, os.SEEK_END)
            while fh.read(1) != b"\n":
                fh.seek(-2, os.SEEK_CUR)
        except OSError:
            fh.seek(0)
        return fh.readline().decode()
