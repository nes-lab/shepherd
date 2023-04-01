"""
shepherd.sysfs_interface
~~~~~
Provides convenience functions for interacting with the sysfs interface
provided by the shepherd kernel module


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import logging
import sys
import time
from pathlib import Path
from typing import Optional
from typing import Union

from . import calibration_default
from .calibration import CalibrationData

logger = logging.getLogger("shp.interface")
sysfs_path = Path("/sys/shepherd")


class SysfsInterfaceException(Exception):
    pass


# dedicated sampling modes
# - _adc_read - modes are used per rpc (currently to calibrate the hardware)
# TODO: what is with "None"?
shepherd_modes = [
    "harvester",
    "hrv_adc_read",
    "emulator",
    "emu_adc_read",
    "debug",
]


def check_sys_access() -> None:
    try:  # test for correct usage -> fail early!
        get_mode()
    except FileNotFoundError:
        logger.error(
            "RuntimeError: Failed to access sysFS -> is the kernel module loaded?",
        )
        sys.exit(1)
    except PermissionError:
        logger.error(
            "RuntimeError: Failed to access sysFS -> is shepherd-sheep run with 'sudo'?",
        )
        sys.exit(1)
    # TODO: if this (log.error & exit) behaves ok it could replace most "raise Errors" in code


def wait_for_state(wanted_state: str, timeout: float) -> float:
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
                f"state is { current_state }",
            )

        time.sleep(0.1)


def set_start(start_time: Union[float, int, None] = None) -> None:
    """Starts shepherd.

    Writes 'start' to the 'state' sysfs attribute in order to transition from
    'idle' to 'running' state. Optionally allows to start at a later point in
    time, transitioning shepherd to 'armed' state.

    Args:
        start_time (int): Desired start time in unix time
    """
    current_state = get_state()
    logger.debug("current state of shepherd kernel module: %s", current_state)
    if current_state != "idle":
        raise SysfsInterfaceException(f"Cannot start from state { current_state }")

    with open(sysfs_path / "state", "w") as f:
        if isinstance(start_time, float):
            start_time = int(start_time)
        if isinstance(start_time, int):
            logger.debug("writing start-time = %d to sysfs", start_time)
            f.write(f"{start_time}")
        else:  # unknown type
            logger.debug("writing 'start' to sysfs")
            f.write("start")


def set_stop(force: bool = False) -> None:
    """Stops shepherd.

    Writes 'stop' to the 'state' sysfs attribute in order to transition from
    any state to 'idle'.
    """
    if not force:
        current_state = get_state()
        if current_state != "running":
            raise SysfsInterfaceException(f"Cannot stop from state { current_state }")

    with open(sysfs_path / "state", "w") as f:
        f.write("stop")


def write_mode(mode: str, force: bool = False) -> None:
    """Sets the shepherd mode.

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
            raise SysfsInterfaceException(
                f"Cannot set mode when shepherd is { get_state() }",
            )

    logger.debug("sysfs/mode: '%s'", mode)
    with open(sysfs_path / "mode", "w") as f:
        f.write(mode)


def write_dac_aux_voltage(
    calibration_settings: Optional[CalibrationData],
    voltage: float,
) -> None:
    """Sends the auxiliary voltage (dac channel B) to the PRU core.

    Args:
        :param voltage: desired voltage in volt
        :param calibration_settings: optional set to convert volt to raw
    """
    if (voltage is None) or (voltage is False):
        voltage = 0.0
    elif (voltage is True) or (isinstance(voltage, str) and "main" in voltage.lower()):
        # set bit 20 (during pru-reset) and therefore link both adc-channels
        write_dac_aux_voltage_raw(2**20)
        return
    elif isinstance(voltage, str) and "mid" in voltage.lower():
        # set bit 21 (during pru-reset) and therefore output
        # intermediate (storage cap) voltage on second channel
        write_dac_aux_voltage_raw(2**21)
        logger.warning(
            "Second DAC-Channel puts out intermediate emulation voltage (@Cap) "
            "-> this might break realtime",
        )
        return

    if voltage < 0.0:
        raise SysfsInterfaceException(f"sending voltage with negative value: {voltage}")
    if voltage > 5.0:
        raise SysfsInterfaceException(f"sending voltage above limit of 5V: {voltage}")

    if calibration_settings is None:
        output = calibration_default.dac_voltage_to_raw(voltage)
    else:
        output = calibration_settings.convert_value_to_raw(
            "emulator",
            "dac_voltage_b",
            voltage,
        )

    logger.debug(
        "Set voltage of supply for auxiliary Target to %.3f V (raw=%d)",
        voltage,
        output,
    )
    # TODO: currently only an assumption that it is for emulation, could also be for harvesting
    write_dac_aux_voltage_raw(output)


def write_dac_aux_voltage_raw(voltage_raw: int) -> None:
    """Sends the auxiliary voltage (dac channel B) to the PRU core.

    Args:
        voltage_raw: desired voltage as raw int for DAC
    """
    if voltage_raw >= (2**16):
        logger.info(
            "DAC: sending raw-voltage above possible limit of 16bit-value "
            "-> this might trigger commands",
        )
    with open(sysfs_path / "dac_auxiliary_voltage_raw", "w") as f:
        logger.debug("Sending raw auxiliary voltage (dac channel B): %d", voltage_raw)
        f.write(str(voltage_raw))


