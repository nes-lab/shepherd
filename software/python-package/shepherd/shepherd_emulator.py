import sys
import time
from contextlib import ExitStack
from datetime import datetime
from typing import Optional

import invoke
from shepherd_core.data_models.task import EmulationTask

from . import commons
from . import sysfs_interface
from .calibration import CalibrationData
from .datalog import ExceptionRecord
from .datalog import LogWriter
from .datalog_reader import LogReader
from .eeprom import retrieve_calibration
from .logger import get_verbose_level
from .logger import logger
from .shared_memory import DataBuffer
from .shepherd_io import ShepherdIO
from .shepherd_io import ShepherdIOException
from .virtual_harvester_config import VirtualHarvesterConfig
from .virtual_source_config import VirtualSourceConfig


class ShepherdEmulator(ShepherdIO):
    """API for emulating data with shepherd.

    Provides a high-level interface for emulating data with
    shepherd. Configures all hardware and initializes the communication
    with kernel module and PRUs.

    """

    def __init__(
        self,
        cfg: EmulationTask,
        mode: str = "emulator",
    ):
        logger.debug("Emulator-Init in %s-mode", mode)
        super().__init__(mode)
        self.cfg = cfg
        self.stack = ExitStack()

        # performance-critical, <4 reduces chatter during main-loop
        self.verbose = get_verbose_level() >= 4

        if not cfg.input_path.exists():
            raise ValueError(f"Input-File does not exist ({cfg.input_path})")
        self.reader = LogReader(cfg.input_path, verbose=self.verbose)
        self.stack.enter_context(self.reader)
        # TODO: new reader allows to check mode and dtype of recording (should be emu, ivcurves)

        cal_inp = self.reader.get_calibration_data()
        if cal_inp is None:
            cal_inp = CalibrationData.from_default()
            logger.warning(
                "No calibration data from emulation-input (harvest) provided"
                " - using defaults",
            )
        self._v_gain = 1e6 * cal_inp["harvester"]["adc_voltage"]["gain"]
        self._v_offset = 1e6 * cal_inp["harvester"]["adc_voltage"]["offset"]
        self._i_gain = 1e9 * cal_inp["harvester"]["adc_current"]["gain"]
        self._i_offset = 1e9 * cal_inp["harvester"]["adc_current"]["offset"]

        self.cal_hw = retrieve_calibration(cfg.use_cal_default)

        if cfg.time_start is None:
            self.start_time = round(time.time() + 10)
        else:
            self.start_time = cfg.time_start.timestamp()

        # TODO: are these used more than once?
        self.samples_per_buffer = sysfs_interface.get_samples_per_buffer()
        self.samplerate_sps = (
            10**9 * self.samples_per_buffer // sysfs_interface.get_buffer_period_ns()
        )
        self.fifo_buffer_size = sysfs_interface.get_n_buffers()

        # TODO: complete rebuild vs_cfg and vh_cfg
        log_cap = (
            cfg.power_tracing is not None and cfg.power_tracing.intermediate_voltage
        )
        self.vs_cfg = VirtualSourceConfig(
            cfg.virtual_source,
            self.samplerate_sps,
            log_cap,
        )
        self.vh_cfg = VirtualHarvesterConfig(
            self.vs_cfg.get_harvester(),
            self.samplerate_sps,
            emu_cfg=self.reader.get_hrv_config(),
        )

        self.writer: Optional[LogWriter] = None
        if cfg.output_path is not None:
            store_path = cfg.output_path.absolute()
            if store_path.is_dir():
                timestamp = datetime.fromtimestamp(self.start_time)
                timestring = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
                # ⤷ closest to ISO 8601, avoids ":"
                store_path = store_path / f"emu_{timestring}.h5"
            self.writer = LogWriter(
                file_path=store_path,
                pwr_cfg=cfg.power_tracing,
                gpio_cfg=cfg.gpio_tracing,
                force_overwrite=cfg.force_overwrite,
                mode="emulator",
                datatype="ivsample",
                calibration_data=self.cal_hw,
                samples_per_buffer=self.samples_per_buffer,
                samplerate_sps=self.samplerate_sps,
                output_compression=cfg.output_compression,
            )

    def __enter__(self):
        super().__enter__()
        super().set_power_state_recorder(False)
        super().set_power_state_emulator(True)

        # TODO: why are there wrappers? just directly access
        super().send_calibration_settings(self.cal_hw)
        super().send_virtual_converter_settings(self.vs_cfg)
        super().send_virtual_harvester_settings(self.vh_cfg)

        super().reinitialize_prus()  # needed for ADCs

        super().set_target_io_level_conv(self.cfg.enable_io)
        super().select_main_target_for_io(self.cfg.io_port)
        super().select_main_target_for_power(self.cfg.io_port)
        super().set_aux_target_voltage(self.cal_hw, self.cfg.voltage_aux)

        if self.writer is not None:
            self.stack.enter_context(self.writer)
            # add hostname to file
            res = invoke.run("hostname", hide=True, warn=True, in_stream=False)
            self.writer["hostname"] = "".join(
                x for x in res.stdout if x.isprintable()
            ).strip()
            self.writer.start_monitors(self.cfg.sys_logging, self.cfg.gpio_tracing)
            self.writer.embed_config(self.vs_cfg.data)

        # Preload emulator with data
        time.sleep(1)
        init_buffers = [
            DataBuffer(voltage=dsv, current=dsc)
            for _, dsv, dsc in self.reader.read_buffers(end_n=self.fifo_buffer_size)
        ]
        for idx, buffer in enumerate(init_buffers):
            self.return_buffer(idx, buffer, verbose=True)
            time.sleep(0.1 * float(self.buffer_period_ns) / 1e9)
            # could be as low as ~ 10us
        return self

    def __exit__(self):
        self.stack.close()
        super().__exit__()

    def return_buffer(self, index: int, buffer: DataBuffer, verbose: bool = False):
        ts_start = time.time() if verbose else 0

        # transform raw ADC data to SI-Units -> the virtual-source-emulator in PRU expects uV and nV
        v_tf = (buffer.voltage * self._v_gain + self._v_offset).astype("u4")
        c_tf = (buffer.current * self._i_gain + self._i_offset).astype("u4")

        self.shared_mem.write_buffer(index, v_tf, c_tf)
        super()._return_buffer(index)
        if verbose:
            logger.debug(
                "Sending emu-buffer #%d to PRU took %.2f ms",
                index,
                1e3 * (time.time() - ts_start),
            )

    def run(self):
        self.start(self.start_time, wait_blocking=False)
        logger.info("waiting %.2f s until start", self.start_time - time.time())
        self.wait_for_start(self.start_time - time.time() + 15)
        logger.info("shepherd started!")

        if self.cfg.duration is None:
            ts_end = sys.float_info.max
        else:
            ts_end = self.start_time + self.cfg.duration.total_seconds()

        for _, dsv, dsc in self.reader.read_buffers(start_n=self.fifo_buffer_size):
            try:
                idx, emu_buf = self.get_buffer(verbose=self.verbose)
            except ShepherdIOException as e:
                logger.warning("Caught an Exception", exc_info=e)

                err_rec = ExceptionRecord(int(time.time() * 1e9), str(e), e.value)
                if self.writer is not None:
                    self.writer.write_exception(err_rec)
                if self.cfg.abort_on_error:
                    raise RuntimeError("Caught unforgivable ShepherdIO-Exception")
                continue

            if emu_buf.timestamp_ns / 1e9 >= ts_end:
                break

            if self.writer is not None:
                self.writer.write_buffer(emu_buf)

            hrvst_buf = DataBuffer(voltage=dsv, current=dsc)
            self.return_buffer(idx, hrvst_buf, self.verbose)

        # Read all remaining buffers from PRU
        while True:
            try:
                idx, emu_buf = self.get_buffer(verbose=self.verbose)
                if emu_buf.timestamp_ns / 1e9 >= ts_end:
                    break
                if self.writer is not None:
                    self.writer.write_buffer(emu_buf)
            except ShepherdIOException as e:
                # We're done when the PRU has processed all emulation data buffers
                if e.id_num == commons.MSG_DEP_ERR_NOFREEBUF:
                    break
                else:
                    if self.cfg.abort_on_error:
                        raise RuntimeError("Caught unforgivable ShepherdIO-Exception")
