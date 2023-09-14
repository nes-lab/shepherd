import platform
import sys
import time
from contextlib import ExitStack
from datetime import datetime
from typing import Optional

from shepherd_core import Reader
from shepherd_core import CalibrationPair
from shepherd_core import CalibrationSeries
from shepherd_core.data_models import EnergyDType
from shepherd_core.data_models.content.virtual_harvester import HarvesterPRUConfig
from shepherd_core.data_models.content.virtual_source import ConverterPRUConfig
from shepherd_core.data_models.task import EmulationTask

from . import commons
from .target_io import TargetIO, target_pins
from . import sysfs_interface
from .eeprom import retrieve_calibration
from .h5_writer import ExceptionRecord
from .h5_writer import Writer
from .logger import get_verbose_level
from .logger import log
from .shared_memory import DataBuffer
from .shepherd_io import ShepherdIO
from .shepherd_io import ShepherdIOException


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
        log.debug("ShepherdEmulator-Init in %s-mode", mode)
        super().__init__(
            mode=mode,
            trace_iv=cfg.power_tracing,
            trace_gpio=cfg.gpio_tracing,
        )
        self.cfg = cfg
        self.stack = ExitStack()

        # performance-critical, <4 reduces chatter during main-loop
        self.verbose = get_verbose_level() >= 4

        if not cfg.input_path.exists():
            raise ValueError(f"Input-File does not exist ({cfg.input_path})")
        self.reader = Reader(cfg.input_path, verbose=get_verbose_level() > 2)
        self.stack.enter_context(self.reader)
        if self.reader.get_mode() != "harvester":
            msg = f"Input-File has wrong mode ({self.reader.get_mode()} != harvester)"
            if self.cfg.abort_on_error:
                raise ValueError(msg)
            else:
                log.error(msg)
        if not self.reader.is_valid() and self.cfg.abort_on_error:
            raise RuntimeError("Input-File is not valid!")

        cal_inp = self.reader.get_calibration_data()
        if cal_inp is None:
            cal_inp = CalibrationSeries()
            log.warning(
                "No calibration data from emulation-input (harvest) provided"
                " - using defaults",
            )

        # PRU expects values in SI: uV and nV
        self.cal_pru = CalibrationSeries(
            voltage=CalibrationPair(
                gain=1e6 * cal_inp.voltage.gain,
                offset=1e6 * cal_inp.voltage.offset,
            ),
            current=CalibrationPair(
                gain=1e9 * cal_inp.current.gain,
                offset=1e9 * cal_inp.current.offset,
            ),
        )

        self.cal_emu = retrieve_calibration(cfg.use_cal_default).emulator

        if cfg.time_start is None:
            self.start_time = round(time.time() + 10)
        else:
            self.start_time = cfg.time_start.timestamp()

        self.samples_per_buffer = sysfs_interface.get_samples_per_buffer()
        self.samplerate_sps = (
            10**9 * self.samples_per_buffer // sysfs_interface.get_buffer_period_ns()
        )
        self.fifo_buffer_size = sysfs_interface.get_n_buffers()
        # TODO: write gpio-mask

        log_iv = cfg.power_tracing is not None
        log_cap = log_iv and cfg.power_tracing.intermediate_voltage
        self.cnv_pru = ConverterPRUConfig.from_vsrc(
            data=cfg.virtual_source,
            log_intermediate_node=log_cap,
        )
        self.hrv_pru = HarvesterPRUConfig.from_vhrv(
            data=cfg.virtual_source.harvester,
            for_emu=False,
            dtype_in=self.reader.get_datatype(),
        )
        log.info("Virtual Source will be initialized to:\n%s", cfg.virtual_source)

        self.writer: Optional[Writer] = None
        if cfg.output_path is not None:
            store_path = cfg.output_path.resolve()
            if store_path.is_dir():
                timestamp = datetime.fromtimestamp(self.start_time)
                timestring = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
                # ⤷ closest to ISO 8601, avoids ":"
                store_path = store_path / f"emu_{timestring}.h5"
            self.writer = Writer(
                file_path=store_path,
                force_overwrite=cfg.force_overwrite,
                mode=mode,
                datatype=EnergyDType.ivsample,
                cal_data=self.cal_emu,
                samples_per_buffer=self.samples_per_buffer,
                samplerate_sps=self.samplerate_sps,
                compression=cfg.output_compression,
                verbose=get_verbose_level() > 2,
            )

        # hard-wire pin-direction until they are configurable
        self._io: Optional[TargetIO] = TargetIO()
        log.info("Setting variable GPIO to INPUT (actuation is not implemented yet)")
        for pin in range(len(target_pins)):
            self._io.set_pin_direction(pin, pdir=True)  # True = Inp

    def __enter__(self):
        super().__enter__()
        super().set_power_state_recorder(False)
        super().set_power_state_emulator(True)

        # TODO: why are there wrappers? just directly access
        super().send_calibration_settings(self.cal_emu)
        super().send_virtual_converter_settings(self.cnv_pru)
        super().send_virtual_harvester_settings(self.hrv_pru)

        super().reinitialize_prus()  # needed for ADCs

        super().set_io_level_converter(self.cfg.enable_io)
        super().select_port_for_io_interface(self.cfg.io_port)
        super().select_port_for_power_tracking(self.cfg.io_port)
        super().set_aux_target_voltage(self.cfg.voltage_aux, self.cal_emu)

        if self.writer is not None:
            self.stack.enter_context(self.writer)
            # add hostname to file
            self.writer.store_hostname(platform.node().strip())
            self.writer.start_monitors(self.cfg.sys_logging, self.cfg.gpio_tracing)
            self.writer.store_config(self.cfg.virtual_source.model_dump())
            # TODO: restore to .cfg.dict() -> fails for yaml-repr of path

        # Preload emulator with data
        time.sleep(1)
        init_buffers = [
            DataBuffer(voltage=dsv, current=dsc)
            for _, dsv, dsc in self.reader.read_buffers(
                end_n=self.fifo_buffer_size,
                is_raw=True,
            )
        ]
        for idx, buffer in enumerate(init_buffers):
            self.return_buffer(idx, buffer, verbose=True)
            time.sleep(0.1 * float(self.buffer_period_ns) / 1e9)
            # ⤷ could be as low as ~ 10us
        return self

    def __exit__(self, *args):  # type: ignore
        self.stack.close()
        super().__exit__()

    def return_buffer(self, index: int, buffer: DataBuffer, verbose: bool = False):
        ts_start = time.time() if verbose else 0

        # transform raw ADC data to SI-Units -> the virtual-source-emulator in PRU expects uV and nV
        v_tf = self.cal_pru.voltage.raw_to_si(buffer.voltage).astype("u4")
        c_tf = self.cal_pru.current.raw_to_si(buffer.current).astype("u4")

        self.shared_mem.write_buffer(index, v_tf, c_tf)
        super()._return_buffer(index)
        if verbose:
            log.debug(
                "Sending emu-buffer #%d to PRU took %.2f ms",
                index,
                1e3 * (time.time() - ts_start),
            )

    def run(self):
        self.start(self.start_time, wait_blocking=False)
        log.info("waiting %.2f s until start", self.start_time - time.time())
        self.wait_for_start(self.start_time - time.time() + 15)
        log.info("shepherd started!")

        if self.cfg.duration is None:
            ts_end = sys.float_info.max
        else:
            duration_s = self.cfg.duration.total_seconds()
            ts_end = self.start_time + duration_s
            log.debug("Duration = %s (forced runtime)", duration_s)

        # Main Loop
        for _, dsv, dsc in self.reader.read_buffers(
            start_n=self.fifo_buffer_size,
            is_raw=True,
        ):
            try:
                idx, emu_buf = self.get_buffer(verbose=self.verbose)
            except ShepherdIOException as e:
                log.warning("Caught an Exception", exc_info=e)

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
