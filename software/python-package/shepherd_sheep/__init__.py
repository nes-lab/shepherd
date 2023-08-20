"""
shepherd.__init__
~~~~~
Provides main API functionality for harvesting and emulating with shepherd.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import platform
import shutil
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Union

from shepherd_core.data_models import FirmwareDType
from shepherd_core.data_models import ShpModel
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.task import FirmwareModTask
from shepherd_core.data_models.task import HarvestTask
from shepherd_core.data_models.task import ProgrammingTask
from shepherd_core.data_models.task import extract_tasks
from shepherd_core.data_models.task import prepare_task
from shepherd_core.fw_tools import extract_firmware
from shepherd_core.fw_tools import firmware_to_hex
from shepherd_core.fw_tools import modify_uid

from . import sysfs_interface
from .eeprom import EEPROM
from .eeprom import CapeData
from .h5_writer import Writer
from .launcher import Launcher
from .logger import increase_verbose_level
from .logger import log
from .shepherd_debug import ShepherdDebug
from .shepherd_emulator import ShepherdEmulator
from .shepherd_harvester import ShepherdHarvester
from .shepherd_io import ShepherdIOException
from .sysfs_interface import check_sys_access
from .sysfs_interface import flatten_list
from .target_io import TargetIO

__version__ = "0.4.5"

__all__ = [
    "Writer",
    "EEPROM",
    "CapeData",
    "TargetIO",
    "Launcher",
    "ShepherdHarvester",
    "ShepherdEmulator",
    "ShepherdDebug",
    "run_emulator",
    "run_harvester",
    "run_programmer",
    "run_firmware_mod",
    "run_task",
    "ShepherdIOException",
    "log",
    "flatten_list",
]

# NOTE:
#   ExitStack enables a cleaner Exit-Behaviour
#   -> ShepherdIo.exit should always be called


def run_harvester(cfg: HarvestTask) -> None:
    stack = ExitStack()
    increase_verbose_level(cfg.verbose)
    try:
        hrv = ShepherdHarvester(cfg=cfg)
        stack.enter_context(hrv)
        hrv.run()
    except SystemExit:
        pass
    stack.close()


def run_emulator(cfg: EmulationTask) -> None:
    stack = ExitStack()
    increase_verbose_level(cfg.verbose)
    try:
        emu = ShepherdEmulator(cfg=cfg)
        stack.enter_context(emu)
        emu.run()
    except SystemExit:
        pass
    stack.close()


def run_firmware_mod(cfg: FirmwareModTask) -> None:
    increase_verbose_level(cfg.verbose)
    check_sys_access()  # not really needed here
    file_path = extract_firmware(cfg.data, cfg.data_type, cfg.firmware_file)
    if cfg.data_type in [FirmwareDType.path_elf, FirmwareDType.base64_elf]:
        modify_uid(file_path, cfg.custom_id)
        file_path = firmware_to_hex(file_path)
    if file_path.as_posix() != cfg.firmware_file.as_posix():
        shutil.move(file_path, cfg.firmware_file)


def run_programmer(cfg: ProgrammingTask):
    stack = ExitStack()
    increase_verbose_level(cfg.verbose)
    failed = False

    try:
        dbg = ShepherdDebug(use_io=False)
        stack.enter_context(dbg)

        dbg.select_port_for_power_tracking(
            not dbg.convert_target_port_to_bool(cfg.target_port),
        )
        dbg.set_power_state_emulator(True)
        dbg.select_port_for_io_interface(cfg.target_port)
        dbg.set_io_level_converter(True)

        sysfs_interface.write_dac_aux_voltage(cfg.voltage)
        # switching target may restart pru
        sysfs_interface.wait_for_state("idle", 5)

        sysfs_interface.load_pru0_firmware(cfg.protocol)
        dbg.refresh_shared_mem()  # address might have changed

        with open(cfg.firmware_file.resolve(), "rb") as fw:
            try:
                dbg.shared_mem.write_firmware(fw.read())
                target = cfg.mcu_type
                if cfg.simulate:
                    target = "dummy"
                if cfg.mcu_port == 1:
                    sysfs_interface.write_programmer_ctrl(
                        target,
                        cfg.datarate,
                        5,
                        4,
                        10,
                    )
                else:
                    sysfs_interface.write_programmer_ctrl(
                        target,
                        cfg.datarate,
                        8,
                        9,
                        11,
                    )
                log.info("Programmer initialized, will start now")
                sysfs_interface.start_programmer()
            except OSError:
                log.error("OSError - Failed to initialize Programmer")
                failed = True
            except ValueError as xpt:
                log.exception("ValueError: %s", str(xpt))  # noqa: G200
                failed = True

        state = "init"
        while state != "idle" and not failed:
            log.info(
                "Programming in progress,\tpgm_state = %s, shp_state = %s",
                state,
                sysfs_interface.get_state(),
            )
            time.sleep(1)
            state = sysfs_interface.check_programmer()
            if "error" in state:
                log.error(
                    "SystemError - Failed during Programming, p_state = %s",
                    state,
                )
                failed = True
        if failed:
            log.info("Programming - Procedure failed - will exit now!")
        else:
            log.info("Finished Programming!")
        log.debug("\tshepherdState   = %s", sysfs_interface.get_state())
        log.debug("\tprogrammerState = %s", state)
        log.debug("\tprogrammerCtrl  = %s", sysfs_interface.read_programmer_ctrl())
    except SystemExit:
        pass
    stack.close()

    sysfs_interface.load_pru0_firmware("shepherd")
    sys.exit(int(failed))


def run_task(cfg: Union[ShpModel, Path, str]) -> None:
    observer_name = platform.node().strip()
    try:
        wrapper = prepare_task(cfg, observer_name)
        content = extract_tasks(wrapper)
    except ValueError as xcp:
        log.error(  # noqa: G200
            "Task-Set was not usable for this observer '%s', with original error = %s",
            observer_name,
            xcp,
        )
        return

    # TODO: parameters currently not handled:
    #   time_prep, root_path, abort_on_error (but used in emuTask)

    for element in content:
        if element is None:
            continue

        e_dict = element.model_dump(exclude_defaults=True, exclude_unset=True)
        log.debug("Starting run with %s", e_dict)

        if isinstance(element, EmulationTask):
            run_emulator(element)
        elif isinstance(element, HarvestTask):
            run_harvester(element)
        elif isinstance(element, FirmwareModTask):
            run_firmware_mod(element)
        elif isinstance(element, ProgrammingTask):
            run_programmer(element)
        else:
            raise ValueError("Task not implemented: %s", type(element))
