import math
import platform
import sys
import time
from contextlib import ExitStack
from datetime import datetime
from types import TracebackType

from shepherd_core.data_models.base.calibration import CalibrationEmulator
from shepherd_core.data_models.base.calibration import CalibrationPair
from shepherd_core.data_models.base.calibration import CalibrationSeries
from shepherd_core.data_models.base.timezone import local_tz
from shepherd_core.data_models.content.enum_datatypes import EnergyDType
from shepherd_core.data_models.content.virtual_harvester_config_pru import HarvesterPRUConfig
from shepherd_core.data_models.content.virtual_source_config_pru import ConverterPRUConfig
from shepherd_core.data_models.content.virtual_storage_config_pru import StoragePRUConfig
from shepherd_core.data_models.experiment import PowerTracing
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.testbed import TargetPort
from shepherd_core.reader import Reader as CoreReader
from tqdm import tqdm
from typing_extensions import Self

from . import commons
from .eeprom import retrieve_calibration
from .h5_writer import Writer
from .hardware_target_io import TargetIO
from .hardware_target_io import target_pins
from .logger import get_verbosity
from .logger import log
from .shared_mem_iv_input import IVTrace
from .shepherd_io import ShepherdIO
from .shepherd_io import ShepherdPRUError
from .sysfs_interface import check_pru_applied_settings
from .sysfs_interface import get_state
from .sysfs_interface import reset_pru_applied_settings
from .sysfs_interface import set_stop


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
            log.error("Input-File has wrong mode (%s != harvester)", self.reader.get_mode())

        self.samples_per_segment = self.reader.CHUNK_SAMPLES_N
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
        # TODO: set cal_pru to None if input already scaled to PRU
        log.debug("Calibration-Setting of input file:")
        for key, value in self.cal_pru.model_dump(
            exclude_unset=False, exclude_defaults=False
        ).items():
            log.debug("\t%s: %s", key, value)

        self.cal_emu = retrieve_calibration(
            use_default_cal=cfg.use_cal_default,
            # TODO: unhandled edge case if aux is selected?
            # NOTE: shouldn't the logic be contained as property in EmulationTask?
        ).emulator

        if cfg.time_start is None:
            self.start_time = round(time.time() + 15)
        else:
            self.start_time = round(cfg.time_start.timestamp())

        # TODO: write gpio-mask

        trace_iv = isinstance(cfg.power_tracing, PowerTracing)
        trace_cap = trace_iv and cfg.power_tracing.intermediate_voltage
        cal_file = self.cal_emu
        if trace_cap:
            # propagate internal PRUs fixed point scaling
            cal_v = CalibrationPair(gain=1e-6, unit="V")  # uV based
            cal_c = CalibrationPair(gain=1e-9, unit="A")  # nA based
            cal_file = CalibrationEmulator(
                dac_V_A=cal_v,
                dac_V_B=cal_v,
                adc_C_A=cal_c,
                adc_C_B=cal_c,
            )

        self.cnv_pru = ConverterPRUConfig.from_vsrc(
            data=cfg.virtual_source,
            dtype_in=self.reader.get_datatype(),
            log_intermediate_node=trace_cap,
        )
        window_size = self.reader.get_window_samples()
        self.hrv_pru = HarvesterPRUConfig.from_vhrv(
            data=cfg.virtual_source.harvester,
            for_emu=True,
            dtype_in=self.reader.get_datatype(),
            window_size=window_size if window_size > 0 else None,
            voltage_step_V=self.reader.get_voltage_step(),
        )
        self.storage_pru = StoragePRUConfig.from_vstorage(data=cfg.virtual_source.storage)
        log.info("Virtual Source will be initialized to:\n%s", cfg.virtual_source)

        self.writer: Writer | None = None
        if cfg.output_path is not None:
            store_path = cfg.output_path.resolve()
            if store_path.is_dir():
                timestamp = datetime.fromtimestamp(self.start_time, tz=local_tz())
                timestring = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
                # ⤷ closest to ISO 8601, avoids ":"
                store_path /= f"emu_{timestring}.h5"
            self.writer = Writer(
                file_path=store_path,
                force_overwrite=cfg.force_overwrite,
                mode=self.component,  # is a cleaned up mode
                datatype=EnergyDType.ivsample,
                cal_data=CalibrationSeries.from_cal(
                    cal_file, emu_port_a=(cfg.pwr_port == TargetPort.A)
                ),
                sample_rate=cfg.power_tracing.samplerate if trace_iv else None,
                only_power=cfg.power_tracing.only_power if trace_iv else False,
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

        # TODO: why use wrappers? just directly access
        super().send_calibration_settings(self.cal_emu)
        super().send_virtual_storage_settings(self.storage_pru)
        super().send_virtual_converter_settings(self.cnv_pru)
        super().send_virtual_harvester_settings(self.hrv_pru)
        reset_pru_applied_settings()  # check later if applied
        super().reinitialize_prus()  # needed for ADCs

        super().set_power_io_level_converter(state=self.cfg.enable_io)
        super().select_port_for_io_interface(self.cfg.io_port)
        super().select_port_for_power_tracking(self.cfg.io_port)
        super().set_aux_target_voltage(self.cfg.voltage_aux, self.cal_emu)

        if self.writer is not None:
            self.stack.enter_context(self.writer)
            # add hostname to file
            self.writer.store_hostname(platform.node().strip())
            self.writer.start_monitors(self.cfg.sys_logging, self.cfg.uart_logging)
            self.writer.store_config(self.cfg)

        # Prefill emulator with data
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
        for _, dsv, dsc in self.reader.read(
            end_n=self.buffer_segment_count,
            is_raw=True,
            omit_timestamps=True,
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
        while self.wait_for_start(5, raising=False):
            # pre-experiment loop that collects pru-util values
            data_ut = self.shared_mem.util.read(verbose=self.verbose_extra)
            if data_ut and self.writer is not None:
                self.writer.write_util_buffer(data_ut)
            if time.time() > self.start_time + 10:
                raise TimeoutError("Timed out waiting for Start")

        self.handle_pru_messages(panic_on_restart=False)
        log.info(">>> Shepherd started! <<< T_sys = %f", time.time())
        if not check_pru_applied_settings():
            log.error("PRU has NOT yet applied the settings!")

        duration_s = sys.float_info.max
        if self.cfg.duration is not None:
            duration_s = int(self.cfg.duration.total_seconds())
            log.debug("Duration = %.1f s (configured runtime)", duration_s)
        if self.reader.runtime_s < duration_s:
            duration_s = int(self.reader.runtime_s)
            log.debug("Duration = %.1f s (runtime of input file)", duration_s)
        ts_end = self.start_time + duration_s
        ts_end_ns = int(ts_end * 1e9)
        set_stop(ts_end)

        prog_bar = tqdm(
            total=int(10 * duration_s),
            desc="Measurement",
            unit="n",
            leave=False,
        )

        # Main Loop
        ts_data_last = self.start_time
        buffer_segment_last = math.floor(duration_s / self.segment_period_s)
        for _, dsv, dsc in self.reader.read(
            start_n=self.buffer_segment_count,
            end_n=buffer_segment_last,
            is_raw=True,
            omit_timestamps=True,
        ):
            # this loop fetches data and tries to fill it into the buffer
            # -> while there is no space it will do other tasks

            while not self.shared_mem.iv_inp.write(
                data=IVTrace(voltage=dsv, current=dsc),
                cal=self.cal_pru,
                verbose=self.verbose_extra,
            ):
                data_iv = self.shared_mem.iv_out.read(verbose=self.verbose_extra)
                data_gp = self.shared_mem.gpio.read(verbose=self.verbose_extra)
                data_ut = self.shared_mem.util.read(
                    timestamp_end_ns=ts_end_ns, verbose=self.verbose_extra
                )

                if data_gp and self.writer is not None:
                    self.writer.write_gpio_buffer(data_gp)
                if data_ut and self.writer is not None:
                    self.writer.write_util_buffer(data_ut)

                if data_iv:
                    prog_bar.update(n=int(10 * data_iv.duration()))
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
                self.shared_mem.supervise_buffers(iv_inp=True, iv_out=True, gpio=True, util=True)
                if not (data_iv or data_gp or data_ut):
                    # note that util is a criteria in this first loop
                    if ts_data_last - time.time() > 10:
                        log.error("Main sheep-routine ran dry for 10s, will STOP")
                        break
                    # rest of loop is non-blocking, so we better doze a while if nothing to do
                    time.sleep(self.segment_period_s / 10)
                if get_state() == "idle":
                    log.info("PRU-State changed to idle -> will STOP")
                    # TODO: timer in kMod stops PRU to idle -> this should be improved
                    #       a) one command-channel, one report-variable
                    #           (not intertwined like shp_pru_state)
                    #       b) running -> stopped /finish operations -> reset /able to start again
                    break

        log.debug("FINISHED supplying input-data -> process remaining buffer")
        force_subchunks = False
        before_ts_end = True
        try:
            while True:
                data_iv = self.shared_mem.iv_out.read(verbose=self.verbose_extra)
                data_gp = self.shared_mem.gpio.read(
                    force=force_subchunks, verbose=self.verbose_extra
                )
                data_ut = self.shared_mem.util.read(
                    timestamp_end_ns=ts_end_ns, force=force_subchunks, verbose=self.verbose_extra
                )
                if data_gp and self.writer is not None:
                    self.writer.write_gpio_buffer(data_gp)
                if data_ut and self.writer is not None:
                    self.writer.write_util_buffer(data_ut)

                if data_iv:
                    prog_bar.update(n=int(10 * data_iv.duration()))
                    if data_iv.timestamp() > ts_end:
                        log.debug("Out of bound timestamp collected -> will discard")
                        data_iv = None
                if data_iv:
                    ts_data_last = time.time()
                    if self.writer is not None:
                        self.writer.write_iv_buffer(data_iv)
                if before_ts_end and (time.time() > ts_end):
                    log.debug("End of measurement reached -> will collect remaining data")
                    # refresh TS before the routine can run dry
                    # this prevents early exit when power-tracing is disabled
                    ts_data_last = time.time()
                    before_ts_end = False
                self.handle_pru_messages(panic_on_restart=before_ts_end)
                self.shared_mem.supervise_buffers(iv_inp=False, iv_out=True, gpio=True, util=True)
                if not (data_iv or data_gp or data_ut):
                    if not before_ts_end and (time.time() - ts_data_last > 3):
                        log.info("Data-collection ran dry for 3s -> begin to exit now")
                        break
                    force_subchunks = True
                    # rest of loop is non-blocking, so we better doze a while if nothing to do
                    time.sleep(self.segment_period_s / 5)

        except ShepherdPRUError as e:
            # We're done when the PRU has processed all emulation data buffers
            if e.id_num == commons.MSG_STATUS_RESTARTING_ROUTINE:
                if before_ts_end:
                    log.warning("PRU restarted - samples might be missing")
                else:
                    log.debug("PRU restarted")
            else:
                raise ShepherdPRUError from e
        except OSError as _xpt:
            log.error(
                "Failed to write data to HDF5-File - will STOP! error = %s",
                _xpt,
            )
        prog_bar.close()
        # Detect recorder missing start / end
        if self.writer is not None and self.writer.data_pos >= 1:
            gain = self.writer.ds_time.attrs["gain"]
            file_start = self.writer.ds_time[0] * gain
            file_end = self.writer.ds_time[self.writer.data_pos - 1] * gain
            if file_start > self.start_time:
                log.error(
                    "Recorder missed %.3f s IVTrace after start", file_start - self.start_time
                )
            if file_end < ts_end - max(1e-3, 2.0 / self.writer.samplerate_sps):
                log.error("Recorder missed ~ %.3f s IVTrace before end", ts_end - file_end)
