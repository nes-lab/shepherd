import math
import platform
import sys
import time
from contextlib import ExitStack
from datetime import datetime
from types import TracebackType

from shepherd_core import CalibrationPair
from shepherd_core import CalibrationSeries
from shepherd_core import Reader as CoreReader
from shepherd_core import local_tz
from shepherd_core.data_models import EnergyDType
from shepherd_core.data_models.content.virtual_harvester import HarvesterPRUConfig
from shepherd_core.data_models.content.virtual_source import ConverterPRUConfig
from shepherd_core.data_models.task import EmulationTask
from tqdm import tqdm
from typing_extensions import Self

from . import commons
from .eeprom import retrieve_calibration
from .h5_writer import Writer
from .logger import get_verbosity
from .logger import log
from .shared_mem_iv_input import IVTrace
from .shepherd_io import ShepherdIO
from .shepherd_io import ShepherdPRUError
from .sysfs_interface import set_stop
from .target_io import TargetIO
from .target_io import target_pins


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
    ) -> None:
        log.debug("ShepherdEmulator-Init in %s-mode", mode)
        super().__init__(
            mode=mode,
            trace_iv=cfg.power_tracing,
            trace_gpio=cfg.gpio_tracing,
        )
        self.cfg = cfg
        self.stack = ExitStack()

        # performance-critical, allows deep insight between py<-->pru-communication
        self.verbose_extra = False

        if not cfg.input_path.exists():
            msg = f"Input-File does not exist ({cfg.input_path})"
            raise FileNotFoundError(msg)
        self.reader = CoreReader(cfg.input_path, verbose=get_verbosity())
        self.stack.enter_context(self.reader)
        if self.reader.get_mode() != "harvester":
            msg = f"Input-File has wrong mode ({self.reader.get_mode()} != harvester)"
            if self.cfg.abort_on_error:
                raise ValueError(msg)
            log.error(msg)
        if not self.reader.is_valid() and self.cfg.abort_on_error:
            raise RuntimeError("Input-File is not valid!")

        self.samples_per_segment = self.reader.BUFFER_SAMPLES_N
        cal_inp = self.reader.get_calibration_data()
        if cal_inp is None:
            cal_inp = CalibrationSeries()
            log.warning(
                "No calibration data from emulation-input (harvest) provided - using defaults",
            )

        # PRU expects values in SI: uV and nV
        self.cal_pru = CalibrationSeries(
            voltage=CalibrationPair(
                gain=1e6 * cal_inp.voltage.gain,
                offset=1e6 * cal_inp.voltage.offset,
                unit="V",
            ),
            current=CalibrationPair(
                gain=1e9 * cal_inp.current.gain,
                offset=1e9 * cal_inp.current.offset,
                unit="A",
            ),
        )
        log.debug("Calibration-Setting of input file:")
        for key, value in self.cal_pru.model_dump(
            exclude_unset=False, exclude_defaults=False
        ).items():
            log.debug("\t%s: %s", key, value)

        self.cal_emu = retrieve_calibration(use_default_cal=cfg.use_cal_default).emulator

        if cfg.time_start is None:
            self.start_time = round(time.time() + 15)
        else:
            self.start_time = cfg.time_start.timestamp()

        # TODO: write gpio-mask

        log_iv = cfg.power_tracing is not None
        log_cap = log_iv and cfg.power_tracing.intermediate_voltage
        self.cnv_pru = ConverterPRUConfig.from_vsrc(
            data=cfg.virtual_source,
            dtype_in=self.reader.get_datatype(),
            log_intermediate_node=log_cap,
        )
        window_size = self.reader.get_window_samples()
        self.hrv_pru = HarvesterPRUConfig.from_vhrv(
            data=cfg.virtual_source.harvester,
            for_emu=True,
            dtype_in=self.reader.get_datatype(),
            window_size=window_size if window_size > 0 else None,
            voltage_step_V=self.reader.get_voltage_step(),
        )
        log.info("Virtual Source will be initialized to:\n%s", cfg.virtual_source)

        self.writer: Writer | None = None
        if cfg.output_path is not None:
            store_path = cfg.output_path.resolve()
            if store_path.is_dir():
                timestamp = datetime.fromtimestamp(self.start_time, tz=local_tz())
                timestring = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
                # ⤷ closest to ISO 8601, avoids ":"
                store_path = store_path / f"emu_{timestring}.h5"
            self.writer = Writer(
                file_path=store_path,
                force_overwrite=cfg.force_overwrite,
                mode=mode,
                datatype=EnergyDType.ivsample,
                cal_data=self.cal_emu,
                compression=cfg.output_compression,
                verbose=get_verbosity(),
            )

        # hard-wire pin-direction until they are configurable
        self._io: TargetIO | None = TargetIO()
        log.info("Setting variable GPIO to INPUT (actuation is not implemented yet)")
        for pin in range(len(target_pins)):
            self._io.set_pin_direction(pin, pdir=True)  # True = Inp

    def __enter__(self) -> Self:
        super().__enter__()

        # TODO: why are there wrappers? just directly access
        super().send_calibration_settings(self.cal_emu)
        super().send_virtual_converter_settings(self.cnv_pru)
        super().send_virtual_harvester_settings(self.hrv_pru)

        super().reinitialize_prus()  # needed for ADCs

        super().set_power_io_level_converter(state=self.cfg.enable_io)
        super().select_port_for_io_interface(self.cfg.io_port)
        super().select_port_for_power_tracking(self.cfg.io_port)
        super().set_aux_target_voltage(self.cfg.voltage_aux, self.cal_emu)

        if self.writer is not None:
            self.stack.enter_context(self.writer)
            # add hostname to file
            self.writer.store_hostname(platform.node().strip())
            self.writer.start_monitors(self.cfg.sys_logging, self.cfg.gpio_tracing)
            self.writer.store_config(self.cfg.model_dump())

        # Preload emulator with data
        self.buffer_segment_count = math.floor(
            commons.BUFFER_IV_INP_SAMPLES_N // self.samples_per_segment
        )
        log.debug("Begin initial fill of IV-Buffer (n=%d segments)", self.buffer_segment_count)
        prog_bar = tqdm(
            total=self.buffer_segment_count,
            desc="Fill IV-Buffer",
            unit="n",
            leave=False,
        )
        for _, dsv, dsc in self.reader.read_buffers(
            end_n=self.buffer_segment_count,
            is_raw=True,
            omit_ts=True,
        ):
            if not self.shared_mem.iv_inp.write(
                data=IVTrace(voltage=dsv, current=dsc),
                cal=self.cal_pru,
                verbose=False,
            ):
                raise BufferError("Not enough space in buffer during initial fill.")
            prog_bar.update(1)
        return self

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.set_power_io_level_converter(state=False)
        time.sleep(2)  # TODO: experimental - for releasing uart-backpressure
        self.stack.close()
        super().__exit__()

    def run(self) -> None:
        if not self.start(self.start_time, wait_blocking=False):
            return
        if self.writer is not None:
            self.writer.check_monitors()
        log.info("waiting %.2f s until start", self.start_time - time.time())
        self.wait_for_start(self.start_time - time.time() + 15)
        self.handle_pru_messages(panic_on_restart=False)
        log.info("shepherd started! T_sys = %f", time.time())

        duration_s = sys.float_info.max
        if self.cfg.duration is not None:
            duration_s = self.cfg.duration.total_seconds()
            log.debug("Duration = %s s (configured runtime)", duration_s)
        if self.reader.runtime_s < duration_s:
            duration_s = self.reader.runtime_s
            log.debug("Duration = %s s (runtime of input file)", duration_s)
        ts_end = self.start_time + duration_s
        set_stop(ts_end)

        # Heartbeat-Message
        prog_bar = tqdm(
            total=duration_s,
            desc="Measurement",
            unit="s",
            leave=False,
        )

        # Main Loop
        ts_data_last = self.start_time
        buffer_segment_last = math.floor(duration_s / self.segment_period_s)
        for _, dsv, dsc in self.reader.read_buffers(
            start_n=self.buffer_segment_count,
            end_n=buffer_segment_last,
            is_raw=True,
            omit_ts=True,
        ):
            # this loop fetches data and tries to fill it into the buffer
            # -> while there is no space it will do other tasks

            # TODO: transform h5_recorders into monitors, make all 3 free threading
            while not self.shared_mem.iv_inp.write(
                data=IVTrace(voltage=dsv, current=dsc),
                cal=self.cal_pru,
                verbose=self.verbose_extra,
            ):
                data_iv = self.shared_mem.iv_out.read(verbose=self.verbose_extra)
                data_gp = self.shared_mem.gpio.read(verbose=self.verbose_extra)
                data_ut = self.shared_mem.util.read(verbose=self.verbose_extra)

                if data_gp and self.writer is not None:
                    self.writer.write_gpio_buffer(data_gp)
                if data_ut and self.writer is not None:
                    self.writer.write_util_buffer(data_ut)

                if data_iv:
                    prog_bar.update(n=data_iv.duration())
                    # TODO: this can't work - with the limiting tracers
                    if data_iv.timestamp() >= ts_end:
                        log.debug("Out of bound timestamp collected -> begin to exit now")
                        break
                    ts_data_last = time.time()
                    if self.writer is not None:
                        try:
                            self.writer.write_iv_buffer(data_iv)
                        except OSError as _xpt:
                            log.error(
                                "Failed to write data to HDF5-File - will STOP! error = %s",
                                _xpt,
                            )
                            return

                self.handle_pru_messages(panic_on_restart=True)
                self.shared_mem.handle_backpressure(iv_inp=True, iv_out=True, gpio=True, util=True)
                if not (data_iv or data_gp or data_ut):
                    if ts_data_last - time.time() > 10:
                        log.error("Main sheep-routine ran dry for 10s, will STOP")
                        break
                    # rest of loop is non-blocking, so we better doze a while if nothing to do
                    time.sleep(self.segment_period_s / 10)

        log.debug("FINISHED supplying input-data -> process remaining buffer")
        force_subchunks = False
        try:
            while True:
                data_iv = self.shared_mem.iv_out.read(verbose=self.verbose_extra)
                data_gp = self.shared_mem.gpio.read(
                    force=force_subchunks, verbose=self.verbose_extra
                )
                data_ut = self.shared_mem.util.read(
                    force=force_subchunks, verbose=self.verbose_extra
                )
                if data_gp and self.writer is not None:
                    self.writer.write_gpio_buffer(data_gp)
                if data_ut and self.writer is not None:
                    self.writer.write_util_buffer(data_ut)

                if data_iv:
                    prog_bar.update(n=data_iv.duration())
                    if data_iv.timestamp() >= ts_end:
                        log.debug("Out of bound timestamp collected -> will discard")
                        data_iv = None
                if data_iv:
                    ts_data_last = time.time()
                    if self.writer is not None:
                        self.writer.write_iv_buffer(data_iv)
                self.handle_pru_messages(panic_on_restart=True)
                self.shared_mem.handle_backpressure(iv_inp=False, iv_out=True, gpio=True, util=True)
                if not (data_iv or data_gp or data_ut):
                    if time.time() - ts_data_last > 3:
                        log.info("FINALIZING: Post data-collection ran dry for 3s -> begin to exit now")
                        break
                    force_subchunks = True
                    # rest of loop is non-blocking, so we better doze a while if nothing to do
                    time.sleep(self.segment_period_s / 5)

        except ShepherdPRUError as e:
            # We're done when the PRU has processed all emulation data buffers
            if e.id_num == commons.MSG_STATUS_RESTARTING_ROUTINE:
                log.warning("PRU restarted - samples might be missing")
            else:
                raise ShepherdPRUError from e
        except OSError as _xpt:
            log.error(
                "Failed to write data to HDF5-File - will STOP! error = %s",
                _xpt,
            )
        prog_bar.close()


