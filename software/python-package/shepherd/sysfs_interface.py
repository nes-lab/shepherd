# -*- coding: utf-8 -*-

"""
shepherd.sysfs_interface
~~~~~
Provides convenience functions for interacting with the sysfs interface
provided by the shepherd kernel module


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""

import sys
import logging
import time
import struct
from pathlib import Path
from typing import NoReturn

logger = logging.getLogger(__name__)
sysfs_path = Path("/sys/shepherd")


class SysfsInterfaceException(Exception):
    pass


attribs = {
    "mode": {"path": "mode", "type": str},
    "state": {"path": "state", "type": str},
    "n_buffers": {"path": "n_buffers", "type": int},
    "buffer_period_ns": {"path": "buffer_period_ns", "type": int},
    "samples_per_buffer": {"path": "samples_per_buffer", "type": int},
    "mem_address": {"path": "memory/address", "type": int},
    "mem_size": {"path": "memory/size", "type": int},
}


def wait_for_state(state: str, timeout: float) -> NoReturn:
    """Waits until shepherd is in specified state.

    Polls the sysfs 'state' attribute until it contains the target state or
    until the timeout expires.

    Args:
        state (int): Target state
        timeout (float): Timeout in seconds
    """
    ts_start = time.time()
    while True:
        current_state = get_state()
        if current_state == state:
            return time.time() - ts_start

        if time.time() - ts_start > timeout:
            raise SysfsInterfaceException(
                (
                    f"timed out waiting for state { state } - "
                    f"state is { current_state }"
                )
            )
        time.sleep(0.1)


def set_start(start_time: int = None) -> NoReturn:
    """Starts shepherd.

    Writes 'start' to the 'state' sysfs attribute in order to transition from
    'idle' to 'running' state. Optionally allows to start at a later point in
    time, transitioning shepherd to 'armed' state.

    Args:
        start_time (int): Desired start time in unix time
    """
    current_state = get_state()
    logger.debug(f"current state of shepherd kernel module: {current_state}")
    if current_state != "idle":
        raise SysfsInterfaceException(
            f"Cannot start from state { current_state }"
        )

    with open(str(sysfs_path / "state"), "w") as f:
        if start_time is None:
            logger.debug(f"writing 'start' to sysfs")
            f.write("start")
        else:
            f.write(f"{ start_time }")


def set_stop() -> NoReturn:
    """Stops shepherd.

    Writes 'stop' to the 'state' sysfs attribute in order to transition from
    any state to 'idle'.
    """
    current_state = get_state()
    if current_state != "running":
        raise SysfsInterfaceException(
            f"Cannot stop from state { current_state }"
        )

    with open(str(sysfs_path / "state"), "w") as f:
        f.write("stop")


def write_mode(mode: str) -> NoReturn:
    """Sets the shepherd mode.

    Sets shepherd mode by writing corresponding string to the 'mode' sysfs
    attribute.

    Args:
        mode (str): Target mode. Must be one of harvesting, load, emulation
    """
    if mode not in ["harvesting", "load", "emulation", "virtcap", "debug"]:
        raise SysfsInterfaceException("invalid value for mode")
    if get_state() != "idle":
        raise SysfsInterfaceException(
            f"Cannot set mode when shepherd is { get_state() }"
        )

    logger.debug(f"mode: {mode}")
    with open(str(sysfs_path / "mode"), "w") as f:
        f.write(mode)


def write_dac_aux_voltage(voltage_raw: int) -> NoReturn:
    """ Sends the auxiliary voltage (dac channel B) to the PRU core.

    Args:
        voltage_raw: desired voltage in volt
    """
    with open(str(sysfs_path / "dac_auxiliary_voltage_raw"), "w") as f:
        logger.debug(f"Sending raw auxiliary voltage (dac channel B): {voltage_raw}")
        f.write(str(voltage_raw))


def read_dac_aux_voltage() -> int:
    """ Reds the auxiliary voltage (dac channel B) to the PRU core.

    Args:

    Returns: voltage as dac_raw
    """
    with open(str(sysfs_path / "dac_auxiliary_voltage_raw"), "r") as f:
        settings = f.read().rstrip()

    int_settings = [int(x) for x in settings.split()]
    return int_settings[0]


def write_calibration_settings(adc_current_gain: int, adc_current_offset: int,
                               dac_voltage_gain: int, dac_voltage_offset: int) -> NoReturn:
    """Sends the calibration settings to the PRU core.

    The virtual-source algorithms use adc measurements and dac-output

    """
    if adc_current_gain < 0:
        logger.warning(f"sending calibration with negative ADC-gain: {adc_current_gain}")
    if dac_voltage_gain < 0:
        logger.warning(f"sending calibration with negative DAC-gain: {adc_current_gain}")

    with open(str(sysfs_path / "calibration_settings"), "w") as f:
        output = f"{adc_current_gain} {adc_current_offset} \n" \
                 f"{dac_voltage_gain} {dac_voltage_offset}"
        logger.debug(f"Sending calibration settings: {output}")
        f.write(output)


def read_calibration_settings() -> tuple[int, int, int, int]:
    """Retrieve the calibration settings from the PRU core.

    The virtual-source algorithms use adc measurements and dac-output

    """
    with open(str(sysfs_path / "calibration_settings"), "r") as f:
        settings = f.read().rstrip()

    int_settings = [int(x) for x in settings.split()]
    return int_settings[0], int_settings[1], int_settings[2], int_settings[3]


def write_virtsource_settings(settings: list) -> NoReturn:
    """Sends the virtcap settings to the PRU core.

    The virtcap algorithm uses these settings to configure emulation.

    """
    logger.debug(f"Writing virtcap to sysfs_interface, first value is {settings[0]}")

    with open(str(sysfs_path / "virtcap_settings"), "w") as file:
        for setting in settings:
            if len(setting) == 1:
                output = str(setting)
            else:
                setting = [str(i) for i in setting]
                output = " ".join(setting)
        file.write(output + " \n")


def read_virtsource_settings() -> str:
    """Retreive the virtcap settings to the PRU core.

    The virtcap algorithm uses these settings to configure emulation.

    """
    with open(str(sysfs_path / "virtcap_settings"), "r") as f:
        settings = f.read().rstrip()

    return settings


def make_attr_getter(name: str, path: str, attr_type: type):
    """Instantiates a getter function for a sysfs attribute.

    To avoid hard-coding getter functions for all sysfs attributes, this
    function generates a getter function that also handles casting to the
    corresponding type

    Args:
        name (str): Name of the attribute
        path (str): Relative path of the attribute with respect to root
            shepherd sysfs path
        attr_type(type): Type of attribute, e.g. int or str
    """

    def _function():
        with open(str(sysfs_path / path), "r") as f:
            return attr_type(f.read().rstrip())

    return _function


# Automatically create getter for all attributes in props
for name, props in attribs.items():
    fun = make_attr_getter(name, props["path"], props["type"])
    setattr(sys.modules[__name__], f"get_{ name }", fun)
