# -*- coding: utf-8 -*-

"""
shepherd.sysfs_interface
~~~~~
Provides convenience functions for interacting with the sysfs interface
provided by the shepherd kernel module


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import logging
import time
from pathlib import Path
from typing import NoReturn, Union

from shepherd.calibration import CalibrationData
from shepherd import calibration_default

logger = logging.getLogger(__name__)
sysfs_path = Path("/sys/shepherd")


class SysfsInterfaceException(Exception):
    pass


# dedicated sampling modes
# - _adc_read - modes are used per rpc (currently to calibrate the hardware)
# TODO: what is with "None"?
shepherd_modes = ["harvester", "hrv_adc_read", "emulator", "emu_adc_read", "debug"]


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
                    f"timed out waiting for state { wanted_state } - "
                    f"state is { current_state }"
            )

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

    with open(sysfs_path/"state", "w") as f:
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

    with open(sysfs_path/"state", "w") as f:
        f.write("stop")


def write_mode(mode: str, force: bool = False) -> NoReturn:
    """ Sets the shepherd mode.

    Sets shepherd mode by writing corresponding string to the 'mode' sysfs
    attribute.

    :param mode: (str) Target mode. Must be one of harvester, emulator or debug
    :param force:
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
    with open(sysfs_path/"mode", "w") as f:
        f.write(mode)


def write_dac_aux_voltage(calibration_settings: Union[CalibrationData, None], voltage: float) -> NoReturn:
    """ Sends the auxiliary voltage (dac channel B) to the PRU core.

    Args:
        :param voltage: desired voltage in volt
        :param calibration_settings: optional set to convert volt to raw
    """
    if voltage is None:
        voltage = 0.0
    elif voltage is False:
        voltage = 0.0
    elif (voltage is True) or (isinstance(voltage, str) and "main" in voltage.lower()):
        # set bit 20 (during pru-reset) and therefore link both adc-channels
        write_dac_aux_voltage_raw(2 ** 20)
        return
    elif isinstance(voltage, str) and "mid" in voltage.lower():
        # set bit 21 (during pru-reset) and therefore output intermediate (storage cap) voltage on second channel
        write_dac_aux_voltage_raw(2 ** 21)
        return

    if voltage < 0.0:
        raise SysfsInterfaceException(f"sending voltage with negative value: {voltage}")
    if voltage > 5.0:
        raise SysfsInterfaceException(f"sending voltage above limit of 5V: {voltage}")

    if calibration_settings is None:
        output = calibration_default.dac_voltage_to_raw(voltage)
    else:
        output = calibration_settings.convert_value_to_raw("emulator", "dac_voltage_b", voltage)

    logger.debug(f"Set voltage of supply for auxiliary Target to {voltage} V (raw={output})")
    # TODO: currently only an assumption that it is for emulation, could also be for harvesting
    write_dac_aux_voltage_raw(output)


def write_dac_aux_voltage_raw(voltage_raw: int) -> NoReturn:
    """ Sends the auxiliary voltage (dac channel B) to the PRU core.

    Args:
        voltage_raw: desired voltage as raw int for DAC
    """
    if voltage_raw >= (2**16):
        logger.info(f"DAC: sending raw-voltage above possible limit of 16bit-value -> this might trigger commands")
    with open(sysfs_path/"dac_auxiliary_voltage_raw", "w") as f:
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
        voltage = calibration_default.dac_raw_to_voltage(value_raw)
    else:
        voltage = cal_settings.convert_raw_to_value("emulator", "dac_voltage_b", value_raw)
    return voltage


def read_dac_aux_voltage_raw() -> int:
    """ Reads the auxiliary voltage (dac channel B) to the PRU core.

    Args:

    Returns: voltage as dac_raw
    """
    with open(sysfs_path/"dac_auxiliary_voltage_raw", "r") as f:
        settings = f.read().rstrip()

    int_settings = [int(x) for x in settings.split()]
    return int_settings[0]


