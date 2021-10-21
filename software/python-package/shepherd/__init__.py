# -*- coding: utf-8 -*-

"""
shepherd.__init__
~~~~~
Provides main API functionality for recording and emulation with shepherd.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import datetime
import logging
import time
import sys
from logging import NullHandler
from pathlib import Path
from contextlib import ExitStack
from typing import NoReturn, Union
import msgpack
import msgpack_numpy
import numpy
import invoke
import signal

from shepherd.shepherd_io import ShepherdIO
from shepherd.virtual_harvester_data import VirtualHarvesterData
from shepherd.virtual_source_data import VirtualSourceData
from shepherd.shepherd_io import ShepherdIOException
from shepherd.datalog import LogReader
from shepherd.datalog import LogWriter
from shepherd.datalog import ExceptionRecord
from shepherd.eeprom import EEPROM
from shepherd.eeprom import CapeData
from shepherd.calibration import CalibrationData
from shepherd.calibration import cal_channel_list
from shepherd import commons
from shepherd import sysfs_interface

# Set default logging handler to avoid "No handler found" warnings.
from shepherd.target_io import TargetIO

logging.getLogger(__name__).addHandler(NullHandler())
logger = logging.getLogger(__name__)
#logging._srcfile = None
#logging.logThreads = 0
#logging.logProcesses = 0


class Recorder(ShepherdIO):
    """API for recording data with shepherd.

    Provides an easy to use, high-level interface for recording data with
    shepherd. Configures all hardware and initializes the communication
    with kernel module and PRUs.

    Args:
        shepherd_mode (str): Should be 'harvesting' to record harvesting data
        harvester: name, path or object to a virtual harvester setting
        # TODO: DAC-Calibration would be nice to have, in case of active mppt even both adc-cal
    """

    def __init__(self,
                 shepherd_mode: str = "harvesting",
                 harvester: Union[dict, str, Path, VirtualHarvesterData] = None,
                 ):
        logger.debug(f"Recorder-Init in {shepherd_mode}-mode")
        self._harvester = harvester
        super().__init__(shepherd_mode)

    def __enter__(self):
        super().__enter__()

        self.set_power_state_emulator(False)
        self.set_power_state_recorder(True)
        self.send_virtual_harvester_settings(self._harvester)

        # Give the PRU empty buffers to begin with
        time.sleep(1)
        for i in range(self.n_buffers):
            time.sleep(0.1 * float(self.buffer_period_ns) / 1e9)  # could be as low as ~ 10us
            self.return_buffer(i, True)

        return self

    def return_buffer(self, index: int, verbose: bool = False):
        """Returns a buffer to the PRU

        After reading the content of a buffer and potentially filling it with
        emulation data, we have to release the buffer to the PRU to avoid it
        running out of buffers.

        :param index: (int) Index of the buffer. 0 <= index < n_buffers
        :param verbose: chatter-prevention, performance-critical computation saver
        """
        self._return_buffer(index)
        if verbose:
            logger.debug(f"Sent empty buffer #{index} to PRU")


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
        aux_target_voltage: Sets, Enables or disables the voltage for the second target, 0.0 or False for Disable, True for linking it to voltage of other Target
        settings_virtsource (dict): Settings which define the behavior of virtual source emulation
    """

    def __init__(self,
                 shepherd_mode: str = "emulation",
                 initial_buffers: list = None,
                 calibration_recording: CalibrationData = None,  # TODO: make clearer that this is "THE RECORDING"
                 calibration_emulation: CalibrationData = None,
                 set_target_io_lvl_conv: bool = False,
                 sel_target_for_io: bool = True,
                 sel_target_for_pwr: bool = True,
                 aux_target_voltage: float = 0.0,
                 settings_virtsource: Union[dict, str, Path, VirtualSourceData] = None,
                 log_intermediate_voltage: bool = None,
                 ):

        logger.debug(f"Emulator-Init in {shepherd_mode}-mode")
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
        self._settings_virtsource = settings_virtsource
        self._log_intermediate_voltage = log_intermediate_voltage

        self._set_target_io_lvl_conv = set_target_io_lvl_conv
        self._sel_target_for_io = sel_target_for_io
        self._sel_target_for_pwr = sel_target_for_pwr
        self._aux_target_voltage = aux_target_voltage

        self._v_gain = 1e6 * self._cal_recording["harvesting"]["adc_voltage"]["gain"]
        self._v_offset = 1e6 * self._cal_recording["harvesting"]["adc_voltage"]["offset"]
        self._i_gain = 1e9 * self._cal_recording["harvesting"]["adc_current"]["gain"]
        self._i_offset = 1e9 * self._cal_recording["harvesting"]["adc_current"]["offset"]

    def __enter__(self):
        super().__enter__()

        self.set_power_state_recorder(False)
        self.set_power_state_emulator(True)

        self.send_virtual_converter_settings(self._settings_virtsource, self._log_intermediate_voltage)
        self.send_calibration_settings(self._cal_emulation)
        self.reinitialize_prus()

        self.set_target_io_level_conv(self._set_target_io_lvl_conv)
        self.select_main_target_for_io(self._sel_target_for_io)
        self.select_main_target_for_power(self._sel_target_for_pwr)
        self.set_aux_target_voltage(self._cal_emulation, self._aux_target_voltage)

        # Preload emulator with data
        time.sleep(1)
        for idx, buffer in enumerate(self._initial_buffers):
            time.sleep(0.1 * float(self.buffer_period_ns) / 1e9)  # could be as low as ~ 10us
            self.return_buffer(idx, buffer, verbose=True)

        return self

    def return_buffer(self, index, buffer, verbose: bool = False):
        if verbose:
            ts_start = time.time()

        # Convert raw ADC data to SI-Units -> the virtual-source-emulator in PRU expects uV and nV
        voltage_transformed = (buffer.voltage * self._v_gain + self._v_offset).astype("u4")
        current_transformed = (buffer.current * self._i_gain + self._i_offset).astype("u4")

        self.shared_mem.write_buffer(index, voltage_transformed, current_transformed)
        self._return_buffer(index)
        if verbose:
            logger.debug(f"Sending emu-buffer #{ index } to PRU took "
                         f"{ round(1e3 * (time.time()-ts_start), 2) } ms")


