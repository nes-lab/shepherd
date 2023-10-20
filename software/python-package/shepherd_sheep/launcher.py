"""
shepherd.launcher
~~~~~
Launcher allows to start and stop shepherd service with the press of a button.
Relies on systemd service.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import os
import time
from contextlib import suppress
from threading import Event
from threading import Thread

from .logger import log

# allow importing shepherd on x86 - for testing
with suppress(ModuleNotFoundError):
    import dbus
    from periphery import GPIO


def call_repeatedly(interval: float, func, *args):  # type: ignore
    stopped = Event()

    def loop():
        while not stopped.wait(interval):
            # the first call is in `interval` secs
            func(*args)

    Thread(target=loop).start()
    return stopped.set


class Launcher:
    """Stores data coming from PRU's in HDF5 format.

    Args:
        pin_button (int): Pin number where button is connected. Must be
            configured as input with pull up and connected against ground
        pin_led (int): Pin number of LED for displaying launcher status
        service_name (str): Name of shepherd systemd service

    """

    def __init__(
        self,
        pin_button: int = 65,
        pin_led: int = 22,
        pin_ack_watchdog: int = 68,
        service_name: str = "shepherd",
    ):
        self.pin_button = pin_button
        self.pin_led = pin_led
        self.pin_ack_watchdog = pin_ack_watchdog
        self.service_name = service_name

    def __enter__(self):
        self.gpio_led = GPIO(self.pin_led, "out")
        self.gpio_button = GPIO(self.pin_button, "in")
        self.gpio_ack_watchdog = GPIO(self.pin_ack_watchdog, "out")
        self.gpio_button.edge = "falling"
        log.debug("configured gpio")
        self.cancel_wd_timer = call_repeatedly(interval=600, func=self.ack_watchdog)

        sys_bus = dbus.SystemBus()
        systemd1 = sys_bus.get_object(
            "org.freedesktop.systemd1",
            "/org/freedesktop/systemd1",
        )
        self.manager = dbus.Interface(systemd1, "org.freedesktop.systemd1.Manager")

        shepherd_object = self.manager.LoadUnit(f"{ self.service_name }.service")
        self.shepherd_proxy = sys_bus.get_object(
            "org.freedesktop.systemd1",
            str(shepherd_object),
        )
        log.debug("configured dbus for systemd")

        return self

    def __exit__(self, *exc):  # type: ignore
        self.gpio_led.close()
        self.gpio_button.close()

    def run(self) -> None:
        """Infinite loop waiting for button presses.

        Waits for falling edge on configured button pin. On detection of the
        edge, shepherd service is either started or stopped. Double button
        press while idle causes system shutdown.
        """
        while True:
            log.info("waiting for falling edge..")
            self.gpio_led.write(True)
            if not self.gpio_button.poll():
                # NOTE poll is suspected to exit after ~ 1-2 weeks running
                #      -> fills mmc with random measurement
                # TODO observe behavior, hopefully this change fixes the bug
                continue
            self.gpio_led.write(False)
            log.debug("edge detected")
            if not self.get_state():
                time.sleep(0.25)
                if self.gpio_button.poll(timeout=5):
                    log.debug("falling edge detected")
                    log.info("shutdown requested")
                    self.initiate_shutdown()
                    self.gpio_led.write(False)
                    time.sleep(3)
                    continue
            self.set_service(not self.get_state())
            time.sleep(10)

    def get_state(self, timeout: float = 10) -> bool:
        """Queries systemd for state of shepherd service.

        Args:
            timeout (float): Time to wait for service state to settle

        Raises:
            TimeoutError: If state remains changing for longer than timeout
        """
        ts_end = time.time() + timeout

        while True:
            systemd_state = self.shepherd_proxy.Get(
                "org.freedesktop.systemd1.Unit",
                "ActiveState",
                dbus_interface="org.freedesktop.DBus.Properties",
            )
            if systemd_state in {"deactivating", "activating"}:
                time.sleep(0.1)
            else:
                break
            if time.time() > ts_end:
                raise TimeoutError("Timed out waiting for service state")

        log.debug("service ActiveState: %s", systemd_state)

        if systemd_state == "active":
            return True
        if systemd_state == "inactive":
            return False
        raise Exception(f"Unknown state { systemd_state }")

    def set_service(self, requested_state: bool):
        """Changes state of shepherd service.

        Args:
            requested_state (bool): Target state of service
        """
        active_state = self.get_state()

        if requested_state == active_state:
            log.debug("service already in requested state")
            self.gpio_led.write(active_state)
            return None

        if active_state:
            log.info("stopping service")
            self.manager.StopUnit("shepherd.service", "fail")
        else:
            log.info("starting service")
            self.manager.StartUnit("shepherd.service", "fail")

        time.sleep(1)

        new_state = self.get_state()
        if new_state != requested_state:
            raise Exception("state didn't change")

        return new_state

    def initiate_shutdown(self, timeout: int = 5) -> None:
        """Initiates system shutdown.

        Args:
            timeout (int): Number of seconds to wait before powering off
                system
        """
        log.debug("initiating shutdown routine..")
        time.sleep(0.25)
        for _ in range(timeout):
            if self.gpio_button.poll(timeout=0.5):
                log.debug("edge detected")
                log.info("shutdown canceled")
                return
            self.gpio_led.write(True)
            if self.gpio_button.poll(timeout=0.5):
                log.debug("edge detected")
                log.info("shutdown canceled")
                return
            self.gpio_led.write(False)
        os.sync()
        log.info("shutting down now")
        self.manager.PowerOff()

    def ack_watchdog(self) -> None:
        """prevent system-reset from watchdog
        hw-rev2 has a watchdog that can turn on the BB every ~60 min

        """
        self.gpio_ack_watchdog.write(True)
        time.sleep(0.002)
        self.gpio_ack_watchdog.write(False)
        log.debug("Signaled ACK to Watchdog")