def write_calibration_settings(cal_pru: dict) -> NoReturn:  # more precise dict[str, int], trouble with py3.6
    """Sends the calibration settings to the PRU core.

    The virtual-source algorithms use adc measurements and dac-output

    """
    if cal_pru['adc_current_gain'] < 0:
        raise SysfsInterfaceException(f"sending calibration with negative ADC-C-gain: {cal_pru['adc_current_gain']}")
    if cal_pru['adc_voltage_gain'] < 0:
        raise SysfsInterfaceException(f"sending calibration with negative ADC-V-gain: {cal_pru['adc_voltage_gain']}")
    if cal_pru['dac_voltage_gain'] < 0:
        raise SysfsInterfaceException(f"sending calibration with negative DAC-gain: {cal_pru['dac_voltage_gain']}")
    wait_for_state("idle", 3.0)

    with open(sysfs_path/"calibration_settings", "w") as f:
        output = f"{int(cal_pru['adc_current_gain'])} {int(cal_pru['adc_current_offset'])} \n" \
                 f"{int(cal_pru['adc_voltage_gain'])} {int(cal_pru['adc_voltage_offset'])} \n" \
                 f"{int(cal_pru['dac_voltage_gain'])} {int(cal_pru['dac_voltage_offset'])}"
        logger.debug(f"Sending calibration settings: {output}")
        f.write(output)


def read_calibration_settings() -> dict:  # more precise dict[str, int], trouble with py3.6
    """Retrieve the calibration settings from the PRU core.

    The virtual-source algorithms use adc measurements and dac-output

    """
    with open(sysfs_path/"calibration_settings", "r") as f:
        settings = f.read().rstrip()

    int_settings = [int(x) for x in settings.split()]
    cal_pru = {"adc_gain": int_settings[0], "adc_offset": int_settings[1],
               "dac_gain": int_settings[2], "dac_offset": int_settings[3]}
    return cal_pru


def write_virtual_converter_settings(settings: list) -> NoReturn:
    """Sends the virtual-converter settings to the PRU core.

    The pru-algorithm uses these settings to configure emulator.

    """
    logger.debug(f"Writing virtual converter to sysfs_interface, first value is {settings[0]}")

    output = ""
    for setting in settings:
        if isinstance(setting, int):
            output += f"{setting} \n"
        elif isinstance(setting, list):
            setting = [str(i) for i in setting]
            output += " ".join(setting) + " \n"
        else:
            raise SysfsInterfaceException(f"virtsource value {setting} has wrong type ({type(setting)})")

    wait_for_state("idle", 3.0)

    with open(sysfs_path/"virtual_converter_settings", "w") as file:
        file.write(output)


def read_virtual_converter_settings() -> list:
    """Retrieve the virtual-converter settings from the PRU core.

    The pru-algorithm uses these settings to configure emulator.

    """
    with open(sysfs_path/"virtual_converter_settings", "r") as f:
        settings = f.read().rstrip()
    int_settings = [int(x) for x in settings.split()]
    return int_settings


def write_virtual_harvester_settings(settings: list) -> NoReturn:
    """Sends the settings to the PRU core.

    The pru-algorithm uses these settings to configure emulator.

    """
    logger.debug(f"Writing virtual harvester to sysfs_interface, first value is {settings[0]}")
    output = ""
    for setting in settings:
        if isinstance(setting, int):
            output += f"{setting} \n"
        else:
            raise SysfsInterfaceException(f"virtual harvester value {setting} has wrong type ({type(setting)})")

    wait_for_state("idle", 3.0)
    with open(sysfs_path/"virtual_harvester_settings", "w") as file:
        file.write(output)


def read_virtual_harvester_settings() -> list:
    """Retrieve the settings from the PRU core.

    The  pru-algorithm uses these settings to configure emulator.

    """
    with open(sysfs_path/"virtual_harvester_settings", "r") as f:
        settings = f.read().rstrip()
    int_settings = [int(x) for x in settings.split()]
    return int_settings


