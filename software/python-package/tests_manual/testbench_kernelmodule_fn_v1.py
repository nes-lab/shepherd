""" """

import subprocess
import time
from pathlib import Path

from shepherd_sheep.logger import log


def get_mode() -> str:
    with Path("/sys/shepherd/mode").open(encoding="utf-8") as f:
        return str(f.read().rstrip())


def load_kernel_module() -> None:
    try_max: int = 6
    run_: int = 0
    while run_ < try_max:
        ret = subprocess.run(
            ["/usr/sbin/modprobe", "-a", "shepherd"],
            timeout=60,
            check=False,
        ).returncode
        run_ += 1
        if ret == 0:
            log.debug("Activated shepherd kernel module (%d. try)", run_)
            time.sleep(3)
            return
        time.sleep(1)
    raise SystemError("Failed to load shepherd kernel module.")


def remove_kernel_module() -> None:
    try_max: int = 6
    run_: int = 0
    while run_ < try_max:
        ret = subprocess.run(
            ["/usr/sbin/modprobe", "-rf", "shepherd"],
            timeout=60,
            capture_output=True,
            check=False,
        ).returncode
        run_ += 1
        if ret == 0:
            log.debug("Deactivated shepherd kernel module (%d. try)", run_)
            time.sleep(1)
            return
        time.sleep(1)
    msg = "Failed to unload shepherd kernel module."
    raise SystemError(msg)


def reload_kernel_module() -> None:
    remove_kernel_module()
    load_kernel_module()


def check_sys_access(iteration: int = 1) -> bool:
    """Return True if access failed."""
    iter_max: int = 5
    try:  # test for correct usage -> fail early!
        get_mode()
    except FileNotFoundError:
        try:
            if iteration > iter_max:
                log.error("Failed to access sysFS - ran out of retries")
                return True
            log.debug(
                "Failed to access sysFS -> "
                "will try to activate shepherd kernel module (attempt %d/%d)",
                iteration,
                iter_max,
            )
            reload_kernel_module()
            check_sys_access(iteration + 1)
        except FileNotFoundError:
            log.error(
                "RuntimeError: Failed to access sysFS -> "
                "make sure shepherd kernel module is active!",
            )
            return True
    except PermissionError:
        log.error(
            "RuntimeError: Failed to access sysFS -> run shepherd-sheep with 'sudo'!",
        )
        return True
    return False
