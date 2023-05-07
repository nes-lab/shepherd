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

from . import commons
from . import sysfs_interface
from .calibration import CalibrationData
from .datalog import ExceptionRecord
from .datalog import LogWriter
from .datalog import T_compr
from .datalog_reader import LogReader
from .eeprom import EEPROM
from .eeprom import CapeData
from .launcher import Launcher
from .logger import get_verbose_level
from .logger import logger
from .logger import set_verbose_level
from .shepherd_debug import ShepherdDebug
from .shepherd_emulator import ShepherdEmulator
from .shepherd_io import ShepherdIOException
from .shepherd_harvester import ShepherdHarvester
from .shared_memory import DataBuffer
from .sysfs_interface import check_sys_access
from .target_io import TargetIO
from .virtual_harvester_config import T_vHrv
from .virtual_harvester_config import VirtualHarvesterConfig
from .virtual_source_config import T_vSrc
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
]


def retrieve_calibration(use_default_cal: bool = False) -> CalibrationData:
    if use_default_cal:
        return CalibrationData.from_default()
    else:
        try:
            with EEPROM() as storage:
                return storage.read_calibration()
        except ValueError:
            logger.warning(
                "Couldn't read calibration from EEPROM (ValueError). "
                "Falling back to default values.",
            )
            return CalibrationData.from_default()
        except FileNotFoundError:
            logger.warning(
                "Couldn't read calibration from EEPROM (FileNotFoundError). "
                "Falling back to default values.",
            )
            return CalibrationData.from_default()


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
        )  # closest to ISO 8601, avoid ":"
        store_path = output_path / f"hrv_{timestring}.h5"
    else:
        store_path = output_path

    samples_per_buffer = sysfs_interface.get_samples_per_buffer()
    samplerate_sps = (
        10**9 * samples_per_buffer // sysfs_interface.get_buffer_period_ns()
    )

    recorder = ShepherdHarvester(
        shepherd_mode=mode, harvester=harvester, calibration=cal_data
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

    with ExitStack() as stack:
        stack.enter_context(
            recorder,
        )  # TODO: these are no real contextmanagers, open with "with", do proper exit
        stack.enter_context(log_writer)

        # in_stream has to be disabled to avoid trouble with pytest
        res = invoke.run("hostname", hide=True, warn=True, in_stream=False)
        log_writer["hostname"] = "".join(
            x for x in res.stdout if x.isprintable()
        ).strip()
        log_writer.embed_config(recorder.harvester.data)
        log_writer.start_monitors()

        recorder.start(start_time, wait_blocking=False)

        logger.info("waiting %.2f s until start", start_time - time.time())
        recorder.wait_for_start(start_time - time.time() + 15)

        logger.info("shepherd started!")

        def exit_gracefully(*args):  # type: ignore
            stack.close()
            sys.exit(0)

        signal.signal(signal.SIGTERM, exit_gracefully)
        signal.signal(signal.SIGINT, exit_gracefully)

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


def run_emulator(
    input_path: Path,
    output_path: Optional[Path] = None,
    duration: Optional[float] = None,
    force_overwrite: bool = False,
    use_cal_default: bool = False,
    start_time: Optional[float] = None,
    enable_io: bool = False,
    io_target: str = "A",
    pwr_target: str = "A",
    aux_target_voltage: float = 0.0,
    virtsource: Optional[T_vSrc] = None,
    log_intermediate_voltage: Optional[bool] = None,
    uart_baudrate: Optional[int] = None,
    warn_only: bool = False,
    skip_log_voltage: bool = False,
    skip_log_current: bool = False,
    skip_log_gpio: bool = False,
    output_compression: Optional[T_compr] = None,
):
    """Starts emulator.

    Args:
        :param input_path: [Path] of hdf5 file containing recorded harvesting data
        :param output_path: [Path] of hdf5 file where power measurements should be stored
        :param duration: [float] Maximum time duration of emulation in seconds
        :param force_overwrite: [bool] True to overwrite existing file under output,
            False to store under different name
        :param use_cal_default: [bool] True to use default calibration values, False to
            read calibration data from EEPROM
        :param start_time: [float] Desired start time of emulation in unix epoch time
        :param enable_io: [bool] Enables the GPIO level converter to targets.
        :param io_target: [str] choose which target (A or B) gets the io-connection
            (serial, swd, gpio) from beaglebone
        :param pwr_target: [str] choose which target (A or B) gets the supply with current-monitor,
        :param aux_target_voltage: Sets, Enables or disables the voltage for the second target,
            0.0 or False for Disable, True for linking it to voltage of other Target
        :param virtsource: [VirtualSourceData] Settings which define the behavior of VS emulation
        :param uart_baudrate: [int] setting a value to non-zero will activate uart-logging
        :param log_intermediate_voltage: [bool] do log intermediate node instead of output
        :param warn_only: [bool] Set true to continue emulation after recoverable error
        :param skip_log_voltage: [bool] reduce file-size by omitting this log
        :param skip_log_gpio: [bool] reduce file-size by omitting this log
        :param skip_log_current: [bool] reduce file-size by omitting this log
        :param output_compression: "lzf" recommended, alternatives are
            "gzip" (level 4) or
            gzip-level 1-9
    """
    mode = "emulator"
    check_sys_access()
    cal = retrieve_calibration(use_cal_default)

    if start_time is None:
        start_time = round(time.time() + 10)

    if enable_io is None:
        enable_io = True

    if io_target is None:
        io_target = "A"

    if pwr_target is None:
        pwr_target = "A"

    if aux_target_voltage is None:
        aux_target_voltage = 0.0

    samples_per_buffer = sysfs_interface.get_samples_per_buffer()
    samplerate_sps = (
        10**9 * samples_per_buffer // sysfs_interface.get_buffer_period_ns()
    )

    log_writer: Optional[LogWriter] = None
    if output_path is not None:
        if not output_path.is_absolute():
            output_path = output_path.absolute()
        if output_path.is_dir():
            timestamp = datetime.datetime.fromtimestamp(start_time)
            timestring = timestamp.strftime(
                "%Y-%m-%d_%H-%M-%S",
            )  # closest to ISO 8601, avoid ":"
            store_path = output_path / f"emu_{timestring}.h5"
        else:
            store_path = output_path

        log_writer = LogWriter(
            file_path=store_path,
            force_overwrite=force_overwrite,
            mode=mode,
            datatype="ivsample",
            calibration_data=cal,
            skip_voltage=skip_log_voltage,
            skip_current=skip_log_current,
            skip_gpio=skip_log_gpio,
            samples_per_buffer=samples_per_buffer,
            samplerate_sps=samplerate_sps,
            output_compression=output_compression,
        )

    if isinstance(input_path, str):
        input_path = Path(input_path)
    if input_path is None:
        raise ValueError("No Input-File configured for emulator")
    if not input_path.exists():
        raise ValueError(f"Input-File does not exist ({input_path})")

    # performance-critical, <4 reduces chatter during main-loop
    verbose = get_verbose_level() >= 4

    log_reader = LogReader(input_path, verbose=verbose)
    # TODO: new reader allow to check mode and dtype of recording (should be emu, ivcurves)

    with ExitStack() as stack:
        if log_writer is not None:
            stack.enter_context(log_writer)
            # TODO: these are no real contextmanagers, open with "with", do proper exit
            # add hostname to file
            res = invoke.run("hostname", hide=True, warn=True, in_stream=False)
            log_writer["hostname"] = "".join(
                x for x in res.stdout if x.isprintable()
            ).strip()
            log_writer.start_monitors(uart_baudrate)

        stack.enter_context(log_reader)

        fifo_buffer_size = sysfs_interface.get_n_buffers()
        init_buffers = [
            DataBuffer(voltage=dsv, current=dsc)
            for _, dsv, dsc in log_reader.read_buffers(end_n=fifo_buffer_size)
        ]

        emu = ShepherdEmulator(
            shepherd_mode=mode,  # TODO: this should not be needed anymore
            initial_buffers=init_buffers,
            calibration_recording=log_reader.get_calibration_data(),
            calibration_emulator=cal,
            enable_io=enable_io,
            io_target=io_target,
            pwr_target=pwr_target,
            aux_target_voltage=aux_target_voltage,
            vsource=virtsource,
            log_intermediate_voltage=log_intermediate_voltage,
            infile_vh_cfg=log_reader.get_hrv_config(),
        )
        stack.enter_context(emu)
        if log_writer is not None:
            log_writer.embed_config(emu.vs_cfg.data)
        emu.start(start_time, wait_blocking=False)
        logger.info("waiting %.2f s until start", start_time - time.time())
        emu.wait_for_start(start_time - time.time() + 15)

        logger.info("shepherd started!")

        def exit_gracefully(*args):  # type: ignore
            stack.close()
            sys.exit(0)

        signal.signal(signal.SIGTERM, exit_gracefully)
        signal.signal(signal.SIGINT, exit_gracefully)

        if duration is None:
            ts_end = sys.float_info.max
        else:
            ts_end = start_time + duration

        for _, dsv, dsc in log_reader.read_buffers(start_n=fifo_buffer_size):
            try:
                idx, emu_buf = emu.get_buffer(verbose=verbose)
            except ShepherdIOException as e:
                logger.warning("Caught an Exception", exc_info=e)

                err_rec = ExceptionRecord(int(time.time() * 1e9), str(e), e.value)
                if log_writer is not None:
                    log_writer.write_exception(err_rec)
                if not warn_only:
                    raise RuntimeError("Caught unforgivable ShepherdIO-Exception")
                continue

            if emu_buf.timestamp_ns / 1e9 >= ts_end:
                break

            if log_writer is not None:
                log_writer.write_buffer(emu_buf)

            hrvst_buf = DataBuffer(voltage=dsv, current=dsc)
            emu.return_buffer(idx, hrvst_buf, verbose)

        # Read all remaining buffers from PRU
        while True:
            try:
                idx, emu_buf = emu.get_buffer(verbose=verbose)
                if emu_buf.timestamp_ns / 1e9 >= ts_end:
                    break
                if log_writer is not None:
                    log_writer.write_buffer(emu_buf)
            except ShepherdIOException as e:
                # We're done when the PRU has processed all emulation data buffers
                if e.id_num == commons.MSG_DEP_ERR_NOFREEBUF:
                    break
                else:
                    if not warn_only:
                        raise RuntimeError("Caught unforgivable ShepherdIO-Exception")