def write_pru_msg(msg_type: int, values: list) -> NoReturn:
    """
    :param msg_type:
    :param values:
    """
    if (not isinstance(msg_type, int)) or (msg_type < 0) or (msg_type > 255):
        raise SysfsInterfaceException(f"pru_msg-type has invalid type, "
                                      f"expected u8 for type (={type(msg_type)}) "
                                      f"and content (={msg_type})")

    if isinstance(values, (int, float)):
        # catch all single ints and floats
        values = [int(values), 0]
    elif not isinstance(values, list):
        raise ValueError(f"Outgoing msg to pru should have been list but is {values}")

    for value in values:
        if (not isinstance(value, int)) or (value < 0) or (value >= 2**32):
            raise SysfsInterfaceException(f"pru_msg-value has invalid type, "
                                          f"expected u32 for type (={type(value)}) and content (={value})")

    with open(sysfs_path/"pru_msg_box", "w") as file:
        file.write(f"{msg_type} {values[0]} {values[1]}")


def read_pru_msg() -> tuple:
    """
    Returns:
    """
    with open(sysfs_path/"pru_msg_box", "r") as f:
        message = f.read().rstrip()
    msg_parts = [int(x) for x in message.split()]
    if len(msg_parts) < 2:
        raise SysfsInterfaceException(f"pru_msg was too short")
    return msg_parts[0], msg_parts[1:]


prog_attribs = ["protocol", "datarate", "pin_tck", "pin_tdio", "pin_tdo", "pin_tms"]


def write_programmer_ctrl(protocol: str, datarate: int,
                          pin_tck: int, pin_tdio: int,
                          pin_tdo: int = 0, pin_tms: int = 0
                          ):
    if ("jtag" in protocol.lower()) and ((pin_tdo < 1) or (pin_tms < 1)):
        raise SysfsInterfaceException(f"jtag needs 4 pins defined")
    parameters = [protocol, datarate, pin_tck, pin_tdio, pin_tdo, pin_tms]
    for parameter in parameters[1:]:
        if (parameter < 0) or (parameter >= 2**32):
            raise SysfsInterfaceException(f"at least one parameter out of u32-bounds, value={parameter}")
    for _iter, attribute in enumerate(prog_attribs):
        with open(sysfs_path / "programmer" / attribute, "w") as file:
            logger.debug(f"[sysfs] set programmer/{attribute} = '{parameters[_iter]}'")
            file.write(str(parameters[_iter]))


def read_programmer_ctrl() -> list:
    parameters = []
    for attribute in prog_attribs:
        with open(sysfs_path/"programmer"/attribute, "r") as file:
            parameters.append(file.read().rstrip())
    return parameters


def write_programmer_datasize(value: int) -> NoReturn:
    with open(sysfs_path / "programmer/datasize", "w") as file:
        file.write(str(value))


def start_programmer() -> NoReturn:
    with open(sysfs_path / "programmer/state", "w") as file:
        file.write("start")
    # force a pru-reset to jump into programming routine
    set_stop(force=True)


def check_programmer() -> str:
    with open(sysfs_path / "programmer/state", "r") as file:
        return file.read().rstrip()


attribs = ["mode", "state", "n_buffers", "buffer_period_ns",
           "samples_per_buffer", "mem_address", "mem_size"]


def get_mode() -> str:
    with open(sysfs_path/"mode", "r") as f:
        return str(f.read().rstrip())


def get_state() -> str:
    with open(sysfs_path/"state", "r") as f:
        return str(f.read().rstrip())


def get_n_buffers() -> int:
    with open(sysfs_path/"n_buffers", "r") as f:
        return int(f.read().rstrip())


def get_buffer_period_ns() -> int:
    with open(sysfs_path/"buffer_period_ns", "r") as f:
        return int(f.read().rstrip())


def get_samples_per_buffer() -> int:
    with open(sysfs_path/"samples_per_buffer", "r") as f:
        return int(f.read().rstrip())


def get_mem_address() -> int:
    with open(sysfs_path/"memory/address", "r") as f:
        return int(f.read().rstrip())


def get_mem_size() -> int:
    with open(sysfs_path/"memory/size", "r") as f:
        return int(f.read().rstrip())