def read_dac_aux_voltage(cal_settings: CalibrationData) -> float:
    """Reads the auxiliary voltage (dac channel B) from the PRU core.

    Args:
        cal_settings: dict with offset/gain

    Returns:
        aux voltage
    """
    value_raw = read_dac_aux_voltage_raw()
    if cal_settings is None:
        voltage = calibration_default.dac_raw_to_voltage(value_raw)
    else:
        voltage = cal_settings.convert_raw_to_value(
            "emulator",
            "dac_voltage_b",
            value_raw,
        )
    return voltage


def read_dac_aux_voltage_raw() -> int:
    """Reads the auxiliary voltage (dac channel B) to the PRU core.

    Args:

    Returns: voltage as dac_raw
    """
    with open(sysfs_path / "dac_auxiliary_voltage_raw") as f:
        settings = f.read().rstrip()

    int_settings = [int(x) for x in settings.split()]
    return int_settings[0]


def write_calibration_settings(
    cal_pru: dict,
) -> None:  # more precise dict[str, int], trouble with py3.6
    """Sends the calibration settings to the PRU core.

    The virtual-source algorithms use adc measurements and dac-output

    """
    if cal_pru["adc_current_gain"] < 0:
        raise SysfsInterfaceException(
            f"sending calibration with negative ADC-C-gain: {cal_pru['adc_current_gain']}",
        )
    if cal_pru["adc_voltage_gain"] < 0:
        raise SysfsInterfaceException(
            f"sending calibration with negative ADC-V-gain: {cal_pru['adc_voltage_gain']}",
        )
    if cal_pru["dac_voltage_gain"] < 0:
        raise SysfsInterfaceException(
            f"sending calibration with negative DAC-gain: {cal_pru['dac_voltage_gain']}",
        )
    wait_for_state("idle", 3.0)

    with open(sysfs_path / "calibration_settings", "w") as f:
        output = (
            f"{int(cal_pru['adc_current_gain'])} {int(cal_pru['adc_current_offset'])} \n"
            f"{int(cal_pru['adc_voltage_gain'])} {int(cal_pru['adc_voltage_offset'])} \n"
            f"{int(cal_pru['dac_voltage_gain'])} {int(cal_pru['dac_voltage_offset'])}"
        )
        logger.debug("Sending calibration settings: %s", output)
        f.write(output)


def read_calibration_settings() -> (
    dict
):  # more precise dict[str, int], trouble with py3.6
    """Retrieve the calibration settings from the PRU core.

    The virtual-source algorithms use adc measurements and dac-output

    """
    with open(sysfs_path / "calibration_settings") as f:
        settings = f.read().rstrip()

    int_settings = [int(x) for x in settings.split()]
    cal_pru = {
        "adc_current_gain": int_settings[0],
        "adc_current_offset": int_settings[1],
        "adc_voltage_gain": int_settings[2],
        "adc_voltage_offset": int_settings[3],
        "dac_voltage_gain": int_settings[4],
        "dac_voltage_offset": int_settings[5],
    }
    return cal_pru


def write_virtual_converter_settings(settings: list) -> None:
    """Sends the virtual-converter settings to the PRU core.

    The pru-algorithm uses these settings to configure emulator.

    """
    logger.debug(
        "Writing virtual converter to sysfs_interface, first values are %s",
        settings[0:3],
    )

    output = ""
    for setting in settings:
        if isinstance(setting, int):
            output += f"{setting} \n"
        elif isinstance(setting, list):
            setting = [str(i) for i in setting]
            output += " ".join(setting) + " \n"
        else:
            raise SysfsInterfaceException(
                f"virtual-converter value {setting} has wrong type ({type(setting)})",
            )

    wait_for_state("idle", 3.0)

    with open(sysfs_path / "virtual_converter_settings", "w") as file:
        file.write(output)


def read_virtual_converter_settings() -> list:
    """Retrieve the virtual-converter settings from the PRU core.

    The pru-algorithm uses these settings to configure emulator.

    """
    with open(sysfs_path / "virtual_converter_settings") as f:
        settings = f.read().rstrip()
    int_settings = [int(x) for x in settings.split()]
    return int_settings


def write_virtual_harvester_settings(settings: list) -> None:
    """Sends the settings to the PRU core.

    The pru-algorithm uses these settings to configure emulator.

    """
    logger.debug(
        "Writing virtual harvester to sysfs_interface, first values are %s",
        settings[0:3],
    )
    output = ""
    for setting in settings:
        if isinstance(setting, int):
            output += f"{setting} \n"
        else:
            raise SysfsInterfaceException(
                f"virtual harvester value {setting} has wrong type ({type(setting)})",
            )

    wait_for_state("idle", 3.0)
    with open(sysfs_path / "virtual_harvester_settings", "w") as file:
        file.write(output)


