""" """

import subprocess
import time
from pathlib import Path

from shepherd_sheep.logger import log


def get_mode() -> str:
    with Path("/sys/shepherd/mode").open(encoding="utf-8") as f:
        return str(f.read().rstrip())


def load_kernel_module() -> None:
    retry_max: int = 10
    run_: int = 0
    path_check = Path("/sys/shepherd/mode")
    wait_max = 3.0
    while run_ < retry_max:
        run_ += 1
        try:
            subprocess.run(
                ["/usr/sbin/modprobe", "--quiet", "shepherd"],
                timeout=10,
                check=True,
                shell=False,
                capture_output=False,
            )
        except subprocess.CalledProcessError:
            pass
        else:
            time_start = time.time()
            while not path_check.exists():
                time.sleep(0.1)
                if time.time() - time_start > wait_max:
                    break
            if time.time() - time_start < wait_max:
                log.debug(
                    "Activated shepherd kernel module (%d. try, %.1f s wait)",
                    run_,
                    time.time() - time_start,
                )
                return
        # cleanup
        remove_kernel_module()
        time.sleep(0.2)

    msg = "Failed to load shepherd kernel module."
    raise SystemError(msg)


def remove_kernel_module() -> None:
    retry_max: int = 10
    run_: int = 0
    while run_ < retry_max:
        run_ += 1
        try:
            subprocess.run(
                [
                    "/usr/sbin/modprobe",
                    "--remove",
                    "--force",
                    "--quiet",
                    "--wait",
                    "300",
                    "shepherd",
                ],
                timeout=10,
                check=True,
                shell=False,
                capture_output=False,
            )
        except subprocess.CalledProcessError:
            continue
        else:
            log.debug("Deactivated shepherd kernel module (%d. try)", run_)
            return

    msg = "Failed to unload shepherd kernel module."
    raise SystemError(msg)


def reload_kernel_module() -> None:
    remove_kernel_module()
    load_kernel_module()


def check_sys_access(iteration: int = 1, *, force_reload: bool = False) -> bool:
    """Return True if access failed."""
    retry_max: int = 5
    if force_reload:
        reload_kernel_module()
    try:  # test for correct usage -> fail early!
        get_mode()
    except FileNotFoundError:
        try:
            if iteration > retry_max:
                log.error("Failed to access sysFS - ran out of retries")
                return True
            log.debug(
                "Failed to access sysFS -> "
                "will try to activate shepherd kernel module (attempt %d/%d)",
                iteration,
                retry_max,
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
