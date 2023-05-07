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
from shepherd_core.data_models.task import EmulationTask

from . import sysfs_interface
from .calibration import CalibrationData
from .datalog import ExceptionRecord
from .datalog import LogWriter
from .datalog import T_compr
from .datalog_reader import LogReader
from .eeprom import EEPROM
from .eeprom import CapeData
from .eeprom import retrieve_calibration
from .launcher import Launcher
from .logger import get_verbose_level
from .logger import logger
from .logger import set_verbose_level
from .shepherd_debug import ShepherdDebug
from .shepherd_emulator import ShepherdEmulator
from .shepherd_harvester import ShepherdHarvester
from .shepherd_io import ShepherdIOException
from .sysfs_interface import check_sys_access
from .target_io import TargetIO
from .virtual_harvester_config import T_vHrv
from .virtual_harvester_config import VirtualHarvesterConfig
from .virtual_source_config import VirtualSourceConfig

__version__ = "0.4.5"

__all__ = [
    "LogReader",
    "LogWriter",
    "EEPROM",
    "CapeData",
    "CalibrationData",
    "VirtualSourceConfig",
    "VirtualHarvesterConfig",
    "TargetIO",
    "Launcher",
    "set_verbose_level",
    "get_verbose_level",
    "logger",
    "ShepherdHarvester",
    "ShepherdEmulator",
    "ShepherdDebug",
    "run_emulator",
    "run_harvester",
    "ShepherdIOException",
]


def run_harvester(
    output_path: Path,
    duration: Optional[float] = None,
    harvester: Optional[T_vHrv] = None,
    force_overwrite: bool = False,
    use_cal_default: bool = False,
    start_time: Optional[float] = None,
    warn_only: bool = False,
    output_compression: Optional[T_compr] = None,
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
    cal_data = retrieve_calibration(use_cal_default)

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
        calibration=cal_data,
    )
    log_writer = LogWriter(
        file_path=store_path,
        calibration_data=cal_data,
        mode=mode,
        datatype=recorder.harvester.data["dtype"],  # is there a cleaner way?
        force_overwrite=force_overwrite,
        samples_per_buffer=samples_per_buffer,
        samplerate_sps=samplerate_sps,
        output_compression=output_compression,
    )

    # performance-critical, <4 reduces chatter during main-loop
    verbose = get_verbose_level() >= 4

    stack.enter_context(recorder)
    stack.enter_context(log_writer)

    # in_stream has to be disabled to avoid trouble with pytest
    res = invoke.run("hostname", hide=True, warn=True, in_stream=False)
    log_writer["hostname"] = "".join(x for x in res.stdout if x.isprintable()).strip()
    log_writer.embed_config(recorder.harvester.data)
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
