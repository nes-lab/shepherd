# -*- coding: utf-8 -*-

"""
shepherd.__init__
~~~~~
Provides main API functionality for recording and emulation with shepherd.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""

import logging
import time
import sys
from logging import NullHandler
from pathlib import Path
from contextlib import ExitStack
import invoke
import signal

from shepherd.datalog import LogReader
from shepherd.datalog import LogWriter
from shepherd.datalog import ExceptionRecord
from shepherd.eeprom import EEPROM
from shepherd.eeprom import CapeData
from shepherd.calibration import CalibrationData, cal_channel_list
from shepherd.shepherd_io import ShepherdIOException
from shepherd.shepherd_io import ShepherdIO
from shepherd import commons
from shepherd import sysfs_interface

# Set default logging handler to avoid "No handler found" warnings.
logging.getLogger(__name__).addHandler(NullHandler())

logger = logging.getLogger(__name__)


class Recorder(ShepherdIO):
    """API for recording data with shepherd.

    Provides an easy to use, high-level interface for recording data with
    shepherd. Configures all hardware and initializes the communication
    with kernel module and PRUs.

    Args:
        mode (str): Should be 'harvesting' to record harvesting data TODO: extend with sweep, mppt,
        # TODO: DAC-Calibration would be nice to have, in case of active mppt even both adc-cal
    """

    def __init__(self, mode: str = "harvesting"):
        super().__init__(mode)

    def __enter__(self):
        super().__enter__()

        # Give the PRU empty buffers to begin with
        for i in range(self.n_buffers):
            time.sleep(float(self.buffer_period_ns) / 1e9)
            self.return_buffer(i)
            logger.debug(f"sent empty buffer {i}")

        return self

    def return_buffer(self, index: int):
        """Returns a buffer to the PRU

        After reading the content of a buffer and potentially filling it with
        emulation data, we have to release the buffer to the PRU to avoid it
        running out of buffers.

        Args:
            index (int): Index of the buffer. 0 <= index < n_buffers
        """
        self._return_buffer(index)


class Emulator(ShepherdIO):
    """API for emulating data with shepherd.

    Provides an easy to use, high-level interface for emulating data with
    shepherd. Configures all hardware and initializes the communication
    with kernel module and PRUs.

    Args:
        shepherd_mode:
        initial_buffers: recorded data  # TODO: initial_ is not the best name, is this a yield/generator?
        calibration_recording (CalibrationData): Shepherd calibration data
            belonging to the IV data that is being emulated
        calibration_emulation (CalibrationData): Shepherd calibration data
            belonging to the cape used for emulation
        set_target_io_lvl_conv: Enables or disables the GPIO level converter to targets.
        sel_target_for_io: choose which targets gets the io-connection (serial, swd, gpio) from beaglebone, True = Target A, False = Target B
        sel_target_for_pwr: choose which targets gets the supply with current-monitor, True = Target A, False = Target B
        aux_voltage: Sets, Enables or disables the voltage for the second target, 0.0 or False for Disable, True for linking it to voltage of other Target
        settings_virtsource (dict): Settings which define the behavior of virtcap emulation
    """

    def __init__(self,
                 shepherd_mode: str = "emulation",
                 initial_buffers: list = None,
                 calibration_recording: CalibrationData = None,  # TODO: make clearer that these is "THE RECORDING"
                 calibration_emulation: CalibrationData = None,
                 set_target_io_lvl_conv: bool = False,
                 sel_target_for_io: bool = True,
                 sel_target_for_pwr: bool = True,
                 aux_voltage: float = 0.0,
                 settings_virtsource: dict = None):

        super().__init__(shepherd_mode)
        self._initial_buffers = initial_buffers

        if calibration_emulation is None:
            calibration_emulation = CalibrationData.from_default()
            logger.warning("No emulation calibration data provided - using defaults")
        if calibration_recording is None:
            calibration_recording = CalibrationData.from_default()
            logger.warning("No recording calibration data provided - using defaults")

        self._cal_recording = calibration_recording
        self._cal_emulation = calibration_emulation
        self.send_calibration_settings(calibration_emulation)

        self.set_target_io_level_conv(set_target_io_lvl_conv)
        self.select_main_target_for_io(sel_target_for_io)
        self.select_main_target_for_power(sel_target_for_pwr)
        self.set_aux_target_voltage(calibration_emulation, aux_voltage)

        settings_virtsource = self.check_and_complete_virtsource_settings(settings_virtsource)
        self.send_virtsource_settings(settings_virtsource)

    def __enter__(self):
        super().__enter__()

        # Preload emulator with some data
        for idx, buffer in enumerate(self._initial_buffers):
            time.sleep(float(self.buffer_period_ns) / 1e9)
            self.put_buffer(idx, buffer)

        return self

    def put_buffer(self, index, buffer):

        ts_start = time.time()

        v_gain = 1e6 * self._cal_recording["harvest"]["voltage"]["gain"]
        v_offset = 1e6 * self._cal_recording["harvest"]["voltage"]["offset"]
        i_gain = 1e9 * self._cal_recording["harvest"]["current"]["gain"]
        i_offset = 1e9 * self._cal_recording["harvest"]["current"]["offset"]

        # Convert raw ADC data to SI-Units -> the virtual-source-emulator in PRU expects uV and nV
        voltage_transformed = (buffer.voltage * v_gain + v_offset).astype("u4")
        current_transformed = (buffer.current * i_gain + i_offset).astype("u4")

        self.shared_mem.write_buffer(index, voltage_transformed, current_transformed)
        self._return_buffer(index)

        logger.debug(
            (
                f"Returning buffer #{ index } to PRU took "
                f"{ time.time()-ts_start }"
            )
        )


class ShepherdDebug(ShepherdIO):
    """API for direct access to ADC and DAC.

    For debugging purposes, running the GUI or for retrieving calibration
    values, we need to directly read values from the ADC and set voltage using
    the DAC. This class allows to put the underlying PRUs and kernel module in
    a mode, where they accept 'debug messages' that allow to directly interface
    with the ADC and DAC.
    """

    def __init__(self):
        super().__init__("debug")

    def adc_read(self, channel: str):
        """Reads value from specified ADC channel.

        Args:
            channel (str): Specifies the channel to read from, e.g., 'v_in' for
                harvesting voltage or 'i_out' for load current
        Returns:
            Binary ADC value read from corresponding channel
        """
        if channel.lower() == "v_in":
            channel_no = 0
        elif channel.lower() == "v_out":
            channel_no = 1
        elif channel.lower() in ["a_in", "i_in"]:
            channel_no = 2
        elif channel.lower() in ["a_out", "i_out"]:
            channel_no = 3
        else:
            raise ValueError(f"ADC channel { channel } unknown")

        self._send_msg(commons.MSG_DEP_DBG_ADC, channel_no)

        msg_type, value = self._get_msg()
        if msg_type != commons.MSG_DEP_DBG_ADC:
            raise ShepherdIOException(
                (
                    f"Expected msg type { commons.MSG_DEP_DBG_ADC } "
                    f"got { msg_type }[{ value }]"
                )
            )

        return value

    def dac_write(self, channel: str, value: int):
        """Writes value to specified DAC channel

        Args:
            channel (str): Specifies the channel to write to, e.g., 'current'
                for current channel or 'v' for voltage channel
            value (int): Binary DAC value to be sent to corresponding channel
        """
        # For a mapping of DAC channel to command refer to TI DAC8562T
        # datasheet Table 17
        if channel.lower() in ["current", "i", "a"]:
            dac_command = value
        elif channel.lower() in ["voltage", "v"]:
            # The DAC 'voltage' channel is on channel B
            dac_command = value | (1 << 16)
        else:
            raise ValueError(f"DAC channel { channel } unknown")

        self._send_msg(commons.MSG_DEP_DBG_DAC, dac_command)

    def get_buffer(self, timeout=None):
        raise NotImplementedError("Method not implemented for debugging mode")


def record(
    output: Path,
    mode: str = "harvesting",
    length: float = None,
    force: bool = False,
    no_calib: bool = False,
    harvesting_voltage: float = None,
    load: str = "artificial",
    ldo_voltage: float = None,
    ldo_mode: str = "pre-charge",
    start_time: float = None,
    warn_only: bool = False,
):
    """Starts recording.

    Args:
        output (Path): Path of hdf5 file where IV measurements should be
            stored
        mode (str): 'harvesting' for recording harvesting data, 'load' for
            recording load consumption data.
        length (float): Maximum time duration of emulation in seconds
        force (bool): True to overwrite existing file under output path,
            False to store under different name
        no_calib (bool): True to use default calibration values, False to
            read calibration data from EEPROM
        harvesting_voltage (float): Sets a fixed reference voltage for the
            input of the boost converter. Alternative to MPPT algorithm.
        load (str): Type of load. 'artificial' for dummy, 'node' for sensor
            node
        ldo_voltage (bool): True to pre-charge capacitor before starting
            emulation
        ldo_mode (str): Selects if LDO should just pre-charge capacitor or run
            continuously.
        start_time (float): Desired start time of emulation in unix epoch time
        warn_only (bool): Set true to continue recording after recoverable
            error
    """

    if not output.is_absolute():
        raise ValueError("Output must be absolute path")
    if output.is_dir():
        store_path = output / "rec.h5"
    else:
        store_path = output

    if no_calib:
        calib = CalibrationData.from_default()
    else:
        try:
            with EEPROM() as eeprom:
                calib = eeprom.read_calibration()
        except ValueError:
            logger.warning("Couldn't read calibration from EEPROM (Val). Falling back to default values.")
            calib = CalibrationData.from_default()
        except FileNotFoundError:
            logger.warning("Couldn't read calibration from EEPROM (FS). Falling back to default values.")
            calib = CalibrationData.from_default()

    recorder = Recorder(
        mode=mode,
        load=load,
        harvesting_voltage=harvesting_voltage,
        ldo_voltage=ldo_voltage,
        ldo_mode=ldo_mode,
    )
    log_writer = LogWriter(
        store_path=store_path, calibration_data=calib, mode=mode, force=force
    )
    with ExitStack() as stack:

        stack.enter_context(recorder)
        stack.enter_context(log_writer)

        # in_stream has to be disabled to avoid trouble with pytest
        res = invoke.run("hostname", hide=True, warn=True, in_stream=False)
        log_writer["hostname"] = res.stdout

        recorder.start(start_time, wait_blocking=False)
        if start_time is None:
            recorder.wait_for_start(15)
        else:
            logger.info(f"waiting {start_time - time.time():.2f}s until start")
            recorder.wait_for_start(start_time - time.time() + 15)

        logger.info("shepherd started!")

        def exit_gracefully(signum, frame):
            stack.close()
            sys.exit(0)

        signal.signal(signal.SIGTERM, exit_gracefully)
        signal.signal(signal.SIGINT, exit_gracefully)

        if length is None:
            ts_end = sys.float_info.max
        else:
            ts_end = time.time() + length

        while time.time() < ts_end:
            try:
                idx, buf = recorder.get_buffer()
            except ShepherdIOException as e:
                logger.error(
                    f"ShepherdIOException(ID={e.id}, val={e.value}): {str(e)}"
                )
                err_rec = ExceptionRecord(
                    int(time.time() * 1e9), str(e), e.value
                )
                log_writer.write_exception(err_rec)
                if not warn_only:
                    raise

            log_writer.write_buffer(buf)
            recorder.return_buffer(idx)


def emulate(
    input: Path,
    output: Path = None,
    length: float = None,
    force: bool = False,
    no_calib: bool = False,
    load: str = "artificial",
    ldo_voltage: float = None,
    start_time: float = None,
    virtcap: dict = None,
    warn_only: bool = False,
):
    """Starts emulation.

    Args:
        input (Path): path of hdf5 file containing recorded
            harvesting data
        output (Path): Path of hdf5 file where load measurements should
            be stored
        length (float): Maximum time duration of emulation in seconds
        force (bool): True to overwrite existing file under output,
            False to store under different name
        no_calib (bool): True to use default calibration values, False to
            read calibration data from EEPROM
        load (str): Type of load. 'artificial' for dummy, 'node' for sensor
            node
        ldo_voltage (float): Pre-charge capacitor to this voltage before
            starting emulation
        start_time (float): Desired start time of emulation in unix epoch time
        virtcap (dict): Settings which define the behavior of virtcap emulation
        warn_only (bool): Set true to continue emulation after recoverable
            error
    """

    if no_calib:
        calib = CalibrationData.from_default()
    else:
        try:
            with EEPROM() as eeprom:
                calib = eeprom.read_calibration()
        except ValueError:
            logger.warning("Couldn't read calibration from EEPROM (Val). Falling back to default values.")
            calib = CalibrationData.from_default()
        except FileNotFoundError:
            logger.warning("Couldn't read calibration from EEPROM (FS). Falling back to default values.")
            calib = CalibrationData.from_default()

    if output is not None:
        if not output.is_absolute():
            raise ValueError("Output must be absolute path")
        if output.is_dir():
            store_path = output / "rec.h5"
        else:
            store_path = output

        log_writer = LogWriter(
            store_path=store_path,
            force=force,
            mode="load",
            calibration_data=calib,
        )

    log_reader = LogReader(input, 10_000)

    with ExitStack() as stack:
        if output is not None:
            stack.enter_context(log_writer)

        stack.enter_context(log_reader)

        emu = Emulator(
            calibration_recording=log_reader.get_calibration_data(),
            calibration_emulation=calib,
            initial_buffers=log_reader.read_buffers(end=64),
            ldo_voltage=ldo_voltage,
            load=load,
            settings_virtsource=virtcap,
        )
        stack.enter_context(emu)

        emu.start(start_time, wait_blocking=False)
        if start_time is None:
            emu.wait_for_start(15)
        else:
            logger.info(f"waiting {start_time - time.time():.2f}s until start")
            emu.wait_for_start(start_time - time.time() + 15)

        logger.info("shepherd started!")

        def exit_gracefully(signum, frame):
            stack.close()
            sys.exit(0)

        signal.signal(signal.SIGTERM, exit_gracefully)
        signal.signal(signal.SIGINT, exit_gracefully)

        if length is None:
            ts_end = sys.float_info.max
        else:
            ts_end = time.time() + length

        for hrvst_buf in log_reader.read_buffers(start=64):
            try:
                idx, load_buf = emu.get_buffer(timeout=1)
            except ShepherdIOException as e:
                logger.error(
                    f"ShepherdIOException(ID={e.id}, val={e.value}): {str(e)}"
                )
                if output is not None:
                    err_rec = ExceptionRecord(
                        int(time.time() * 1e9), str(e), e.value
                    )
                    log_writer.write_exception(err_rec)

                if not warn_only:
                    raise

            if output is not None:
                log_writer.write_buffer(load_buf)

            emu.put_buffer(idx, hrvst_buf)

            if time.time() > ts_end:
                break

        # Read all remaining buffers from PRU
        while True:
            try:
                idx, load_buf = emu.get_buffer(timeout=1)
                if output is not None:
                    log_writer.write_buffer(load_buf)
            except ShepherdIOException as e:
                # We're done when the PRU has processed all emulation data buffers
                if e.id == commons.MSG_DEP_ERR_NOFREEBUF:
                    break
                else:
                    if not warn_only:
                        raise