def read_virtual_harvester_settings() -> list:
    """Retrieve the settings from the PRU core.

    The  pru-algorithm uses these settings to configure emulator.

    """
    with open(sysfs_path / "virtual_harvester_settings") as f:
        settings = f.read().rstrip()
    int_settings = [int(x) for x in settings.split()]
    return int_settings


def write_pru_msg(msg_type: int, values: Union[list, float, int]) -> None:
    """
    :param msg_type:
    :param values:
    """
    if (not isinstance(msg_type, int)) or (msg_type < 0) or (msg_type > 255):
        raise SysfsInterfaceException(
            f"pru_msg-type has invalid type, "
            f"expected u8 for type (={type(msg_type)}) "
            f"and content (={msg_type})",
        )

    if isinstance(values, (int, float)):
        # catch all single ints and floats
        values = [int(values), 0]
    elif not isinstance(values, list):
        raise ValueError(f"Outgoing msg to pru should have been list but is {values}")

    for value in values:
        if (not isinstance(value, int)) or (value < 0) or (value >= 2**32):
            raise SysfsInterfaceException(
                f"pru_msg-value has invalid type, "
                f"expected u32 for type (={type(value)}) and content (={value})",
            )

    with open(sysfs_path / "pru_msg_box", "w") as file:
        file.write(f"{msg_type} {values[0]} {values[1]}")


def read_pru_msg() -> tuple:
    """
    Returns:
    """
    with open(sysfs_path / "pru_msg_box") as f:
        message = f.read().rstrip()
    msg_parts = [int(x) for x in message.split()]
    if len(msg_parts) < 2:
        raise SysfsInterfaceException("pru_msg was too short")
    return msg_parts[0], msg_parts[1:]


prog_attribs = [
    "target",
    "datarate",
    "pin_tck",
    "pin_tdio",
    "pin_dir_tdio",
    "pin_tdo",
    "pin_tms",
    "pin_dir_tms",
]


def write_programmer_ctrl(
    target: str,
    datarate: int,
    pin_tck: int,
    pin_tdio: int,
    pin_dir_tdio: int,
    pin_tdo: int = 0,
    pin_tms: int = 0,
    pin_dir_tms: int = 0,
):
    args = locals()
    logger.debug("set programmerCTRL")
    for num, attribute in enumerate(prog_attribs):
        value = args[attribute]
        if value is None:
            continue
        if num > 0 and ((value < 0) or (value >= 2**32)):
            raise SysfsInterfaceException(
                f"at least one parameter out of u32-bounds, value={value}",
            )
        with open(sysfs_path / "programmer" / attribute, "w") as file:
            logger.debug("\t%s = '%s'", attribute, value)
            file.write(str(value))


def read_programmer_ctrl() -> list:
    parameters = []
    for attribute in prog_attribs:
        with open(sysfs_path / "programmer" / attribute) as file:
            parameters.append(file.read().rstrip())
    return parameters


def write_programmer_datasize(value: int) -> None:
    with open(sysfs_path / "programmer/datasize", "w") as file:
        file.write(str(value))


def start_programmer() -> None:
    with open(sysfs_path / "programmer/state", "w") as file:
        file.write("start")
    # force a pru-reset to jump into programming routine
    set_stop(force=True)


def check_programmer() -> str:
    with open(sysfs_path / "programmer/state") as file:
        return file.read().rstrip()


pru0_firmwares = [
    "am335x-pru0-shepherd-fw",
    "am335x-pru0-programmer-SWD-fw",
    "am335x-pru0-programmer-SBW-fw",
]


def load_pru0_firmware(value: str = "shepherd") -> None:
    """

    Args:
        value: unique part of valid file-name like shepherd, swd, sbw (not case sensitive)
    """
    choice = pru0_firmwares[0]  # default
    for firmware in pru0_firmwares:
        if value.lower() in firmware.lower():
            choice = firmware
    with open(sysfs_path / "pru0_firmware", "w") as file:
        logger.debug("set pru0-firmware to '%s'", choice)
        file.write(choice)


def pru0_firmware_is_default() -> bool:
    with open(sysfs_path / "pru0_firmware") as file:
        return file.read().rstrip() in pru0_firmwares[0]


attribs = [
    "mode",
    "state",
    "n_buffers",
    "buffer_period_ns",
    "samples_per_buffer",
    "mem_address",
    "mem_size",
]


def get_mode() -> str:
    with open(sysfs_path / "mode") as f:
        return str(f.read().rstrip())


def get_state() -> str:
    with open(sysfs_path / "state") as f:
        return str(f.read().rstrip())


def get_n_buffers() -> int:
    with open(sysfs_path / "n_buffers") as f:
        return int(f.read().rstrip())


def get_buffer_period_ns() -> int:
    with open(sysfs_path / "buffer_period_ns") as f:
        return int(f.read().rstrip())


def get_samples_per_buffer() -> int:
    with open(sysfs_path / "samples_per_buffer") as f:
        return int(f.read().rstrip())


def get_mem_address() -> int:
    with open(sysfs_path / "memory/address") as f:
        return int(f.read().rstrip())


def get_mem_size() -> int:
    with open(sysfs_path / "memory/size") as f:
        return int(f.read().rstrip())
