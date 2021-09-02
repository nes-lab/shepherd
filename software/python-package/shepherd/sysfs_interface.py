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

from shepherd.calibration import CalibrationData
from shepherd import calibration_default

logger = logging.getLogger(__name__)
sysfs_path = Path("/sys/shepherd")


class SysfsInterfaceException(Exception):
    pass


# TODO: what is with "None"?
shepherd_modes = ["harvesting", "harvesting_test", "emulation", "emulation_test", "emulation_cal", "debug"]

attribs = {
    "mode": {"path": "mode", "type": str},
    "state": {"path": "state", "type": str},
    "n_buffers": {"path": "n_buffers", "type": int},
    "buffer_period_ns": {"path": "buffer_period_ns", "type": int},
    "samples_per_buffer": {"path": "samples_per_buffer", "type": int},
    "mem_address": {"path": "memory/address", "type": int},
    "mem_size": {"path": "memory/size", "type": int},
}


def wait_for_state(wanted_state: str, timeout: float) -> NoReturn:
    """Waits until shepherd is in specified state.

    Polls the sysfs 'state' attribute until it contains the target state or
    until the timeout expires.

    Args:
        wanted_state (int): Target state
        timeout (float): Timeout in seconds
    """
    ts_start = time.time()
    while True:
        current_state = get_state()
        if current_state == wanted_state:
            return time.time() - ts_start

        if time.time() - ts_start > timeout:
            raise SysfsInterfaceException(
                (
                    f"timed out waiting for state { wanted_state } - "
                    f"state is { current_state }"
                )
            )
            # TODO: does it really need an exception?
        time.sleep(0.1)