class ShepherdDebug(ShepherdIO):
    """API for direct access to ADC and DAC.

    For debugging purposes, running the GUI or for retrieving calibration
    values, we need to directly read values from the ADC and set voltage using
    the DAC. This class allows to put the underlying PRUs and kernel module in
    a mode, where they accept 'debug messages' that allow to directly interface
    with the ADC and DAC.
    """
    # offer a default cali for debugging, TODO: maybe also try to read from eeprom
    _cal: CalibrationData = None
    _io: TargetIO = None
    P_in_fW: float = 0.0
    P_out_fW: float = 0.0

    def __init__(self, use_io: bool = True):
        super().__init__("debug")

        if use_io:
            self._io = TargetIO()

        try:
            with EEPROM() as storage:
                storage.read_cape_data()
                self._cal = storage.read_calibration()
        except ValueError:
            logger.warning("Couldn't read calibration from EEPROM (Val). Falling back to default values.")
            self._cal = CalibrationData.from_default()
        except FileNotFoundError:
            logger.warning("Couldn't read calibration from EEPROM (FS). Falling back to default values.")
            self._cal = CalibrationData.from_default()

    def __enter__(self):
        super().__enter__()
        super().set_power_state_recorder(True)
        super().set_power_state_emulator(True)
        super().reinitialize_prus()
        return self

    def adc_read(self, channel: str):
        """Reads value from specified ADC channel.

        Args:
            channel (str): Specifies the channel to read from, e.g., 'v_in' for
                harvesting voltage or 'i_out' for current
        Returns:
            Binary ADC value read from corresponding channel
        """
        if channel.lower() in ["hrv_a_in", "hrv_i_in", "a_in", "i_in"]:
            channel_no = 0
        elif channel.lower() in ["hrv_v_in", "v_in"]:
            channel_no = 1
        elif channel.lower() in ["emu", "emu_a_out", "emu_i_out", "a_out", "i_out"]:
            channel_no = 2
        else:
            raise ValueError(f"ADC channel { channel } unknown")

        super()._send_msg(commons.MSG_DBG_ADC, channel_no)

        msg_type, values = self._get_msg(30)
        if msg_type != commons.MSG_DBG_ADC:
            raise ShepherdIOException(
                    f"Expected msg type { hex(commons.MSG_DBG_ADC) }, "
                    f"but got type={ hex(msg_type) } val={ values }"
                    )
        return values[0]

    def gpi_read(self) -> int:
        """ issues a pru-read of the gpio-registers that monitor target-communication

        Returns: an int with the corresponding bits set
                -> see bit-definition in commons.py
        """
        super()._send_msg(commons.MSG_DBG_GPI, 0)
        msg_type, values = self._get_msg()
        if msg_type != commons.MSG_DBG_GPI:
            raise ShepherdIOException(
                    f"Expected msg type { hex(commons.MSG_DBG_GPI) }, "
                    f"but got type={ hex(msg_type) } val={ values }"
                    )
        return values[0]

    def gp_set_batok(self, value: int):
        super()._send_msg(commons.MSG_DBG_GP_BATOK, value)

    def dac_write(self, channels: int, value: int):
        """Writes value to specified DAC channel, DAC8562

        Args:
            channels: 4 lower bits of int-num control b0: harvest-ch-a, b1: harv-ch-b, b2: emulation-ch-a, b3: emu-ch-b
            value (int): 16 bit raw DAC value to be sent to corresponding channel
        """
        channels = (int(channels) & ((1 << 4) - 1)) << 20
        value = int(value) & ((1 << 16) - 1)
        message = channels | value
        super()._send_msg(commons.MSG_DBG_DAC, message)

    def get_buffer(self, timeout_n: float = None, verbose: bool = False):
        raise NotImplementedError("Method not implemented for debugging mode")

    def dbg_fn_test(self, factor: int, mode: int) -> int:
        super()._send_msg(commons.MSG_DBG_FN_TESTS, [factor, mode])
        msg_type, values = self._get_msg()
        if msg_type != commons.MSG_DBG_FN_TESTS:
            raise ShepherdIOException(
                    f"Expected msg type { hex(commons.MSG_DBG_FN_TESTS) }, but got type={ hex(msg_type) } val={ values }")
        return values[0]*(2**32) + values[1]  # P_out_pW

    def vsource_init(self, vs_settings, cal_settings):
        super().send_virtual_converter_settings(vs_settings)
        super().send_calibration_settings(cal_settings)
        time.sleep(0.5)
        super().start()
        super()._send_msg(commons.MSG_DBG_VSOURCE_INIT, 0)
        msg_type, values = super()._get_msg()  # no data, just a confirmation
        if msg_type != commons.MSG_DBG_VSOURCE_INIT:
            raise ShepherdIOException(
                    f"Expected msg type { hex(commons.MSG_DBG_VSOURCE_INIT) }, but got type={ hex(msg_type) } val={ values }")
        # TEST-SIMPLIFICATION - code below is not part of pru-code
        self.P_in_fW = 0.0
        self.P_out_fW = 0.0
        self._cal = cal_settings

    def vsource_calc_inp_power(self, input_voltage_uV: int, input_current_nA: int) -> int:
        super()._send_msg(commons.MSG_DBG_VSOURCE_P_INP, [int(input_voltage_uV), int(input_current_nA)])
        msg_type, values = self._get_msg()
        if msg_type != commons.MSG_DBG_VSOURCE_P_INP:
            raise ShepherdIOException(
                    f"Expected msg type { hex(commons.MSG_DBG_VSOURCE_P_INP) }, but got type={ hex(msg_type) } val={ values }")
        return values[0]*(2**32) + values[1]  # P_inp_pW

    def vsource_charge(self, input_voltage_uV: int, input_current_nA: int) -> (int, int):
        self._send_msg(commons.MSG_DBG_VSOURCE_CHARGE, [int(input_voltage_uV), int(input_current_nA)])
        msg_type, values = self._get_msg()
        if msg_type != commons.MSG_DBG_VSOURCE_CHARGE:
            raise ShepherdIOException(
                    f"Expected msg type { hex(commons.MSG_DBG_VSOURCE_CHARGE) }, but got type={ hex(msg_type) } val={ values }")
        return values[0], values[1]  # V_store_uV, V_out_dac_raw

    def vsource_calc_out_power(self, current_adc_raw: int) -> int:
        self._send_msg(commons.MSG_DBG_VSOURCE_P_OUT, int(current_adc_raw))
        msg_type, values = self._get_msg()
        if msg_type != commons.MSG_DBG_VSOURCE_P_OUT:
            raise ShepherdIOException(
                    f"Expected msg type { hex(commons.MSG_DBG_VSOURCE_P_OUT) }, but got type={ hex(msg_type) } val={ values }")
        return values[0]*(2**32) + values[1]  # P_out_pW

    def vsource_drain(self, current_adc_raw: int) -> (int, int):
        self._send_msg(commons.MSG_DBG_VSOURCE_DRAIN, int(current_adc_raw))
        msg_type, values = self._get_msg()
        if msg_type != commons.MSG_DBG_VSOURCE_DRAIN:
            raise ShepherdIOException(
                    f"Expected msg type { hex(commons.MSG_DBG_VSOURCE_DRAIN) }, but got type={ hex(msg_type) } val={ values }")
        return values[0], values[1]  # V_store_uV, V_out_dac_raw

    def vsource_update_cap_storage(self) -> int:
        self._send_msg(commons.MSG_DBG_VSOURCE_V_CAP, 0)
        msg_type, values = self._get_msg()
        if msg_type != commons.MSG_DBG_VSOURCE_V_CAP:
            raise ShepherdIOException(
                    f"Expected msg type { hex(commons.MSG_DBG_VSOURCE_V_CAP) }, but got type={ hex(msg_type) } val={ values }")
        return values[0]  # V_store_uV

    def vsource_update_states_and_output(self) -> int:
        self._send_msg(commons.MSG_DBG_VSOURCE_V_OUT, 0)
        msg_type, values = self._get_msg()
        if msg_type != commons.MSG_DBG_VSOURCE_V_OUT:
            raise ShepherdIOException(
                    f"Expected msg type { hex(commons.MSG_DBG_VSOURCE_V_OUT) }, but got type={ hex(msg_type) } val={ values }")
        return values[0]  # V_out_dac_raw

    # TEST-SIMPLIFICATION - code below is also part py-vsource with same interface
    def iterate(self, V_in_uV: int = 0, A_in_nA: int = 0, A_out_nA: int = 0):
        self.vsource_calc_inp_power(V_in_uV, A_in_nA)
        A_out_raw = self._cal.convert_value_to_raw("emulation", "adc_current", A_out_nA * 10**-9)
        self.vsource_calc_out_power(A_out_raw)
        self.vsource_update_cap_storage()
        V_out_raw = self.vsource_update_states_and_output()
        V_out_uV = int(self._cal.convert_raw_to_value("emulation", "dac_voltage_b", V_out_raw) * 10**6)
        self.P_in_fW += V_in_uV * A_in_nA
        self.P_out_fW += V_out_uV * A_out_nA
        return V_out_uV

    @staticmethod
    def is_alive() -> bool:
        """ feedback-fn for RPC-usage to check for connection
        :return: True
        """
        return True

    # all methods below are wrapper for zerorpc - it seems to have trouble with inheritance and runtime inclusion

    @staticmethod
    def set_shepherd_state(state: bool) -> NoReturn:
        if state:
            sysfs_interface.set_start()
        else:
            sysfs_interface.set_stop()

    @staticmethod
    def get_shepherd_state() -> str:
        return sysfs_interface.get_state()

    def set_shepherd_pcb_power(self, state: bool) -> NoReturn:
        self._set_shepherd_pcb_power(state)

    def set_power_recorder(self, state: bool) -> NoReturn:
        self.set_power_state_recorder(state)

    def set_power_emulator(self, state: bool) -> NoReturn:
        self.set_power_state_emulator(state)

    def select_target_for_power_tracking(self, sel_a: bool) -> NoReturn:
        self.select_main_target_for_power(sel_a)

    def select_target_for_io_interface(self, sel_a: bool) -> NoReturn:
        self.select_main_target_for_io(sel_a)

    def set_io_level_converter(self, state) -> NoReturn:
        self.set_target_io_level_conv(state)

    def convert_raw_to_value(self, component: str, channel: str, raw: int) -> float:
        return self._cal.convert_raw_to_value(component, channel, raw)

    def convert_value_to_raw(self, component: str, channel: str, value: float) -> int:
        return self._cal.convert_value_to_raw(component, channel, value)

    def set_gpio_one_high(self, num: int) -> NoReturn:
        if not (self._io is None):
            self._io.one_high(num)
        else:
            logger.debug(f"Error: IO is not enabled in this shepherd-debug-instance")

    def set_power_state_emulator(self, state: bool) -> NoReturn:
        super().set_power_state_emulator(state)

    def set_power_state_recorder(self, state: bool) -> NoReturn:
        super().set_power_state_recorder(state)

    def reinitialize_prus(self) -> NoReturn:
        super().reinitialize_prus()

    @staticmethod
    def set_aux_target_voltage_raw(voltage_raw) -> NoReturn:
        sysfs_interface.write_dac_aux_voltage_raw(voltage_raw)

    def switch_shepherd_mode(self, mode: str) -> str:
        mode_old = sysfs_interface.get_mode()
        sysfs_interface.write_mode(mode, force=True)
        super().reinitialize_prus()
        if "debug" in mode:
            super().start(wait_blocking=True)
        return mode_old

    def sample_emu_cal(self, length_n_buffers: int = 10):
        length_n_buffers = int(min(max(length_n_buffers, 1), 60))

        super().reinitialize_prus()
        time.sleep(0.1)
        for i in range(length_n_buffers+2):  # Fill FIFO
            time.sleep(0.02)
            super()._return_buffer(i)
        time.sleep(0.1)

        base_array = numpy.empty([0], dtype="=u4")
        super().start(wait_blocking=True)
        time.sleep(0.1)
        for i in range(length_n_buffers):  # get Data
            idx, emu_buf = super().get_buffer()
            base_array = numpy.hstack((base_array, emu_buf.current))
        super().reinitialize_prus()
        return msgpack.packb(base_array, default=msgpack_numpy.encode)  # zeroRPC / msgpack can not handle numpy-data without this


