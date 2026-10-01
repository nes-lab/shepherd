"""
The FNs called during main-loop should be optimized!
- generators / iterator are 10x faster

Benchmark results 2026-10-01
        read_pru_msg_v1() = 0.512 s for 1000 reps
        next(pru_msg_v2) = 0.046 s for 1000 reps
        read_pru_msg_now() = 0.048 s for 1000 reps
"""

import time
from collections.abc import Generator
from pathlib import Path
from timeit import timeit

from shepherd_sheep.logger import log
from shepherd_sheep.logger import set_verbosity
from shepherd_sheep.sysfs_interface import SysfsInterfaceError
from shepherd_sheep.sysfs_interface import read_pru_msg


def read_pru_msg_v1() -> tuple[int, list[int]] | None:
    try:
        with Path("/sys/shepherd/pru_msg_box").open(encoding="utf-8") as f:
            message = f.read().rstrip()
        msg_parts = [int(x) for x in message.split()]
        if len(msg_parts) < 2:
            raise SysfsInterfaceError("pru_msg was too short")  # noqa: TRY301
        return msg_parts[0], msg_parts[1:]
    except SysfsInterfaceError:
        return None


def read_pru_msg_v2() -> Generator[tuple[int, list[int]] | None, None, None]:
    while True:
        with Path("/sys/shepherd/pru_msg_box").open(encoding="utf-8") as f:
            while f.readable():
                f.seek(0)
                message = f.read().rstrip()
                msg_parts = [int(x) for x in message.split()]
                if len(msg_parts) < 2:
                    yield None
                yield msg_parts[0], msg_parts[1:]


pru_msg_v2 = read_pru_msg_v2()


def read_pru_msg_now() -> tuple[int, list[int]] | None:
    return read_pru_msg()


if __name__ == "__main__":
    set_verbosity()

    for routine_under_test in [
        "read_pru_msg_v1()",
        "next(pru_msg_v2)",
        "read_pru_msg_now()",
    ]:
        repetitions = 1000
        time.sleep(1)
        time_total = timeit(
            routine_under_test,
            globals=globals(),
            number=repetitions,
        )
        log.info("\t%s = %.3f s for %d reps", routine_under_test, time_total, repetitions)
