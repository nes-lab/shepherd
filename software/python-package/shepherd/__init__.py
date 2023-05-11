"""
shepherd.__init__
~~~~~
Provides main API functionality for harvesting and emulating with shepherd.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import datetime
import signal
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Optional

import invoke
from shepherd_core import Compression
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.task import ProgrammingTask
from shepherd_core.data_models.testbed import TargetPort

from . import sysfs_interface
from .sheep_writer import ExceptionRecord
from .sheep_writer import SheepWriter
from .eeprom import EEPROM
from .eeprom import CapeData
from .eeprom import retrieve_calibration
from .launcher import Launcher
from .shepherd_debug import ShepherdDebug
from .shepherd_emulator import ShepherdEmulator
from .shepherd_harvester import ShepherdHarvester
from .shepherd_io import ShepherdIOException
from .sysfs_interface import check_sys_access
from .target_io import TargetIO
from .virtual_harvester_config import T_vHrv
from .virtual_harvester_config import VirtualHarvesterConfig
from .virtual_source_config import VirtualSourceConfig
from shepherd_core import get_verbose_level
from .logger import logger

__version__ = "0.4.5"

__all__ = [
    "SheepWriter",
    "EEPROM",
    "CapeData",
    "VirtualSourceConfig",
    "VirtualHarvesterConfig",
    "TargetIO",
    "Launcher",
    "ShepherdHarvester",
    "ShepherdEmulator",
    "ShepherdDebug",
    "run_emulator",
    "run_harvester",
    "ShepherdIOException",
    "logger",
]


def run_harvester(
    output_path: Path,
    duration: Optional[float] = None,
    harvester: Optional[T_vHrv] = None,
    force_overwrite: bool = False,
    use_cal_default: bool = False,
    start_time: Optional[float] = None,
    warn_only: bool = False,
    output_compression: Optional[Compression] = Compression.default,
):
    """Starts recording.
    TODO: refactor the same way as emulator:
        - derive config data-model
        - put most functionality into ShepherdHarvester()
        - remove parametrized CLI (keep only file-based start)

    Args:
        output_path (Path): Path of hdf5 file where IV measurements should be
            stored
        duration (float): Maximum time duration of emulation in seconds
        harvester: name, path or object to a virtual harvester setting
        force_overwrite (bool): True to overwrite existing file under output path,
            False to store under different name
        use_cal_default (bool): True to use default calibration values, False to
            read calibration data from EEPROM
        start_time (float): Desired start time of emulation in unix epoch time
        warn_only (bool): Set true to continue recording after recoverable error
        output_compression: "lzf" recommended, alternatives are "gzip" (level 4) or gzip-level 1-9
    """
    stack = ExitStack()

    def exit_gracefully(*args):  # type: ignore
        stack.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, exit_gracefully)
    signal.signal(signal.SIGINT, exit_gracefully)

    mode = "harvester"
    check_sys_access()
    cal_hrv = retrieve_calibration(use_cal_default).harvester

    if start_time is None:
        start_time = round(time.time() + 10)

    if not output_path.is_absolute():
        output_path = output_path.absolute()
    if output_path.is_dir():
        timestamp = datetime.datetime.fromtimestamp(start_time)
        timestring = timestamp.strftime(
            "%Y-%m-%d_%H-%M-%S",
        )
        # ⤷ closest to ISO 8601, avoids ":"
        store_path = output_path / f"hrv_{timestring}.h5"
    else:
        store_path = output_path

    samples_per_buffer = sysfs_interface.get_samples_per_buffer()
    samplerate_sps = (
        10**9 * samples_per_buffer // sysfs_interface.get_buffer_period_ns()
    )

    recorder = ShepherdHarvester(
        shepherd_mode=mode,
        harvester=harvester,
        cal_=cal_hrv,
    )
    log_writer = SheepWriter(
        file_path=store_path,
        cal_data=cal_hrv,
        mode=mode,
        datatype=recorder.harvester.data["dtype"],  # is there a cleaner way?
        force_overwrite=force_overwrite,
        samples_per_buffer=samples_per_buffer,
        samplerate_sps=samplerate_sps,
        compression=output_compression,
    )

    # performance-critical, <4 reduces chatter during main-loop
    verbose = get_verbose_level() >= 4

    stack.enter_context(recorder)
    stack.enter_context(log_writer)

    # in_stream has to be disabled to avoid trouble with pytest
    res = invoke.run("hostname", hide=True, warn=True, in_stream=False)
    log_writer["hostname"] = "".join(x for x in res.stdout if x.isprintable()).strip()
    log_writer.set_config(recorder.harvester.data)
    log_writer.start_monitors()

    recorder.start(start_time, wait_blocking=False)

    logger.info("waiting %.2f s until start", start_time - time.time())
    recorder.wait_for_start(start_time - time.time() + 15)

    logger.info("shepherd started!")

    if duration is None:
        ts_end = sys.float_info.max
    else:
        ts_end = start_time + duration

    while True:
        try:
            idx, hrv_buf = recorder.get_buffer(verbose=verbose)
        except ShepherdIOException as e:
            logger.warning("Caught an Exception", exc_info=e)
            err_rec = ExceptionRecord(int(time.time() * 1e9), str(e), e.value)
            log_writer.write_exception(err_rec)
            if not warn_only:
                raise RuntimeError("Caught unforgivable ShepherdIO-Exception")
            continue

        if (hrv_buf.timestamp_ns / 1e9) >= ts_end:
            break

        log_writer.write_buffer(hrv_buf)
        recorder.return_buffer(idx, verbose=verbose)


def run_emulator(cfg: EmulationTask):
    stack = ExitStack()

    def exit_gracefully(*args):  # type: ignore
        stack.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, exit_gracefully)
    signal.signal(signal.SIGINT, exit_gracefully)

    emu = ShepherdEmulator(cfg=cfg)
    stack.enter_context(emu)
    emu.run()


def run_programmer(cfg: ProgrammingTask):
    with ShepherdDebug(use_io=False) as sd:
        sd.select_target_for_power_tracking(sel_a=cfg.target_port != TargetPort.A)
        sd.set_power_state_emulator(True)
        sd.select_main_target_for_io(cfg.target_port)
        sd.set_io_level_converter(True)

        sysfs_interface.write_dac_aux_voltage(cfg.voltage)
        # switching target may restart pru
        sysfs_interface.wait_for_state("idle", 5)

        sysfs_interface.load_pru0_firmware(cfg.protocol)
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
                logger.info("Programmer initialized, will start now")
                sysfs_interface.start_programmer()
            except OSError:
                logger.error("OSError - Failed to initialize Programmer")
                failed = True
            except ValueError as xpt:
                logger.exception("ValueError: %s", str(xpt))  # noqa: G200
                failed = True

        state = "init"
        while state != "idle" and not failed:
            logger.info("Programming in progress,\tstate = %s", state)
            time.sleep(1)
            state = sysfs_interface.check_programmer()
            if "error" in state:
                logger.error("SystemError - Failed during Programming")
                failed = True
            # TODO: programmer can hang in "starting", should restart automatically then
        if failed:
            logger.info("Programming - Procedure failed - will exit now!")
        else:
            logger.info("Finished Programming!")
        logger.debug("\tshepherdState   = %s", sysfs_interface.get_state())
        logger.debug("\tprogrammerState = %s", state)
        logger.debug("\tprogrammerCtrl  = %s", sysfs_interface.read_programmer_ctrl())

    sysfs_interface.load_pru0_firmware("shepherd")
    sys.exit(int(failed))