def retrieve_calibration(use_default_cal: bool = False) -> CalibrationData:
    if use_default_cal:
        return CalibrationData.from_default()
    else:
        try:
            with EEPROM() as storage:
                return storage.read_calibration()
        except ValueError:
            logger.warning("Couldn't read calibration from EEPROM (ValueError). Falling back to default values.")
            return CalibrationData.from_default()
        except FileNotFoundError:
            logger.warning("Couldn't read calibration from EEPROM (FileNotFoundError). Falling back to default values.")
            return CalibrationData.from_default()


def record(
    output_path: Path,
    mode: str = "harvesting",
    duration: float = None,
    harvester: Union[dict, str, Path, VirtualHarvesterData] = None,
    force_overwrite: bool = False,
    default_cal: bool = False,
    start_time: float = None,
    warn_only: bool = False,
):
    """Starts recording.

    Args:
        output_path (Path): Path of hdf5 file where IV measurements should be
            stored
        mode (str): 'harvesting' for recording harvesting data
        duration (float): Maximum time duration of emulation in seconds
        harvester: name, path or object to a virtual harvester setting
        force_overwrite (bool): True to overwrite existing file under output path,
            False to store under different name
        default_cal (bool): True to use default calibration values, False to
            read calibration data from EEPROM
        start_time (float): Desired start time of emulation in unix epoch time
        warn_only (bool): Set true to continue recording after recoverable
            error
    """
    calib = retrieve_calibration(default_cal)

    if start_time is None:
        start_time = round(time.time() + 10)

    if not output_path.is_absolute():
        output_path = output_path.absolute()
    if output_path.is_dir():
        timestamp = datetime.datetime.fromtimestamp(start_time)
        timestring = timestamp.strftime("%Y-%m-%d_%H-%M-%S")  # closest to ISO 8601, avoid ":"
        store_path = output_path / f"hrv_{timestring}.h5"
    else:
        store_path = output_path

    samples_per_buffer = sysfs_interface.get_samples_per_buffer()
    samplerate_sps = 10**9 * samples_per_buffer // sysfs_interface.get_buffer_period_ns()

    recorder = Recorder(shepherd_mode=mode,
                        harvester=harvester)
    log_writer = LogWriter(store_path=store_path,
                           calibration_data=calib,
                           mode=mode,
                           force_overwrite=force_overwrite,
                           samples_per_buffer=samples_per_buffer,
                           samplerate_sps=samplerate_sps)
    verbose = logger.isEnabledFor(logging.DEBUG)  # performance-critical

    with ExitStack() as stack:

        stack.enter_context(recorder)
        stack.enter_context(log_writer)

        # in_stream has to be disabled to avoid trouble with pytest
        res = invoke.run("hostname", hide=True, warn=True, in_stream=False)
        log_writer["hostname"] = res.stdout
        log_writer.start_monitors()

        recorder.start(start_time, wait_blocking=False)

        logger.info(f"waiting {start_time - time.time():.2f} s until start")
        recorder.wait_for_start(start_time - time.time() + 15)

        logger.info("shepherd started!")

        def exit_gracefully(*args):
            stack.close()
            sys.exit(0)

        signal.signal(signal.SIGTERM, exit_gracefully)
        signal.signal(signal.SIGINT, exit_gracefully)

        if duration is None:
            ts_end = sys.float_info.max
        else:
            ts_end = time.time() + duration

        while time.time() < ts_end:
            try:
                idx, hrv_buf = recorder.get_buffer(verbose=verbose)
            except ShepherdIOException as e:
                logger.error(
                    f"ShepherdIOException(ID={e.id_num}, val={e.value}): {str(e)}"
                )
                err_rec = ExceptionRecord(
                    int(time.time() * 1e9), str(e), e.value
                )
                log_writer.write_exception(err_rec)
                if not warn_only:
                    raise

            log_writer.write_buffer(hrv_buf)
            recorder.return_buffer(idx, verbose=verbose)


