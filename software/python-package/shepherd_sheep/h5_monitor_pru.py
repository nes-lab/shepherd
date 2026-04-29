import threading
from types import TracebackType

import h5py
from shepherd_core.data_models.content.enum_datatypes import Compression

from . import commons
from .h5_monitor_abc import Monitor
from .logger import log
from .shared_mem_util_output import SharedMemUtilOutput
from .shared_mem_util_output import UtilTrace


class PruMonitor(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        source: SharedMemUtilOutput,
        compression: Compression | None = Compression.default,
        timestamp_end_ns: int | None = None,
        *,
        verbose: bool = False,
    ) -> None:
        super().__init__(target, compression, poll_interval=1.01)

        self.data.create_dataset(
            name="values",
            shape=(self.increment, 3),
            dtype="u2",
            maxshape=(None, 3),
            chunks=(self.increment, 3),
            compression=compression,
        )

        self.data["values"].attrs["unit"] = "ns, ns, ns"
        self.data["values"].attrs["description"] = (
            "pru0_vsrc_tsample_mean [ns], "
            "pru0_vsrc_tsample_max [ns], "
            f"pru1_gpio_tsample_max [ns/{commons.SAMPLE_INTERVAL_NS}ns]"
        )
        # reset increment AFTER creating all dsets are created
        self.increment = 1000  # 100 s
        # TODO: make dependent from commons.BUFFER_GPIO_SAMPLES_N
        self.source = source
        self.timestamp_end_ns = timestamp_end_ns
        self.verbose = verbose

        self.thread = threading.Thread(
            target=self.thread_fn, daemon=True, name="Shp.H5Mon.PRU_UTIL"
        )
        self.thread.start()

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=2 * self.poll_interval)
            if self.thread.is_alive():
                log.error(
                    "[%s] thread failed to end itself - will delete that instance",
                    type(self).__name__,
                )
            self.thread = None
        self.data["values"].resize((self.position, 3))
        super().__exit__()

    def write(self, data: UtilTrace) -> None:
        """This data allows to
        - reconstruct timestamp-stream later (runtime-optimization, 33% less load)
        - identify critical pru0-timeframes
        """
        len_new = len(data)
        if len_new < 1:
            return
        pos_end = self.position + len_new
        data_length = self.data["time"].shape[0]
        if pos_end >= data_length:
            data_length += max(self.increment, pos_end - data_length)
            self.data["values"].resize((data_length, 3))
            self.data["time"].resize((data_length,))
        self.data["time"][self.position : pos_end] = data.timestamps_ns
        self.data["values"][self.position : pos_end, 0] = data.pru0_tsample_mean
        self.data["values"][self.position : pos_end, 1] = data.pru0_tsample_max
        self.data["values"][self.position : pos_end, 2] = data.pru1_tsample_max
        self.position = pos_end

    def thread_fn(self) -> None:
        while not self.event.wait(self.poll_interval):  # rate limiter & exit
            util = self.source.read(
                timestamp_end_ns=self.timestamp_end_ns,
                verbose=self.verbose,
            )
            if util is not None:
                self.write(util)
