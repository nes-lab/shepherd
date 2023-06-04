"""
shepherd.__init__
~~~~~
Provides main API functionality for harvesting and emulating with shepherd.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import signal
import sys
import time
from contextlib import ExitStack

from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.task import HarvestTask
from shepherd_core.data_models.task import ProgrammingTask

from . import sysfs_interface
from .eeprom import EEPROM
from .eeprom import CapeData
from .h5_writer import Writer
from .launcher import Launcher
from .logger import log
from .shepherd_debug import ShepherdDebug
from .shepherd_emulator import ShepherdEmulator
from .shepherd_harvester import ShepherdHarvester
from .shepherd_io import ShepherdIOException
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
    "ShepherdIOException",
    "log",
]


def context_stack() -> ExitStack:
    stack = ExitStack()

    def exit_gracefully(*args):  # type: ignore
        stack.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, exit_gracefully)
    signal.signal(signal.SIGINT, exit_gracefully)
    return stack


def run_harvester(cfg: HarvestTask) -> None:
    stack = context_stack()
    hrv = ShepherdHarvester(cfg=cfg)
    stack.enter_context(hrv)
    hrv.run()


def run_emulator(cfg: EmulationTask) -> None:
    stack = context_stack()
    emu = ShepherdEmulator(cfg=cfg)
    stack.enter_context(emu)
    emu.run()


def run_programmer(cfg: ProgrammingTask):
    with ShepherdDebug(use_io=False) as sd:
        sd.select_port_for_power_tracking(cfg.target_port)
        sd.set_power_state_emulator(True)
        sd.select_port_for_io_interface(cfg.target_port)
        sd.set_io_level_converter(True)

        sysfs_interface.write_dac_aux_voltage(cfg.voltage)
        # switching target may restart pru
        sysfs_interface.wait_for_state("idle", 5)

        sysfs_interface.load_pru0_firmware(cfg.protocol)
        sd.refresh_shared_mem()  # address might have changed
        failed = False

        with open(cfg.firmware_file, "rb") as fw:
            try:
                sd.shared_mem.write_firmware(fw.read())
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
            log.info("Programming in progress,\tstate = %s", state)
            time.sleep(1)
            state = sysfs_interface.check_programmer()
            if "error" in state:
                log.error("SystemError - Failed during Programming, state = %s", state)
                failed = True
            # TODO: programmer can hang in "starting", should restart automatically then
        if failed:
            log.info("Programming - Procedure failed - will exit now!")
        else:
            log.info("Finished Programming!")
        log.debug("\tshepherdState   = %s", sysfs_interface.get_state())
        log.debug("\tprogrammerState = %s", state)
        log.debug("\tprogrammerCtrl  = %s", sysfs_interface.read_programmer_ctrl())

    sysfs_interface.load_pru0_firmware("shepherd")
    sys.exit(int(failed))