def emulate(
        input_path: Path,
        output_path: Path = None,
        duration: float = None,
        force_overwrite: bool = False,
        default_cal: bool = False,
        start_time: float = None,
        set_target_io_lvl_conv: bool = False,
        sel_target_for_io: bool = True,
        sel_target_for_pwr: bool = True,
        aux_target_voltage: float = 0.0,
        settings_virtsource: Union[dict, str, Path, VirtualSourceData] = None,
        log_intermediate_voltage: bool = None,
        uart_baudrate: int = None,
        warn_only: bool = False,
        skip_log_voltage: bool = False,
        skip_log_current: bool = False,
        skip_log_gpio: bool = False,
):
    """ Starts emulation.

    Args:
        :param input_path: [Path] of hdf5 file containing recorded harvesting data
        :param output_path: [Path] of hdf5 file where power measurements should be stored
        :param duration: [float] Maximum time duration of emulation in seconds
        :param force_overwrite: [bool] True to overwrite existing file under output,
            False to store under different name
        :param default_cal: [bool] True to use default calibration values, False to
            read calibration data from EEPROM
        :param start_time: [float] Desired start time of emulation in unix epoch time
        :param set_target_io_lvl_conv: [bool] Enables or disables the GPIO level converter to targets.
        :param sel_target_for_io: [bool] choose which targets gets the io-connection
            (serial, swd, gpio) from beaglebone, True = Target A, False = Target B
        :param sel_target_for_pwr: [bool] choose which targets gets the supply with current-monitor,
            True = Target A, False = Target B
        :param aux_target_voltage: Sets, Enables or disables the voltage for the second target,
            0.0 or False for Disable, True for linking it to voltage of other Target
        :param settings_virtsource: [VirtualSourceData] Settings which define the behavior of VS emulation
        :param uart_baudrate: [int] setting a value to non-zero will activate uart-logging
        :param log_intermediate_voltage: [bool] do log intermediate node instead of output
        :param warn_only: [bool] Set true to continue emulation after recoverable error
        :param skip_log_voltage: [bool] reduce file-size by omitting this log
        :param skip_log_gpio: [bool] reduce file-size by omitting this log
        :param skip_log_current: [bool] reduce file-size by omitting this log
    """
    cal = retrieve_calibration(default_cal)

    if start_time is None:
        start_time = round(time.time() + 10)

    if set_target_io_lvl_conv is None:
        set_target_io_lvl_conv = True

    if sel_target_for_io is None:
        sel_target_for_io = True

    if sel_target_for_pwr is None:
        sel_target_for_pwr = True

    if aux_target_voltage is None:
        aux_target_voltage = 0.0

    samples_per_buffer = sysfs_interface.get_samples_per_buffer()
    samplerate_sps = 10**9 * samples_per_buffer // sysfs_interface.get_buffer_period_ns()

    if output_path is not None:
        if not output_path.is_absolute():
            output_path = output_path.absolute()
        if output_path.is_dir():
            timestamp = datetime.datetime.fromtimestamp(start_time)
            timestring = timestamp.strftime("%Y-%m-%d_%H-%M-%S")  # closest to ISO 8601, avoid ":"
            store_path = output_path / f"emu_{timestring}.h5"
        else:
            store_path = output_path

        log_writer = LogWriter(
            store_path=store_path,
            force_overwrite=force_overwrite,
            mode="emulation",
            calibration_data=cal,
            skip_voltage=skip_log_voltage,
            skip_current=skip_log_current,
            skip_gpio=skip_log_gpio,
            samples_per_buffer=samples_per_buffer,
            samplerate_sps=samplerate_sps
        )

    if isinstance(input_path, str):
        input_path = Path(input_path)
    if input_path is None:
        raise ValueError("No Input-File configured for emulation")
    if not input_path.exists():
        raise ValueError(f"Input-File does not exist ({input_path})")

    log_reader = LogReader(input_path, samples_per_buffer, samplerate_sps)
    verbose = logger.isEnabledFor(logging.DEBUG)  # performance-critical

    with ExitStack() as stack:
        if output_path is not None:
            stack.enter_context(log_writer)
            log_writer.start_monitors(uart_baudrate)

        stack.enter_context(log_reader)

        fifo_buffer_size = sysfs_interface.get_n_buffers()

        emu = Emulator(
            shepherd_mode="emulation",
            initial_buffers=log_reader.read_buffers(end=fifo_buffer_size, verbose=verbose),
            calibration_recording=log_reader.get_calibration_data(),
            calibration_emulation=cal,
            set_target_io_lvl_conv=set_target_io_lvl_conv,
            sel_target_for_io=sel_target_for_io,
            sel_target_for_pwr=sel_target_for_pwr,
            aux_target_voltage=aux_target_voltage,
            settings_virtsource=settings_virtsource,
            log_intermediate_voltage=log_intermediate_voltage,
        )
        stack.enter_context(emu)
        emu.start(start_time, wait_blocking=False)
        logger.info(f"waiting {start_time - time.time():.2f} s until start")
        emu.wait_for_start(start_time - time.time() + 15)

        logger.info("shepherd started!")

        def exit_gracefully(*args):
            stack.close()
            sys.exit(0)

        signal.signal(signal.SIGTERM, exit_gracefully)
        signal.signal(signal.SIGINT, exit_gracefully)

        if duration is None:
            ts_end = sys.float_info.max
        else:
            ts_end = time.time() + duration

        for hrvst_buf in log_reader.read_buffers(start=fifo_buffer_size, verbose=verbose):
            try:
                idx, emu_buf = emu.get_buffer(verbose=verbose)
            except ShepherdIOException as e:
                logger.error(
                    f"ShepherdIOException(ID={e.id_num}, val={e.value}): {str(e)}"
                )

                err_rec = ExceptionRecord(int(time.time() * 1e9), str(e), e.value)
                if output_path is not None:
                    log_writer.write_exception(err_rec)
                if not warn_only:
                    raise

            if output_path is not None:
                log_writer.write_buffer(emu_buf)

            emu.return_buffer(idx, hrvst_buf, verbose)

            if time.time() > ts_end:
                break

        # Read all remaining buffers from PRU
        while True:
            try:
                idx, emu_buf = emu.get_buffer(verbose=verbose)
                if output_path is not None:
                    log_writer.write_buffer(emu_buf)
            except ShepherdIOException as e:
                # We're done when the PRU has processed all emulation data buffers
                if e.id_num == commons.MSG_DEP_ERR_NOFREEBUF:
                    break
                else:
                    if not warn_only:
                        raise
