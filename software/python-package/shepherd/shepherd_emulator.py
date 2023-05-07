import time
from typing import Optional

from . import sysfs_interface
from .calibration import CalibrationData
from .logger import logger
from .shepherd_io import ShepherdIO
from .shared_memory import DataBuffer
from .virtual_harvester_config import VirtualHarvesterConfig
from .virtual_source_config import T_vSrc
from .virtual_source_config import VirtualSourceConfig


class ShepherdEmulator(ShepherdIO):
    """API for emulating data with shepherd.

    Provides an easy to use, high-level interface for emulating data with
    shepherd. Configures all hardware and initializes the communication
    with kernel module and PRUs.

    Args:
        shepherd_mode:
        initial_buffers: recorded data,
        calibration_recording (CalibrationData): Shepherd calibration data
            belonging to the IV data that is being emulated
        calibration_emulator (CalibrationData): Shepherd calibration data
            belonging to the cape used for emulation
        enable_io: Enables or disables the GPIO level converter to targets.
        io_target: target-port (A or B) that gets the io-connection (serial, swd, gpio),
        pwr_target: target-port (A or B) that gets the supply with current-monitor,
        aux_target_voltage: Sets, Enables or disables the voltage for the second target,
                            0.0 or False for Disable,
                            True for linking it to voltage of other Target
        infile_vh_cfg (dict): define the behavior of virtual harvester during emulation
    """

    def __init__(
        self,
        shepherd_mode: str = "emulator",
        initial_buffers: Optional[list] = None,
        calibration_recording: Optional[CalibrationData] = None,
        # TODO: make clearer that this is "THE RECORDING"
        calibration_emulator: Optional[CalibrationData] = None,
        enable_io: bool = False,
        io_target: str = "A",
        pwr_target: str = "A",
        aux_target_voltage: float = 0.0,
        vsource: Optional[T_vSrc] = None,
        log_intermediate_voltage: Optional[bool] = None,
        infile_vh_cfg: Optional[dict] = None,
    ):
        logger.debug("Emulator-Init in %s-mode", shepherd_mode)
        super().__init__(shepherd_mode)
        if initial_buffers is None:
            raise ValueError("initial buffers must be provided")
        self._initial_buffers: list = initial_buffers

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
            vsource,
            self.samplerate_sps,
            log_intermediate_voltage,
        )
        self.vh_cfg = VirtualHarvesterConfig(
            self.vs_cfg.get_harvester(),
            self.samplerate_sps,
            emu_cfg=infile_vh_cfg,
        )

        self._enable_io = enable_io
        self._io_target = io_target
        self._pwr_target = pwr_target
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

        super().set_target_io_level_conv(self._enable_io)
        super().select_main_target_for_io(self._io_target)
        super().select_main_target_for_power(self._pwr_target)
        super().set_aux_target_voltage(self.calibration, self._aux_target_voltage)

        # Preload emulator with data
        time.sleep(1)
        for idx, buffer in enumerate(self._initial_buffers):
            time.sleep(
                0.1 * float(self.buffer_period_ns) / 1e9,
            )  # could be as low as ~ 10us
            self.return_buffer(idx, buffer, verbose=True)

        return self

    def return_buffer(self, index: int, buffer: DataBuffer, verbose: bool = False):
        ts_start = time.time() if verbose else 0

        # Convert raw ADC data to SI-Units -> the virtual-source-emulator in PRU expects uV and nV
        voltage_transformed = (buffer.voltage * self._v_gain + self._v_offset).astype(
            "u4",
        )
        current_transformed = (buffer.current * self._i_gain + self._i_offset).astype(
            "u4",
        )

        self.shared_mem.write_buffer(index, voltage_transformed, current_transformed)
        super()._return_buffer(index)
        if verbose:
            logger.debug(
                "Sending emu-buffer #%d to PRU took %.2f ms",
                index,
                1e3 * (time.time() - ts_start),
            )
