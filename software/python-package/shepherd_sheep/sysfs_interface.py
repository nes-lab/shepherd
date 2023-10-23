"""
shepherd.sysfs_interface
~~~~~
Provides convenience functions for interacting with the sysfs interface
provided by the shepherd kernel module


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import subprocess
import sys
import time
from pathlib import Path

from pydantic import validate_call
from shepherd_core import CalibrationEmulator
from shepherd_core.data_models.content.virtual_harvester import HarvesterPRUConfig
from shepherd_core.data_models.content.virtual_source import ConverterPRUConfig

from .logger import log


class SysfsInterfaceError(Exception):
    pass


# dedicated sampling modes
# - _adc_read - modes are used per rpc (currently to calibrate the hardware)
# TODO: what is with "None"?
shepherd_modes = {
    "harvester",
    "hrv_adc_read",
    "emulator",
    "emu_adc_read",
    "debug",
}


def flatten_list(dl: list) -> list:
    """small helper FN to convert (multi-dimensional) lists to 1D list

    Args:
        dl: (multi-dimensional) lists
    Returns:
        1D list
    """
    if isinstance(dl, list):
        if len(dl) < 1:
            return dl
        if len(dl) == 1:
            if isinstance(dl[0], list):
                return flatten_list(dl[0])
            return dl
        if isinstance(dl[0], list):
            return flatten_list(dl[0]) + flatten_list(dl[1:])
        return [dl[0], *flatten_list(dl[1:])]
    return [dl]


def load_kernel_module() -> None:
    _try = 6
    while _try > 0:
        ret = subprocess.run(
            ["/usr/sbin/modprobe", "-a", "shepherd"],  # noqa: S603
            timeout=60,
            check=False,
        ).returncode
        if ret == 0:
            log.debug("Activated shepherd kernel module")
            time.sleep(3)
            return
        _try -= 1
        time.sleep(1)
    raise SystemError("Failed to load shepherd kernel module.")


def remove_kernel_module() -> None:
    _try = 6
    while _try > 0:
        ret = subprocess.run(
            ["/usr/sbin/modprobe", "-rf", "shepherd"],  # noqa: S603
            timeout=60,
            capture_output=True,
            check=False,
        ).returncode
        if ret == 0:
            log.debug("Deactivated shepherd kernel module")
            time.sleep(1)
            return
        _try -= 1
        time.sleep(1)
    raise SystemError("Failed to unload shepherd kernel module.")


def reload_kernel_module() -> None:
    remove_kernel_module()
    load_kernel_module()


def check_sys_access(iteration: int = 1) -> None:
    iter_max: int = 5
    try:  # test for correct usage -> fail early!
        get_mode()
    except FileNotFoundError:
        try:
            if iteration > iter_max:
                sys.exit(1)
            log.warning(
                "Failed to access sysFS -> "
                "will try to activate shepherd kernel module (attempt %d/%d)",
                iteration,
                iter_max,
            )
            load_kernel_module()
            check_sys_access(iteration + 1)
        except FileNotFoundError:
            log.error(
                "RuntimeError: Failed to access sysFS -> "
                "make sure shepherd kernel module is active!",
            )
            sys.exit(1)
    except PermissionError:
        log.error(
            "RuntimeError: Failed to access sysFS -> "
            "run shepherd-sheep with 'sudo'!",
        )
        sys.exit(1)


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
            raise SysfsInterfaceError(
                f"timed out waiting for state { wanted_state } - "
                f"state is { current_state }",
            )

        time.sleep(0.1)


def set_start(start_time: float | int | None = None) -> True:  # noqa: PYI041
    """Starts shepherd.

    Writes 'start' to the 'state' sysfs attribute in order to transition from
    'idle' to 'running' state. Optionally allows to start at a later point in
    time, transitioning shepherd to 'armed' state.

    Args:
        start_time (int): Desired start time in unix time
    """
    current_state = get_state()
    log.debug("current state of shepherd kernel module: %s", current_state)
    if current_state != "idle":
        raise SysfsInterfaceError(f"Cannot start from state { current_state }")

    try:
        with Path("/sys/shepherd/state").open("w", encoding="utf-8") as f:
            if isinstance(start_time, float):
                start_time = int(start_time)
            if isinstance(start_time, int):
                log.debug("writing start-time = %d to sysfs", start_time)
                f.write(f"{start_time}")
            else:  # unknown type
                log.debug("writing 'start' to sysfs")
                f.write("start")
    except OSError:
        log.error("Failed to write 'Start' to sysfs")
        return False
    return True


def set_stop(force: bool = False) -> None:
    """Stops shepherd.

    Writes 'stop' to the 'state' sysfs attribute in order to transition from
    any state to 'idle'.
    """
    if not force:
        current_state = get_state()
        if current_state != "running":
            raise SysfsInterfaceError(f"Cannot stop from state { current_state }")

    with Path("/sys/shepherd/state").open("w", encoding="utf-8") as f:
        f.write("stop")


def write_mode(mode: str, force: bool = False) -> None:
    """Sets the shepherd mode.

    Sets shepherd mode by writing corresponding string to the 'mode' sysfs
    attribute.

    :param mode: (str) Target mode. Must be one of harvester, emulator or debug
    :param force:
    """
    if mode not in shepherd_modes:
        raise SysfsInterfaceError("invalid value for mode")
    if force:
        set_stop(force=True)
        wait_for_state("idle", 5)
    elif get_state() != "idle":
        raise SysfsInterfaceError(
            f"Cannot set mode when shepherd is { get_state() }",
        )

    log.debug("sysfs/mode: '%s'", mode)
    with Path("/sys/shepherd/mode").open("w", encoding="utf-8") as f:
        f.write(mode)


@validate_call
def write_dac_aux_voltage(
    voltage: float | str | None,
    cal_emu: CalibrationEmulator | None = None,
) -> None:
    """Sends the auxiliary voltage (dac channel B) to the PRU core.

    Args:
        :param voltage: desired voltage in volt
        :param cal_emu: optional set to convert volt to raw
    """
    if (voltage is None) or (voltage is False):
        voltage = 0.0
    elif (voltage is True) or (isinstance(voltage, str) and "main" in voltage.lower()):
        # set bit 20 (during pru-reset) and therefore link both adc-channels
        write_dac_aux_voltage_raw(0, ch_link=True)
        return
    elif isinstance(voltage, str) and "buffer" in voltage.lower():
        # set bit 21 (during pru-reset) and therefore output
        # intermediate (storage cap) voltage on second channel
        write_dac_aux_voltage_raw(0, cap_out=True)
        log.warning(
            "Second DAC-Channel puts out intermediate emulation voltage (@Cap) "
            "-> this might break realtime",
        )
        return

    if voltage < 0.0:
        raise SysfsInterfaceError(f"sending voltage with negative value: {voltage}")
    if voltage > 5.0:
        raise SysfsInterfaceError(f"sending voltage above limit of 5V: {voltage}")
    if not cal_emu:
        cal_emu = CalibrationEmulator()
    output = int(cal_emu.dac_V_A.si_to_raw(voltage))

    log.debug(
        "Set voltage of supply for auxiliary Target to %.3f V (raw=%d)",
        voltage,
        output,
    )
    # TODO: currently only an assumption that it is for emulation, could also be for harvesting
    write_dac_aux_voltage_raw(output)


def write_dac_aux_voltage_raw(
    voltage_raw: int,
    ch_link: bool = False,
    cap_out: bool = False,
) -> None:
    """Sends the auxiliary voltage (dac channel B) to the PRU core.

    Args:
        cap_out: aux will output cap-voltage of vsrc
        ch_link: switch both dac-channels
        voltage_raw: desired voltage as raw int for DAC
    """
    if voltage_raw >= (2**16):
        log.info(
            "DAC: sending raw-voltage above possible limit of 16bit-value, will limit",
        )
        voltage_raw = min(voltage_raw, 2**16 - 1)
    voltage_raw |= int(ch_link) << 20
    voltage_raw |= int(cap_out) << 21
    with Path("/sys/shepherd/dac_auxiliary_voltage_raw").open(
        "w",
        encoding="utf-8",
    ) as f:
        log.debug("Sending raw auxiliary voltage (dac channel B): %d", voltage_raw)
        f.write(str(voltage_raw))


def read_dac_aux_voltage(cal_emu: CalibrationEmulator | None = None) -> float:
    """Reads the auxiliary voltage (dac channel B) from the PRU core.

    Args:
        cal_emu: dict with offset/gain

    Returns:
        aux voltage
    """
    value_raw = read_dac_aux_voltage_raw()
    if not cal_emu:
        cal_emu = CalibrationEmulator()
    return cal_emu.dac_V_A.raw_to_si(value_raw)


def read_dac_aux_voltage_raw() -> int:
    """Reads the auxiliary voltage (dac channel B) to the PRU core.

    Args:

    Returns: voltage as dac_raw
    """
    with Path("/sys/shepherd/dac_auxiliary_voltage_raw").open(encoding="utf-8") as f:
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
        raise SysfsInterfaceError(
            f"sending calibration with negative ADC-C-gain: {cal_pru['adc_current_gain']}",
        )
    if cal_pru["adc_voltage_gain"] < 0:
        raise SysfsInterfaceError(
            f"sending calibration with negative ADC-V-gain: {cal_pru['adc_voltage_gain']}",
        )
    if cal_pru["dac_voltage_gain"] < 0:
        raise SysfsInterfaceError(
            f"sending calibration with negative DAC-gain: {cal_pru['dac_voltage_gain']}",
        )
    wait_for_state("idle", 3.0)

    with Path("/sys/shepherd/calibration_settings").open("w", encoding="utf-8") as f:
        output = (
            f"{int(cal_pru['adc_current_gain'])} {int(cal_pru['adc_current_offset'])} \n"
            f"{int(cal_pru['adc_voltage_gain'])} {int(cal_pru['adc_voltage_offset'])} \n"
            f"{int(cal_pru['dac_voltage_gain'])} {int(cal_pru['dac_voltage_offset'])}"
        )
        log.debug("Sending calibration settings:\n%s", output)
        f.write(output)


def read_calibration_settings() -> (
    dict
):  # more precise dict[str, int], trouble with py3.6
    """Retrieve the calibration settings from the PRU core.

    The virtual-source algorithms use adc measurements and dac-output

    """
    with Path("/sys/shepherd/calibration_settings").open(encoding="utf-8") as f:
        settings = f.read().rstrip()

    int_settings = [int(x) for x in settings.split()]
    return {
        "adc_current_gain": int_settings[0],
        "adc_current_offset": int_settings[1],
        "adc_voltage_gain": int_settings[2],
        "adc_voltage_offset": int_settings[3],
        "dac_voltage_gain": int_settings[4],
        "dac_voltage_offset": int_settings[5],
    }


@validate_call
def write_virtual_converter_settings(settings: ConverterPRUConfig) -> None:
    """Sends the virtual-converter settings to the PRU core.

    The pru-algorithm uses these settings to configure emulator.

    """
    settings = list(settings.model_dump().values())
    log.debug(
        "Writing virtual converter to sysfs_interface, first values are %s",
        settings[0:3],
    )

    output = ""
    for setting in settings:
        if isinstance(setting, int):
            output += f"{setting} \n"
        elif isinstance(setting, list):
            _set = flatten_list(setting)
            _set = [str(i) for i in _set]
            output += " ".join(_set) + " \n"
        else:
            raise SysfsInterfaceError(
                f"virtual-converter value {setting} has wrong type ({type(setting)})",
            )

    wait_for_state("idle", 3.0)
    with Path("/sys/shepherd/virtual_converter_settings").open(
        "w",
        encoding="utf-8",
    ) as file:
        file.write(output)


def read_virtual_converter_settings() -> list:
    """Retrieve the virtual-converter settings from the PRU core.

    The pru-algorithm uses these settings to configure emulator.

    """
    with Path("/sys/shepherd/virtual_converter_settings").open(encoding="utf-8") as f:
        settings = f.read().rstrip()
    return [int(x) for x in settings.split()]


@validate_call
def write_virtual_harvester_settings(settings: HarvesterPRUConfig) -> None:
    """Sends the settings to the PRU core.

    The pru-algorithm uses these settings to configure emulator.

    """
    settings = list(settings.model_dump().values())
    log.debug(
        "Writing virtual harvester to sysfs_interface, first values are %s",
        settings[0:3],
    )
    output = ""
    for setting in settings:
        if isinstance(setting, int):
            output += f"{setting} \n"
        else:
            raise SysfsInterfaceError(
                f"virtual harvester value {setting} has wrong type ({type(setting)})",
            )

    wait_for_state("idle", 3.0)
    with Path("/sys/shepherd/virtual_harvester_settings").open(
        "w",
        encoding="utf-8",
    ) as file:
        file.write(output)


def read_virtual_harvester_settings() -> list:
    """Retrieve the settings from the PRU core.

    The  pru-algorithm uses these settings to configure emulator.

    """
    with Path("/sys/shepherd/virtual_harvester_settings").open(encoding="utf-8") as f:
        settings = f.read().rstrip()
    return [int(x) for x in settings.split()]


def write_pru_msg(msg_type: int, values: list | float | int) -> None:  # noqa: PYI041
    """
    :param msg_type:
    :param values:
    """
    if (not isinstance(msg_type, int)) or (msg_type < 0) or (msg_type > 255):
        raise SysfsInterfaceError(
            f"pru_msg-type has invalid type, "
            f"expected u8 for type (={type(msg_type)}) "
            f"and content (={msg_type})",
        )

    if isinstance(values, int | float):
        # catch all single ints and floats
        values = [int(values), 0]
    elif not isinstance(values, list):
        raise ValueError(f"Outgoing msg to pru should have been list but is {values}")

    for value in values:
        if (not isinstance(value, int)) or (value < 0) or (value >= 2**32):
            raise SysfsInterfaceError(
                f"pru_msg-value has invalid type, "
                f"expected u32 for type (={type(value)}) and content (={value})",
            )

    with Path("/sys/shepherd/pru_msg_box").open("w", encoding="utf-8") as file:
        file.write(f"{msg_type} {values[0]} {values[1]}")


def read_pru_msg() -> tuple[int, list[int]]:
    """
    Returns:
    """
    with Path("/sys/shepherd/pru_msg_box").open(encoding="utf-8") as f:
        message = f.read().rstrip()
    msg_parts = [int(x) for x in message.split()]
    if len(msg_parts) < 2:
        raise SysfsInterfaceError("pru_msg was too short")
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
) -> None:
    # check for validity
    pin_list = [pin_tck, pin_tdio, pin_dir_tdio, pin_tdo, pin_tms, pin_dir_tms]
    pin_set = set(pin_list)

    if sum([pin > 0 for pin in pin_list[0:3]]) < 3:
        raise ValueError(
            "the first 3 programmer pins (tck, tdio, dir_tdio) have to be set!",
        )
    if sum([pin > 0 for pin in pin_list]) != sum([pin > 0 for pin in pin_set]):
        raise ValueError("all programming pins need unique pin-numbers!")
    if datarate == 0 or datarate > 1_000_000:
        raise ValueError("Programming datarate must be within: 0 < datarate < 1 MB/s!")

    # processing
    args = locals()
    log.debug("set programmerCTRL")
    prog_path = Path("/sys/shepherd/programmer")
    for num, attribute in enumerate(prog_attribs):
        value = args[attribute]
        if value is None:
            continue
        if num > 0 and ((value < 0) or (value >= 2**32)):
            raise SysfsInterfaceError(
                f"at least one parameter out of u32-bounds, value={value}",
            )
        with (prog_path / attribute).open(
            "w",
            encoding="utf-8",
        ) as file:
            log.debug("\t%s = '%s'", attribute, value)
            file.write(str(value))


def read_programmer_ctrl() -> list:
    parameters = []
    prog_path = Path("/sys/shepherd/programmer")
    for attribute in prog_attribs:
        with (prog_path / attribute).open(encoding="utf-8") as file:
            parameters.append(file.read().rstrip())
    return parameters


def write_programmer_datasize(value: int) -> None:
    with Path("/sys/shepherd/programmer/datasize").open("w", encoding="utf-8") as file:
        file.write(str(value))


def start_programmer() -> None:
    with Path("/sys/shepherd/programmer/state").open("w", encoding="utf-8") as file:
        file.write("start")
    # force a pru-reset to jump into programming routine
    set_stop(force=True)


def check_programmer() -> str:
    with Path("/sys/shepherd/programmer/state").open(encoding="utf-8") as file:
        return file.read().rstrip()


pru0_firmwares = [
    "am335x-pru0-shepherd-fw",
    "am335x-pru0-programmer-SWD-fw",
    "am335x-pru0-programmer-SBW-fw",
]


def load_pru0_firmware(value: str = "shepherd") -> None:
    """Swap firmwares
    NOTE: current kernel 4.19 (or kernel module code) locks up rproc-sysfs
    WORKAROUND: catch lockup, restart shp-module until successful

    Args:
        value: unique part of valid file-name like shepherd, swd, sbw (not case sensitive)
    """
    request = pru0_firmwares[0]  # default
    for firmware in pru0_firmwares:
        if value.lower() in firmware.lower():
            request = firmware
    log.debug("Will set pru0-firmware to '%s'", request)
    _count = 1
    while _count < 6:
        try:
            with Path("/sys/shepherd/pru0_firmware").open(
                "w",
                encoding="utf-8",
            ) as file:
                file.write(request)
            time.sleep(2)
            with Path("/sys/shepherd/pru0_firmware").open(encoding="utf-8") as file:
                result = file.read().rstrip()
            if result == request:
                return
            log.error(
                "Requested PRU-FW (%s) was not set (is '%s')",
                request,
                result,
            )
        except OSError:  # noqa: PERF203
            log.warning(
                "PRU-Driver is locked up (during pru-fw change)"
                " -> will restart kernel-module (n=%d)",
                _count,
            )
            reload_kernel_module()
            _count += 1
    raise OSError(
        "PRU-Driver still locked up (during pru-fw change)"
        " -> consider restarting node",
    )


def pru0_firmware_is_default() -> bool:
    _count = 1
    while _count < 6:
        try:
            with Path("/sys/shepherd/pru0_firmware").open(encoding="utf-8") as file:
                return file.read().rstrip() in pru0_firmwares[0]
        except OSError:  # noqa: PERF203
            log.warning(
                "PRU-Driver is locked up (during pru-fw read)"
                " -> will restart kernel-module (n=%d)",
                _count,
            )
            reload_kernel_module()
            _count += 1
    raise OSError(
        "PRU-Driver still locked up (during pru-fw read)"
        " -> consider restarting node",
    )


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
    with Path("/sys/shepherd/mode").open(encoding="utf-8") as f:
        return str(f.read().rstrip())


def get_state() -> str:
    with Path("/sys/shepherd/state").open(encoding="utf-8") as f:
        return str(f.read().rstrip())


def get_n_buffers() -> int:
    with Path("/sys/shepherd/n_buffers").open(encoding="utf-8") as f:
        return int(f.read().rstrip())


def get_buffer_period_ns() -> int:
    with Path("/sys/shepherd/buffer_period_ns").open(encoding="utf-8") as f:
        return int(f.read().rstrip())


def get_samples_per_buffer() -> int:
    with Path("/sys/shepherd/samples_per_buffer").open(encoding="utf-8") as f:
        return int(f.read().rstrip())


def get_mem_address() -> int:
    with Path("/sys/shepherd/memory/address").open(encoding="utf-8") as f:
        return int(f.read().rstrip())


def get_mem_size() -> int:
    with Path("/sys/shepherd/memory/size").open(encoding="utf-8") as f:
        return int(f.read().rstrip())
