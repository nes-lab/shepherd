import datetime
import sys
import time
from contextlib import ExitStack

import invoke
from shepherd_core import get_verbose_level
from shepherd_core.data_models.content.virtual_harvester import HarvesterPRUConfig
from shepherd_core.data_models.task import HarvestTask

from . import sysfs_interface
from .eeprom import retrieve_calibration
from .h5_writer import ExceptionRecord
from .h5_writer import Writer
from .logger import log
from .shepherd_io import ShepherdIO
from .shepherd_io import ShepherdIOException


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
    ):
        log.debug("ShepherdHarvester-Init in %s-mode", mode)
        super().__init__(
            mode=mode,
            trace_iv=cfg.power_tracing,
            trace_gpio=None,
        )
        self.cfg = cfg
        self.stack = ExitStack()

        # performance-critical, <4 reduces chatter during main-loop
        self.verbose = get_verbose_level() >= 4

        self.cal_hrv = retrieve_calibration(cfg.use_cal_default).harvester

        if cfg.time_start is None:
            self.start_time = round(time.time() + 10)
        else:
            self.start_time = cfg.time_start.timestamp()

        self.samples_per_buffer = sysfs_interface.get_samples_per_buffer()
        self.samplerate_sps = (
            10**9 * self.samples_per_buffer // sysfs_interface.get_buffer_period_ns()
        )

        self.hrv_pru = HarvesterPRUConfig.from_vhrv(
            data=cfg.virtual_harvester,
            for_emu=False,
            dtype_in=None,
        )

        store_path = cfg.output_path.absolute()
        if store_path.is_dir():
            timestamp = datetime.datetime.fromtimestamp(self.start_time)
            timestring = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
            # ⤷ closest to ISO 8601, avoids ":"
            store_path = store_path / f"hrv_{timestring}.h5"

        self.writer = Writer(
            file_path=store_path,
            mode=mode,
            datatype=cfg.virtual_harvester.get_datatype(),
            window_samples=cfg.virtual_harvester.calc_window_size(for_emu=False),
            cal_data=self.cal_hrv,
            compression=cfg.output_compression,
            force_overwrite=cfg.force_overwrite,
            samples_per_buffer=self.samples_per_buffer,
            samplerate_sps=self.samplerate_sps,
        )

    def __enter__(self):
        super().__enter__()
        super().set_power_state_emulator(False)
        super().set_power_state_recorder(True)

        super().send_virtual_harvester_settings(self.hrv_pru)
        super().send_calibration_settings(self.cal_hrv)

        super().reinitialize_prus()  # needed for ADCs

        self.stack.enter_context(self.writer)
        # add hostname to file

        res = invoke.run("hostname", hide=True, warn=True, in_stream=False)
        # ⤷ in_stream has to be disabled to avoid trouble with pytest
        self.writer["hostname"] = "".join(
            x for x in res.stdout if x.isprintable()
        ).strip()
        self.writer.store_config(self.cfg.dict())
        self.writer.start_monitors(self.cfg.sys_logging)

        # Give the PRU empty buffers to begin with
        time.sleep(1)
        for i in range(self.n_buffers):
            self.return_buffer(i, True)
            time.sleep(0.1 * float(self.buffer_period_ns) / 1e9)
            # ⤷ could be as low as ~ 10us
        return self

    def __exit__(self):
        self.stack.close()
        super().__exit__()

    def return_buffer(self, index: int, verbose: bool = False) -> None:
        """Returns a buffer to the PRU

        After reading the content of a buffer and potentially filling it with
        emulation data, we have to release the buffer to the PRU to avoid it
        running out of buffers.

        :param index: (int) Index of the buffer. 0 <= index < n_buffers
        :param verbose: chatter-prevention, performance-critical computation saver
        """
        super()._return_buffer(index)
        if verbose:
            log.debug("Sent empty buffer #%s to PRU", index)

    def run(self) -> None:
        self.start(self.start_time, wait_blocking=False)

        log.info("waiting %.2f s until start", self.start_time - time.time())
        self.wait_for_start(self.start_time - time.time() + 15)
        log.info("shepherd started!")

        if self.cfg.duration is None:
            ts_end = sys.float_info.max
        else:
            ts_end = self.start_time + self.cfg.duration.total_seconds()

        while True:
            try:
                idx, hrv_buf = self.get_buffer(verbose=self.verbose)
            except ShepherdIOException as e:
                log.warning("Caught an Exception", exc_info=e)

                err_rec = ExceptionRecord(int(time.time() * 1e9), str(e), e.value)
                self.writer.write_exception(err_rec)
                if self.cfg.abort_on_error:
                    raise RuntimeError("Caught unforgivable ShepherdIO-Exception")
                continue

            if (hrv_buf.timestamp_ns / 1e9) >= ts_end:
                break

            self.writer.write_buffer(hrv_buf)
            self.return_buffer(idx, verbose=self.verbose)