def set_start(start_time: float = None) -> NoReturn:
    """ Starts shepherd.

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
        if isinstance(start_time, float):
            start_time = int(start_time)
        if isinstance(start_time, int):
            logger.debug(f"writing start-time = {start_time} to sysfs")
            f.write(f"{start_time}")
        else:  # unknown type
            logger.debug(f"writing 'start' to sysfs")
            f.write("start")


def set_stop(force: bool = False) -> NoReturn:
    """ Stops shepherd.

    Writes 'stop' to the 'state' sysfs attribute in order to transition from
    any state to 'idle'.
    """
    if not force:
        current_state = get_state()
        if current_state != "running":
            raise SysfsInterfaceException(f"Cannot stop from state { current_state }")

    with open(str(sysfs_path / "state"), "w") as f:
        f.write("stop")


def write_mode(mode: str, force: bool = False) -> NoReturn:
    """ Sets the shepherd mode.

    Sets shepherd mode by writing corresponding string to the 'mode' sysfs
    attribute.

    Args:
        mode (str): Target mode. Must be one of harvesting, emulation or debug
    """
    if mode not in shepherd_modes:
        raise SysfsInterfaceException("invalid value for mode")
    if force:
        set_stop(force=True)
        wait_for_state("idle", 5)
    else:
        if get_state() != "idle":
            raise SysfsInterfaceException(f"Cannot set mode when shepherd is { get_state() }")

    logger.debug(f"sysfs/mode: '{mode}'")
    with open(str(sysfs_path / "mode"), "w") as f:
        f.write(mode)


def write_dac_aux_voltage(calibration_settings: CalibrationData, voltage_V: float) -> NoReturn:
    """ Sends the auxiliary voltage (dac channel B) to the PRU core.

    Args:
        voltage_V: desired voltage in volt
    """
    if voltage_V is None:
        voltage_V = 0.0
    elif voltage_V is False:
        voltage_V = 0.0
    elif (voltage_V is True) or (isinstance(voltage_V, str) and "main" in voltage_V.lower()):
        # set bit 20 (during pru-reset) and therefore link both adc-channels
        write_dac_aux_voltage_raw(2 ** 20)
        return
    elif isinstance(voltage_V, str) and "mid" in voltage_V.lower():
        # set bit 21 (during pru-reset) and therefore output intermediate (storage cap) voltage on second channel
        write_dac_aux_voltage_raw(2 ** 21)
        return

    if voltage_V < 0.0:
        raise SysfsInterfaceException(f"sending voltage with negative value: {voltage_V}")
    if voltage_V > 5.0:
        raise SysfsInterfaceException(f"sending voltage above limit of 5V: {voltage_V}")

    if calibration_settings is None:
        output = calibration_default.dac_ch_b_voltage_to_raw(voltage_V)
    else:
        output = calibration_settings.convert_value_to_raw("emulation", "dac_voltage_b", voltage_V)

    # TODO: currently only an assumption that it is for emulation, could also be for harvesting
    # TODO: fn would be smoother if it contained the offset/gain-dict of the cal-data. but this requires a general FN for conversion
    write_dac_aux_voltage_raw(output)


def write_dac_aux_voltage_raw(voltage_raw: int) -> NoReturn:
    """ Sends the auxiliary voltage (dac channel B) to the PRU core.

    Args:
        voltage_raw: desired voltage in volt
    """
    if voltage_raw >= (2**16):
        logger.info(f"DAC: sending raw-voltage above possible limit of 16bit-value -> this will link both channels")
    with open(str(sysfs_path / "dac_auxiliary_voltage_raw"), "w") as f:
        logger.debug(f"Sending raw auxiliary voltage (dac channel B): {voltage_raw}")
        f.write(str(voltage_raw))


def read_dac_aux_voltage(cal_settings: CalibrationData) -> float:
    """ Reads the auxiliary voltage (dac channel B) from the PRU core.

    Args:
        cal_settings: dict with offset/gain

    Returns:
        aux voltage
    """
    value_raw = read_dac_aux_voltage_raw()
    if cal_settings is None:
        voltage = calibration_default.dac_ch_a_raw_to_voltage(value_raw)
    else:
        voltage = cal_settings.convert_raw_to_value("emulation", "dac_voltage_b", value_raw)
    return voltage


def read_dac_aux_voltage_raw() -> int:
    """ Reads the auxiliary voltage (dac channel B) to the PRU core.

    Args:

    Returns: voltage as dac_raw
    """
    with open(str(sysfs_path / "dac_auxiliary_voltage_raw"), "r") as f:
        settings = f.read().rstrip()

    int_settings = [int(x) for x in settings.split()]
    return int_settings[0]


def write_calibration_settings(cal_pru: dict) -> NoReturn:  # more precise dict[str, int], trouble with py3.6
    """Sends the calibration settings to the PRU core.

    The virtual-source algorithms use adc measurements and dac-output

    """
    if cal_pru['adc_gain'] < 0:
        raise SysfsInterfaceException(f"sending calibration with negative ADC-gain: {cal_pru['adc_gain']}")
    if cal_pru['dac_gain'] < 0:
        raise SysfsInterfaceException(f"sending calibration with negative DAC-gain: {cal_pru['dac_gain']}")
    wait_for_state("idle", 3.0)

    with open(str(sysfs_path / "calibration_settings"), "w") as f:
        output = f"{int(cal_pru['adc_gain'])} {int(cal_pru['adc_offset'])} \n" \
                 f"{int(cal_pru['dac_gain'])} {int(cal_pru['dac_offset'])}"
        logger.debug(f"Sending calibration settings: {output}")
        f.write(output)


def read_calibration_settings() -> dict:  # more precise dict[str, int], trouble with py3.6
    """Retrieve the calibration settings from the PRU core.

    The virtual-source algorithms use adc measurements and dac-output

    """
    with open(str(sysfs_path / "calibration_settings"), "r") as f:
        settings = f.read().rstrip()

    int_settings = [int(x) for x in settings.split()]
    cal_pru = {"adc_gain": int_settings[0], "adc_offset": int_settings[1],
               "dac_gain": int_settings[2], "dac_offset": int_settings[3]}
    return cal_pru


def write_virtsource_settings(settings: list) -> NoReturn:
    """Sends the virtual-source settings to the PRU core.

    The virtual-source algorithm uses these settings to configure emulation.

    """
    logger.debug(f"Writing virtsource to sysfs_interface, first value is {settings[0]}")

    output = str("")
    for setting in settings:
        if isinstance(setting, int):
            output += f"{setting} \n"
        elif isinstance(setting, list):
            setting = [str(i) for i in setting]
            output += " ".join(setting) + " \n"
        else:
            raise SysfsInterfaceException(f"virtSource value {setting} has wrong type ({type(setting)})")

    wait_for_state("idle", 3.0)

    with open(str(sysfs_path / "virtsource_settings"), "w") as file:
        file.write(output)


def read_virtsource_settings() -> list:
    """Retreive the virtual source settings from the PRU core.

    The virtsource algorithm uses these settings to configure emulation.

    """
    with open(str(sysfs_path / "virtsource_settings"), "r") as f:
        settings = f.read().rstrip()
    int_settings = [int(x) for x in settings.split()]
    return int_settings


def write_pru_msg(msg_type: int, values: list) -> NoReturn:
    """
    Args:
        msg_type:
        value1:
        value2:
    Returns:
    """
    if (not isinstance(msg_type, int)) or (msg_type < 0) or (msg_type > 255) :
        raise SysfsInterfaceException(f"pru_msg-type has invalid type, "
            f"expected u8 for type (={type(msg_type)}) and content (={msg_type})")

    if not isinstance(values, list):
        # catch all single ints and floats
        values = [int(values), 0]

    for value in values:
        if (not isinstance(value, int)) or (value < 0) or (value >= 2**32):
            raise SysfsInterfaceException(f"pru_msg-value has invalid type, "
                                          f"expected u32 for type (={type(value)}) and content (={value})")

    with open(str(sysfs_path / "pru_msg_box"), "w") as file:
        file.write(f"{msg_type} {values[0]} {values[1]}")


def read_pru_msg() -> tuple:
    """
    Returns:
    """
    with open(str(sysfs_path / "pru_msg_box"), "r") as f:
        message = f.read().rstrip()
    msg_parts = [int(x) for x in message.split()]
    if len(msg_parts) < 2:
        raise SysfsInterfaceException(f"pru_msg was too short")
    return msg_parts[0], msg_parts[1:]  # TODO: can be widened to two type + 2 values, not needed currently


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
