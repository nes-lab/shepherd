import datetime
import platform
import time
from contextlib import ExitStack
from types import TracebackType

from shepherd_core import local_tz
from shepherd_core.data_models.content.virtual_harvester import HarvesterPRUConfig
from shepherd_core.data_models.task import HarvestTask
from tqdm import tqdm
from typing_extensions import Self

from . import commons
from .eeprom import retrieve_calibration
from .h5_writer import Writer
from .logger import get_verbosity
from .logger import log
from .shepherd_io import ShepherdIO
from .shepherd_io import ShepherdPRUError
from .sysfs_interface import set_stop


class ShepherdHarvester(ShepherdIO):
    """API for recording a harvest with shepherd.

    Provides an easy-to-use, high-level interface for recording data with
    shepherd. Configures all hardware and initializes the communication
    with kernel module and PRUs.

    Args:
        cfg: harvester task setting
        mode (str): Should be 'harvester' to record harvesting data
    """

    def __init__(
        self,
        cfg: HarvestTask,
        mode: str = "harvester",
    ) -> None:
        log.debug("ShepherdHarvester-Init in %s-mode", mode)
        super().__init__(
            mode=mode,
            trace_iv=cfg.power_tracing,
            trace_gpio=None,
        )
        self.cfg = cfg
        self.stack = ExitStack()

        # performance-critical, allows deep insight between py<-->pru-communication
        self.verbose_extra = False

        self.cal_hrv = retrieve_calibration(use_default_cal=cfg.use_cal_default).harvester

        if cfg.time_start is None:
            self.start_time = round(time.time() + 10)
        else:
            self.start_time = round(cfg.time_start.timestamp())

        self.hrv_pru = HarvesterPRUConfig.from_vhrv(
            data=cfg.virtual_harvester,
            for_emu=False,
            dtype_in=None,
        )

        store_path = cfg.output_path.resolve()
        if store_path.is_dir():
            timestamp = datetime.datetime.fromtimestamp(self.start_time, tz=local_tz())
            timestring = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
            # ⤷ closest to ISO 8601, avoids ":"
            store_path = store_path / f"hrv_{timestring}.h5"

        self.writer = Writer(
            file_path=store_path,
            mode=mode,
            datatype=cfg.virtual_harvester.get_datatype(),
            window_samples=cfg.virtual_harvester.calc_window_size(for_emu=True),
            cal_data=self.cal_hrv,
            compression=cfg.output_compression,
            force_overwrite=cfg.force_overwrite,
            verbose=get_verbosity(),
        )

    def __enter__(self) -> Self:
        super().__enter__()

        super().send_virtual_harvester_settings(self.hrv_pru)
        super().send_calibration_settings(self.cal_hrv)

        super().reinitialize_prus()  # needed for ADCs

        self.stack.enter_context(self.writer)
        # add hostname to file
        self.writer.store_hostname(platform.node().strip())
        self.writer.store_config(self.cfg.model_dump())
        self.writer.start_monitors(
            sys=self.cfg.sys_logging,
        )

        # Give the PRU empty buffers to begin with
        time.sleep(1)
        return self

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
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

        if self.cfg.duration is None:
            duration_s = 10**6  # s, defaults to ~ 100 days
            log.debug("Duration = %d s (100 days runtime, press ctrl+c to exit)", duration_s)
        else:
            duration_s = self.cfg.duration.total_seconds()
            log.debug("Duration = %.1f s (configured runtime)", duration_s)
        ts_end = self.start_time + duration_s
        set_stop(ts_end)

        prog_bar = tqdm(
            total=int(10 * duration_s),
            desc="Measurement",
            unit="n",
            leave=False,
        )

        ts_data_last = self.start_time
        while True:
            data_iv = self.shared_mem.iv_out.read(verbose=self.verbose_extra)
            data_ut = self.shared_mem.util.read(verbose=self.verbose_extra)
            if data_ut:
                self.writer.write_util_buffer(data_ut)

            if data_iv is not None:
                prog_bar.update(n=int(10 * data_iv.duration()))
                if data_iv.timestamp() > ts_end:
                    log.debug("FINISHED! Out of bound timestamp collected -> begin to exit now")
                    break
                ts_data_last = time.time()
                try:
                    self.writer.write_iv_buffer(data_iv)
                except OSError as _xpt:
                    log.error(
                        "Failed to write data to HDF5-File - will STOP! error = %s",
                        _xpt,
                    )
                    break

            try:
                self.handle_pru_messages(panic_on_restart=True)
            except ShepherdPRUError as _xpt:
                # We're done when the PRU has processed all emulation data buffers
                if _xpt.id_num == commons.MSG_STATUS_RESTARTING_ROUTINE:
                    log.warning("PRU restarted - samples might be missing")
                else:
                    log.error("%s", _xpt)
            self.shared_mem.supervise_buffers(iv_inp=False, iv_out=True, gpio=False, util=True)
            if not (data_iv or data_ut):
                if time.time() - ts_data_last > 5:
                    log.info("Data-collection ran dry for 5s -> begin to exit now")
                    break
                # rest of loop is non-blocking, so we better doze a while if nothing to do
                time.sleep(self.segment_period_s)

        prog_bar.close()
        # Detect recorder missing start / end
        gain = self.writer.ds_time.attrs["gain"]
        file_start = self.writer.ds_time[0] * gain
        file_end = self.writer.ds_time[self.writer.data_pos - 1] * gain
        if file_start > self.start_time:
            log.error("Recorder missed %.3f s IVTrace after start", file_start - self.start_time)
        if file_end < ts_end - 1e-3:
            log.error("Recorder missed %.3f s IVTrace before end", file_end - ts_end)
