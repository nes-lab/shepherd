"""
shepherd.__init__
~~~~~
Provides main API functionality for harvesting and emulating with shepherd.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import datetime
import logging
import signal
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from typing import NoReturn
from typing import Optional
from typing import Union

import invoke
import msgpack
import msgpack_numpy
import numpy

from shepherd import commons
from shepherd import sysfs_interface

from .calibration import CalibrationData
from .datalog import ExceptionRecord
from .datalog import LogWriter
from .datalog_reader import LogReader
from .eeprom import EEPROM
from .eeprom import CapeData
from .launcher import Launcher
from .logger_config import get_verbose_level
from .logger_config import set_verbose_level
from .shepherd_io import DataBuffer
from .shepherd_io import ShepherdIO
from .shepherd_io import ShepherdIOException
from .target_io import TargetIO
from .virtual_harvester_config import VirtualHarvesterConfig
from .virtual_source_config import VirtualSourceConfig

__version__ = "0.3.0"

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
    "Recorder",
    "Emulator",
    "ShepherdDebug",
    "run_emulator",
    "run_recorder",
]


logger = logging.getLogger("shp")
set_verbose_level(verbose=1)


class Recorder(ShepherdIO):
    """API for recording data with shepherd.

    Provides an easy to use, high-level interface for recording data with
    shepherd. Configures all hardware and initializes the communication
    with kernel module and PRUs.

    Args:
        shepherd_mode (str): Should be 'harvester' to record harvesting data
        harvester: name, path or object to a virtual harvester setting
        # TODO: DAC-Calibration would be nice to have, in case of active mppt even both adc-cal
    """

    def __init__(
        self,
        shepherd_mode: str = "harvester",
        harvester: Union[dict, str, Path, VirtualHarvesterConfig] = None,
        calibration: CalibrationData = None,
    ):
        logger.debug("Recorder-Init in %s-mode", shepherd_mode)
        self.samplerate_sps = (
            10**9
            * sysfs_interface.get_samples_per_buffer()
            // sysfs_interface.get_buffer_period_ns()
        )
        self.harvester = VirtualHarvesterConfig(harvester, self.samplerate_sps)
        self.calibration = calibration
        super().__init__(shepherd_mode)

    def __enter__(self):
        super().__enter__()

        super().set_power_state_emulator(False)
        super().set_power_state_recorder(True)
        super().send_virtual_harvester_settings(self.harvester)
        super().send_calibration_settings(self.calibration)

        super().reinitialize_prus()  # needed for ADCs

        # Give the PRU empty buffers to begin with
        time.sleep(1)
        for i in range(self.n_buffers):
            time.sleep(
                0.1 * float(self.buffer_period_ns) / 1e9
            )  # could be as low as ~ 10us
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
        super()._return_buffer(index)
        if verbose:
            logger.debug("Sent empty buffer #%s to PRU", index)


class Emulator(ShepherdIO):
    """API for emulating data with shepherd.

    Provides an easy to use, high-level interface for emulating data with
    shepherd. Configures all hardware and initializes the communication
    with kernel module and PRUs.

    Args:
        shepherd_mode:
        initial_buffers: recorded data
            TODO: initial_ is not the best name, is this a yield/generator?
        calibration_recording (CalibrationData): Shepherd calibration data
            belonging to the IV data that is being emulated
        calibration_emulator (CalibrationData): Shepherd calibration data
            belonging to the cape used for emulation
        set_target_io_lvl_conv: Enables or disables the GPIO level converter to targets.
        sel_target_for_io: choose which target gets the io-connection (serial, swd, gpio),
                            True = Target A,
                            False = Target B
        sel_target_for_pwr: choose which targets gets the supply with current-monitor,
                            True = Target A,
                            False = Target B
        aux_target_voltage: Sets, Enables or disables the voltage for the second target,
                            0.0 or False for Disable,
                            True for linking it to voltage of other Target
        infile_vh_cfg (dict): define the behavior of virtual harvester during emulation
    """

    def __init__(
        self,
        shepherd_mode: str = "emulator",
        initial_buffers: list = None,
        calibration_recording: CalibrationData = None,
        # TODO: make clearer that this is "THE RECORDING"
        calibration_emulator: CalibrationData = None,
        set_target_io_lvl_conv: bool = False,
        sel_target_for_io: bool = True,
        sel_target_for_pwr: bool = True,
        aux_target_voltage: float = 0.0,
        vsource: Union[dict, str, Path, VirtualSourceConfig] = None,
        log_intermediate_voltage: bool = None,
        infile_vh_cfg: dict = None,
    ):

        logger.debug("Emulator-Init in %s-mode", shepherd_mode)
        super().__init__(shepherd_mode)
        self._initial_buffers = initial_buffers

        if calibration_emulator is None:
            calibration_emulator = CalibrationData.from_default()
            logger.warning("No calibration data for emulator provided - using defaults")
        if calibration_recording is None:
            calibration_recording = CalibrationData.from_default()
            logger.warning("No calibration data harvester provided - using defaults")

        self.calibration = calibration_emulator
        self.samplerate_sps = (
            10**9
            * sysfs_interface.get_samples_per_buffer()
            // sysfs_interface.get_buffer_period_ns()
        )
        self.vs_cfg = VirtualSourceConfig(
            vsource, self.samplerate_sps, log_intermediate_voltage
        )
        self.vh_cfg = VirtualHarvesterConfig(
            self.vs_cfg.get_harvester(),
            self.samplerate_sps,
            emu_cfg=infile_vh_cfg,
        )

        self._set_target_io_lvl_conv = set_target_io_lvl_conv
        self._sel_target_for_io = sel_target_for_io
        self._sel_target_for_pwr = sel_target_for_pwr
        self._aux_target_voltage = aux_target_voltage

        self._v_gain = 1e6 * calibration_recording["harvester"]["adc_voltage"]["gain"]
        self._v_offset = (
            1e6 * calibration_recording["harvester"]["adc_voltage"]["offset"]
        )
        self._i_gain = 1e9 * calibration_recording["harvester"]["adc_current"]["gain"]
        self._i_offset = (
            1e9 * calibration_recording["harvester"]["adc_current"]["offset"]
        )

    def __enter__(self):
        super().__enter__()

        super().set_power_state_recorder(False)
        super().set_power_state_emulator(True)

        # TODO: why are there wrappers? just directly access
        super().send_calibration_settings(self.calibration)
        super().send_virtual_converter_settings(self.vs_cfg)
        super().send_virtual_harvester_settings(self.vh_cfg)

        super().reinitialize_prus()  # needed for ADCs

        super().set_target_io_level_conv(self._set_target_io_lvl_conv)
        super().select_main_target_for_io(self._sel_target_for_io)
        super().select_main_target_for_power(self._sel_target_for_pwr)
        super().set_aux_target_voltage(self.calibration, self._aux_target_voltage)

        # Preload emulator with data
        time.sleep(1)
        for idx, buffer in enumerate(self._initial_buffers):
            time.sleep(
                0.1 * float(self.buffer_period_ns) / 1e9
            )  # could be as low as ~ 10us
            self.return_buffer(idx, buffer, verbose=True)

        return self

    def return_buffer(self, index, buffer, verbose: bool = False):
        if verbose:
            ts_start = time.time()

        # Convert raw ADC data to SI-Units -> the virtual-source-emulator in PRU expects uV and nV
        voltage_transformed = (buffer.voltage * self._v_gain + self._v_offset).astype(
            "u4"
        )
        current_transformed = (buffer.current * self._i_gain + self._i_offset).astype(
            "u4"
        )

        self.shared_mem.write_buffer(index, voltage_transformed, current_transformed)
        super()._return_buffer(index)
        if verbose:
            logger.debug(
                "Sending emu-buffer #%d to PRU took %.2f ms",
                index,
                1e3 * (time.time() - ts_start),
            )


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
            logger.warning(
                "Couldn't read calibration from EEPROM (Val). Falling back to default values."
            )
            self._cal = CalibrationData.from_default()
        except FileNotFoundError:
            logger.warning(
                "Couldn't read calibration from EEPROM (FS). Falling back to default values."
            )
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
        elif channel.lower() in [
            "emu",
            "emu_a_out",
            "emu_i_out",
            "a_out",
            "i_out",
        ]:
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
        """issues a pru-read of the gpio-registers that monitor target-communication

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
            channels: 4 lower bits of int-num control
                b0: harvester-ch-a,
                b1: hrv-ch-b,
                b2: emulator-ch-a,
                b3: emu-ch-b
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
                f"Expected msg type { hex(commons.MSG_DBG_FN_TESTS) }, "
                f"but got type={ hex(msg_type) } val={ values }"
            )
        return values[0] * (2**32) + values[1]  # P_out_pW

    def vsource_init(
        self,
        vs_settings: VirtualSourceConfig,
        cal_settings,
        input_setting: Optional[dict],
    ):
        super().send_virtual_converter_settings(vs_settings)
        super().send_calibration_settings(cal_settings)
        vh_config = VirtualHarvesterConfig(
            vs_settings.get_harvester(),
            vs_settings.samplerate_sps,
            emu_cfg=input_setting,
        )
        super().send_virtual_harvester_settings(vh_config)
        time.sleep(0.5)
        super().start()
        super()._send_msg(commons.MSG_DBG_VSOURCE_INIT, 0)
        msg_type, values = super()._get_msg()  # no data, just a confirmation
        if msg_type != commons.MSG_DBG_VSOURCE_INIT:
            raise ShepherdIOException(
                f"Expected msg type { hex(commons.MSG_DBG_VSOURCE_INIT) }, "
                f"but got type={ hex(msg_type) } val={ values }"
            )
        # TEST-SIMPLIFICATION - code below is not part of pru-code
        self.P_in_fW = 0.0
        self.P_out_fW = 0.0
        self._cal = cal_settings

    def vsource_calc_inp_power(
        self, input_voltage_uV: int, input_current_nA: int
    ) -> int:
        super()._send_msg(
            commons.MSG_DBG_VSOURCE_P_INP,
            [int(input_voltage_uV), int(input_current_nA)],
        )
        msg_type, values = self._get_msg()
        if msg_type != commons.MSG_DBG_VSOURCE_P_INP:
            raise ShepherdIOException(
                f"Expected msg type { hex(commons.MSG_DBG_VSOURCE_P_INP) }, "
                f"but got type={ hex(msg_type) } val={ values }"
            )
        return values[0] * (2**32) + values[1]  # P_inp_pW

    def vsource_charge(
        self, input_voltage_uV: int, input_current_nA: int
    ) -> (int, int):
        self._send_msg(
            commons.MSG_DBG_VSOURCE_CHARGE,
            [int(input_voltage_uV), int(input_current_nA)],
        )
        msg_type, values = self._get_msg()
        if msg_type != commons.MSG_DBG_VSOURCE_CHARGE:
            raise ShepherdIOException(
                f"Expected msg type { hex(commons.MSG_DBG_VSOURCE_CHARGE) }, "
                f"but got type={ hex(msg_type) } val={ values }"
            )
        return values[0], values[1]  # V_store_uV, V_out_dac_raw

    def vsource_calc_out_power(self, current_adc_raw: int) -> int:
        self._send_msg(commons.MSG_DBG_VSOURCE_P_OUT, int(current_adc_raw))
        msg_type, values = self._get_msg()
        if msg_type != commons.MSG_DBG_VSOURCE_P_OUT:
            raise ShepherdIOException(
                f"Expected msg type { hex(commons.MSG_DBG_VSOURCE_P_OUT) }, "
                f"but got type={ hex(msg_type) } val={ values }"
            )
        return values[0] * (2**32) + values[1]  # P_out_pW

    def vsource_drain(self, current_adc_raw: int) -> (int, int):
        self._send_msg(commons.MSG_DBG_VSOURCE_DRAIN, int(current_adc_raw))
        msg_type, values = self._get_msg()
        if msg_type != commons.MSG_DBG_VSOURCE_DRAIN:
            raise ShepherdIOException(
                f"Expected msg type { hex(commons.MSG_DBG_VSOURCE_DRAIN) }, "
                f"but got type={ hex(msg_type) } val={ values }"
            )
        return values[0], values[1]  # V_store_uV, V_out_dac_raw

    def vsource_update_cap_storage(self) -> int:
        self._send_msg(commons.MSG_DBG_VSOURCE_V_CAP, 0)
        msg_type, values = self._get_msg()
        if msg_type != commons.MSG_DBG_VSOURCE_V_CAP:
            raise ShepherdIOException(
                f"Expected msg type { hex(commons.MSG_DBG_VSOURCE_V_CAP) }, "
                f"but got type={ hex(msg_type) } val={ values }"
            )
        return values[0]  # V_store_uV

    def vsource_update_states_and_output(self) -> int:
        self._send_msg(commons.MSG_DBG_VSOURCE_V_OUT, 0)
        msg_type, values = self._get_msg()
        if msg_type != commons.MSG_DBG_VSOURCE_V_OUT:
            raise ShepherdIOException(
                f"Expected msg type { hex(commons.MSG_DBG_VSOURCE_V_OUT) }, "
                f"but got type={ hex(msg_type) } val={ values }"
            )
        return values[0]  # V_out_dac_raw

    # TEST-SIMPLIFICATION - code below is also part py-vsource with same interface
    def iterate_sampling(self, V_in_uV: int = 0, A_in_nA: int = 0, A_out_nA: int = 0):
        self.vsource_calc_inp_power(V_in_uV, A_in_nA)
        A_out_raw = self._cal.convert_value_to_raw(
            "emulator", "adc_current", A_out_nA * 10**-9
        )
        self.vsource_calc_out_power(A_out_raw)
        self.vsource_update_cap_storage()
        V_out_raw = self.vsource_update_states_and_output()
        V_out_uV = int(
            self._cal.convert_raw_to_value("emulator", "dac_voltage_b", V_out_raw)
            * 10**6
        )
        self.P_in_fW += V_in_uV * A_in_nA
        self.P_out_fW += V_out_uV * A_out_nA
        return V_out_uV

    @staticmethod
    def is_alive() -> bool:
        """feedback-fn for RPC-usage to check for connection
        :return: True
        """
        return True

    # all methods below are wrapper for zerorpc - it seems
    # to have trouble with inheritance and runtime inclusion

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
            logger.debug("Error: IO is not enabled in this shepherd-debug-instance")

    def set_power_state_emulator(self, state: bool) -> NoReturn:
        super().set_power_state_emulator(state)

    def set_power_state_recorder(self, state: bool) -> NoReturn:
        super().set_power_state_recorder(state)

    def reinitialize_prus(self) -> NoReturn:
        super().reinitialize_prus()

    def get_power_state_shepherd(self) -> bool:
        return self.gpios["en_shepherd"].read()

    def get_power_state_recorder(self) -> bool:
        return self.gpios["en_recorder"].read()

    def get_power_state_emulator(self) -> bool:
        return self.gpios["en_emulator"].read()

    def get_main_target_for_power(self) -> bool:
        return self.gpios["target_pwr_sel"].read()

    def get_main_target_for_io(self) -> bool:
        return self.gpios["target_io_sel"].read()

    def get_target_io_level_conv(self) -> bool:
        return self.gpios["target_io_en"].read()

    @staticmethod
    def set_aux_target_voltage_raw(voltage_raw, also_main: bool = False) -> NoReturn:
        sysfs_interface.write_dac_aux_voltage_raw(voltage_raw | (int(also_main) << 20))

    def switch_shepherd_mode(self, mode: str) -> str:
        mode_old = sysfs_interface.get_mode()
        super().set_power_state_recorder(False)
        super().set_power_state_emulator(False)
        sysfs_interface.write_mode(mode, force=True)
        super().set_power_state_recorder(True)
        super().set_power_state_emulator(True)
        super().reinitialize_prus()
        if "debug" in mode:
            super().start(wait_blocking=True)
        return mode_old

    def sample_from_pru(self, length_n_buffers: int = 10):
        length_n_buffers = int(min(max(length_n_buffers, 1), 55))
        super().reinitialize_prus()
        time.sleep(0.1)
        for _i in range(length_n_buffers + 4):  # Fill FIFO
            time.sleep(0.02)
            super()._return_buffer(_i)
        time.sleep(0.1)
        super().start(wait_blocking=True)
        c_array = numpy.empty([0], dtype="=u4")
        v_array = numpy.empty([0], dtype="=u4")
        time.sleep(0.1)
        for _ in range(2):  # flush first 2 buffers out
            super().get_buffer()
        for _ in range(length_n_buffers):  # get Data
            idx, _buf = super().get_buffer()
            c_array = numpy.hstack((c_array, _buf.current))
            v_array = numpy.hstack((v_array, _buf.voltage))
        super().reinitialize_prus()
        base_array = numpy.vstack((c_array, v_array))
        return msgpack.packb(
            base_array, default=msgpack_numpy.encode
        )  # zeroRPC / msgpack can not handle numpy-data without this


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
                "Falling back to default values."
            )
            return CalibrationData.from_default()
        except FileNotFoundError:
            logger.warning(
                "Couldn't read calibration from EEPROM (FileNotFoundError). "
                "Falling back to default values."
            )
            return CalibrationData.from_default()


