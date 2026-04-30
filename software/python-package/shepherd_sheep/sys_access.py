import subprocess
import time
from pathlib import Path

from .logger import log


def kernel_module_is_active() -> bool:
    """Return True if access the sysfs of the kMod."""
    try:  # test for correct usage -> fail early!
        # this is sysfs_interface.get_mode() to avoid import
        with Path("/sys/shepherd/mode").open(encoding="utf-8") as f:
            _ = f.read()
    except FileNotFoundError:
        return False
    except PermissionError:
        raise RuntimeError("Failed to access sysFS -> run shepherd-sheep with 'sudo'!") from None
    return True


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
                    "shepherd",
                ],  # "--wait 300" does not help
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


def load_kernel_module() -> None:
    retry_max: int = 10
    run_: int = 0
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
            while not kernel_module_is_active():
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
        log.warning(
            "Failed to load shepherd kernel module - will remove & try again (%d. try)", run_
        )
        remove_kernel_module()
        time.sleep(0.5)

    msg = "Failed to load shepherd kernel module."
    raise SystemError(msg)


def reload_kernel_module() -> None:
    """Makes sure to create a clean slate.

    This will unload, load, test access and raises if
    - permissions are missing
    - reload of kMod failed
    """
    kernel_module_is_active()  # check for permissions - raise early
    remove_kernel_module()
    load_kernel_module()


def check_on_kernel_module() -> None:
    """Make sure the module is running - start if needed.

    This will test access and unload/load if needed. It raises if
    - permissions are missing
    - reload of kMod failed
    """
    if not kernel_module_is_active():
        reload_kernel_module()


def disable_ntp() -> None:
    ret = subprocess.run(
        ["/usr/bin/systemctl", "is-active", "--quiet", "systemd-timesyncd.service"],
        timeout=20,
        check=False,
    ).returncode
    if ret == 0:
        subprocess.run(
            ["/usr/bin/systemctl", "stop", "systemd-timesyncd.service"],
            timeout=20,
            check=False,
        )
        log.debug("Deactivated systemd-timesyncd.service (NTP)")


def resync_ptp() -> bool:
    commands = [
        ["/usr/bin/systemctl", "stop", "phc2sys@eth0"],
        ["/usr/bin/systemctl", "stop", "ptp4l@eth0"],
        ["/usr/sbin/ntpdate", "-b", "-s", "-u", "pool.ntp.org"],
        ["/usr/bin/systemctl", "start", "phc2sys@eth0"],
        ["/usr/bin/systemctl", "start", "ptp4l@eth0"],
    ]
    had_error = False
    for command in commands:
        had_error |= subprocess.run(command, timeout=10, check=False).returncode > 0  # noqa: S603
    reload_kernel_module()  # for restarting sync-loop to PRU
    return had_error
