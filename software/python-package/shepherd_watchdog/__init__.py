"""Allows to periodically reset hardware-watchdog on Cape."""

import contextlib
import itertools
import logging
import signal
import subprocess
import sys
import time
from contextlib import suppress
from datetime import datetime
from importlib import metadata
from types import FrameType
from types import TracebackType

from shepherd_sheep.usage_log import usage_logger
from typing_extensions import Self

from shepherd_watchdog.config import WatchdogConfig

# Top-Level Package-logger
log = logging.getLogger("ShpWatchdog")
log.addHandler(logging.StreamHandler())
log.setLevel(logging.DEBUG)
log.propagate = False

# allow importing shepherd on x86 - for testing
with suppress(ModuleNotFoundError):
    from periphery import GPIO


def exit_gracefully(_signum: int, _frame: FrameType | None) -> None:
    log.warning("Exiting from signal %d!", _signum)
    sys.exit(128 + _signum)


gpio_data: list[str] | None = None


def get_gpio_info() -> list[str]:
    ret = subprocess.run(
        ["/usr/bin/sudo", "/usr/bin/gpioinfo"],
        timeout=10,
        check=False,
        shell=False,
        capture_output=True,
    )
    if ret.returncode != 0 or not isinstance(ret.stdout, bytes):
        msg = f"Gpioinfo failed, got: {ret.stdout}"
        raise ValueError(msg)

    values = ret.stdout.decode().split("\n")
    if len(values) < 60:
        msg = f"Gpioinfo failed, got not enough info: {values}"
        raise ValueError(msg)
    return [x.strip() for x in values if not x.startswith("gpiochip")]


def gpio_name_2_num(name: str | int) -> int:
    if isinstance(name, int):
        # keep backward compat for deprecated num-system (i.e. gpio 68)
        return name

    global gpio_data  # noqa: PLW0603
    if gpio_data is None:
        gpio_data = get_gpio_info()

    for pin_num, gpio_date in enumerate(gpio_data):
        if name in gpio_date:
            log.debug("GPIO '%s' was resolved to # %d", name, pin_num)
            return pin_num
    msg = f"Gpio '{name}' not found"
    raise ValueError(msg)


class Watchdog:
    """Allows to periodically reset hardware-watchdog on Cape."""

    def __init__(self) -> None:
        self.cfg = WatchdogConfig.from_file()
        if self.cfg is None:
            self.cfg: WatchdogConfig = WatchdogConfig()
            self.cfg.to_file()

        log.debug("Initializing Shepherd-Watchdog v%s", metadata.version("shepherd-sheep"))
        log.debug(
            "  -> Ack-Signal on pin = %d, interval = %d s", self.cfg.pin_ack, self.cfg.interval
        )
        if self.cfg.network_needed:
            log.info("  -> will also check network connection")
        self.hosts_iter = itertools.cycle(self.cfg.network_hosts)
        self.hosts_stat = dict.fromkeys(self.cfg.network_hosts, True)

    def __enter__(self) -> Self:
        pin_num = gpio_name_2_num(self.cfg.pin_ack)
        self.gpio_ack = GPIO(pin_num, "out")
        log.debug("Configured GPIO")
        return self

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.gpio_ack.close()

    @staticmethod
    def ping(host: str) -> bool:
        """Ping a desired host and return True on success.

        Ping is configured to collect 1 reply and timeout after 2 seconds (wait).
        """
        return (
            subprocess.run(  # noqa: S603
                ["/usr/bin/ping", "-c1", "-w2", host],
                timeout=3,
                check=False,
                shell=False,
                capture_output=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )

    @staticmethod
    def reboot() -> None:
        """Force restart of system."""
        subprocess.run(
            ["/usr/bin/sudo", "/usr/sbin/reboot"],
            timeout=3,
            check=False,
        )

    def check_connection(self) -> None:
        """Test if public internet servers are reachable.

        The host-list could also be populated with internal IPs to just check network access.
        """
        host = next(self.hosts_iter)
        self.hosts_stat[host] = self.ping(host)
        count = sum(self.hosts_stat.values())
        if self.hosts_stat[host]:
            log.debug("Pinged %s", host)
        else:
            log.warning("Failed to ping to %s (%d still online)", host, count)
        if count < 1:
            log.error("Network connection failed persistently -> will reboot!")
            with contextlib.suppress(BaseException):
                usage_logger(datetime.now().astimezone(), "reboot due to connection failure")
            self.reboot()

    def run(self) -> None:
        """Prevent system-reset from watchdog.

        cape-rev2 has a watchdog that can turn on (or restart) the BB every ~60 min
        """
        try:
            while True:
                if self.cfg.network_needed:
                    self.check_connection()
                self.gpio_ack.write(value=True)
                time.sleep(0.002)
                self.gpio_ack.write(value=False)
                log.debug("Signaled ACK to Watchdog")
                time.sleep(self.cfg.interval)
        except SystemExit:
            return


def main() -> None:
    signal.signal(signal.SIGTERM, exit_gracefully)
    signal.signal(signal.SIGINT, exit_gracefully)
    with Watchdog() as watchdog:
        watchdog.run()


if __name__ == "__main__":
    main()