def run_recorder(
    output_path: Path,
    duration: float = None,
    harvester: Union[dict, str, Path, VirtualHarvesterConfig] = None,
    force_overwrite: bool = False,
    use_cal_default: bool = False,
    start_time: float = None,
    warn_only: bool = False,
    output_compression=None,
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
    cal_data = retrieve_calibration(use_cal_default)

    if start_time is None:
        start_time = round(time.time() + 10)

    if not output_path.is_absolute():
        output_path = output_path.absolute()
    if output_path.is_dir():
        timestamp = datetime.datetime.fromtimestamp(start_time)
        timestring = timestamp.strftime(
            "%Y-%m-%d_%H-%M-%S"
        )  # closest to ISO 8601, avoid ":"
        store_path = output_path / f"hrv_{timestring}.h5"
    else:
        store_path = output_path

    samples_per_buffer = sysfs_interface.get_samples_per_buffer()
    samplerate_sps = (
        10**9 * samples_per_buffer // sysfs_interface.get_buffer_period_ns()
    )

    recorder = Recorder(shepherd_mode=mode, harvester=harvester, calibration=cal_data)
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
            recorder
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

        def exit_gracefully(*args):
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
                    raise

            if (hrv_buf.timestamp_ns / 1e9) >= ts_end:
                break

            log_writer.write_buffer(hrv_buf)
            recorder.return_buffer(idx, verbose=verbose)


def run_emulator(
    input_path: Path,
    output_path: Path = None,
    duration: float = None,
    force_overwrite: bool = False,
    use_cal_default: bool = False,
    start_time: float = None,
    set_target_io_lvl_conv: bool = False,
    sel_target_for_io: bool = True,
    sel_target_for_pwr: bool = True,
    aux_target_voltage: float = 0.0,
    virtsource: Union[dict, str, Path, VirtualSourceConfig] = None,
    log_intermediate_voltage: bool = None,
    uart_baudrate: int = None,
    warn_only: bool = False,
    skip_log_voltage: bool = False,
    skip_log_current: bool = False,
    skip_log_gpio: bool = False,
    output_compression=None,
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
        :param set_target_io_lvl_conv: [bool] Enables the GPIO level converter to targets.
        :param sel_target_for_io: [bool] choose which targets gets the io-connection
            (serial, swd, gpio) from beaglebone, True = Target A, False = Target B
        :param sel_target_for_pwr: [bool] choose which targets gets the supply with current-monitor,
            True = Target A, False = Target B
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
    cal = retrieve_calibration(use_cal_default)

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
    samplerate_sps = (
        10**9 * samples_per_buffer // sysfs_interface.get_buffer_period_ns()
    )

    if output_path is not None:
        if not output_path.is_absolute():
            output_path = output_path.absolute()
        if output_path.is_dir():
            timestamp = datetime.datetime.fromtimestamp(start_time)
            timestring = timestamp.strftime(
                "%Y-%m-%d_%H-%M-%S"
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
        if output_path is not None:
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

        emu = Emulator(
            shepherd_mode=mode,  # TODO: this should not be needed anymore
            initial_buffers=init_buffers,
            calibration_recording=CalibrationData(log_reader.get_calibration_data()),
            calibration_emulator=cal,
            set_target_io_lvl_conv=set_target_io_lvl_conv,
            sel_target_for_io=sel_target_for_io,
            sel_target_for_pwr=sel_target_for_pwr,
            aux_target_voltage=aux_target_voltage,
            vsource=virtsource,
            log_intermediate_voltage=log_intermediate_voltage,
            infile_vh_cfg=log_reader.get_hrv_config(),
        )
        stack.enter_context(emu)
        if output_path is not None:
            log_writer.embed_config(emu.vs_cfg.data)
        emu.start(start_time, wait_blocking=False)
        logger.info("waiting %.2f s until start", start_time - time.time())
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
            ts_end = start_time + duration

        for _, dsv, dsc in log_reader.read_buffers(start_n=fifo_buffer_size):
            try:
                idx, emu_buf = emu.get_buffer(verbose=verbose)
            except ShepherdIOException as e:
                logger.warning("Caught an Exception", exc_info=e)

                err_rec = ExceptionRecord(int(time.time() * 1e9), str(e), e.value)
                if output_path is not None:
                    log_writer.write_exception(err_rec)
                if not warn_only:
                    raise

            if emu_buf.timestamp_ns / 1e9 >= ts_end:
                break

            if output_path is not None:
                log_writer.write_buffer(emu_buf)

            hrvst_buf = DataBuffer(voltage=dsv, current=dsc)
            emu.return_buffer(idx, hrvst_buf, verbose)

        # Read all remaining buffers from PRU
        while True:
            try:
                idx, emu_buf = emu.get_buffer(verbose=verbose)
                if emu_buf.timestamp_ns / 1e9 >= ts_end:
                    break
                if output_path is not None:
                    log_writer.write_buffer(emu_buf)
            except ShepherdIOException as e:
                # We're done when the PRU has processed all emulation data buffers
                if e.id_num == commons.MSG_DEP_ERR_NOFREEBUF:
                    break
                else:
                    if not warn_only:
                        raise
