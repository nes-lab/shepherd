import copy
import threading
from queue import Queue
from types import TracebackType

import h5py
from shepherd_core.data_models.content.enum_datatypes import Compression
from shepherd_launcher import log

from . import commons
from .h5_monitor_abc import Monitor
from .shared_mem_util_output import SharedMemUtilOutput
from .shared_mem_util_output import UtilTrace


class PruRecorder(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
    ) -> None:
        super().__init__(
            target,
            compression,
            poll_interval=0.66 * SharedMemUtilOutput.DURATION_CHUNK_S,
            chunk_size=SharedMemUtilOutput.N_SAMPLES_PER_CHUNK,  # 2 s
        )

        self.ds_values = self.data.create_dataset(
            name="values",
            shape=(self.ds_size, 3),
            dtype="u2",
            maxshape=(None, 3),
            chunks=(self.chunk_size, 3),
            compression=compression,
        )
        self.ds_values.attrs["unit"] = "ns, ns, ns"
        self.ds_values.attrs["description"] = (
            "pru0_vsrc_tsample_mean [ns], "
            "pru0_vsrc_tsample_max [ns], "
            f"pru1_gpio_tsample_max [ns/{commons.SAMPLE_INTERVAL_NS}ns]"
        )

        self.dropped_data = False
        self.direct = False
        if not self.direct:
            chunk_size = SharedMemUtilOutput.SIZE_SAMPLE * SharedMemUtilOutput.N_SAMPLES_PER_CHUNK
            self.queue_size = min(int(10e6 / chunk_size), 1000)  # 10 MB max
            self.queue = Queue(maxsize=self.queue_size)
            log.debug("[%s] starts with size_queue = %d", type(self).__name__, self.queue_size)
            self.thread = threading.Thread(
                target=self.thread_fn,
                daemon=True,
                name="Shp.H5Rec.Pru",
            )
            self.thread.start()

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.flush_queue()
        self.shutdown_thread()
        # py313 has shutdown for queue
        if self.dropped_data:
            log.error("[%s] dropped data due to backpressure", type(self).__name__)
        self.ds_values.resize((self.position, 3))
        super().__exit__()

    def write(self, data: UtilTrace) -> None:
        """This data allows to
        - reconstruct timestamp-stream later (runtime-optimization, 33% less load)
        - identify critical pru0-timeframes
        """
        if self.direct:
            self.write_to_file(data)
            return
        if self.queue.full():
            self.dropped_data = True
            return  # drop package
        data_new = copy.deepcopy(data)
        self.queue.put(data_new)

    def write_to_file(self, data: UtilTrace) -> None:
        len_new = len(data)
        if len_new < 1:
            return
        pos_end = self.position + len_new
        if pos_end >= self.ds_size:
            self.ds_size += self.increment_size
            self.ds_values.resize((self.ds_size, 3))
            self.ds_time.resize((self.ds_size,))
        self.ds_time[self.position : pos_end] = data.timestamps_ns
        self.ds_values[self.position : pos_end, 0] = data.pru0_tsample_mean
        self.ds_values[self.position : pos_end, 1] = data.pru0_tsample_max
        self.ds_values[self.position : pos_end, 2] = data.pru1_tsample_max
        self.position = pos_end

    def thread_fn(self) -> None:
        while not self.event.is_set():
            if self.queue.empty():
                self.event.wait(self.poll_interval)  # rate limiter
            else:
                self.write_to_file(self.queue.get())
        log.debug("[%s] thread ended itself", type(self).__name__)

    def check_status(self) -> None:
        return

    def preshape_by_runtime(self, value_s: float) -> None:
        """Reshape some datasets with predictable length."""
        runtime_addition = 30
        datarate_sps = 1.0 / SharedMemUtilOutput.DURATION_SAMPLE_S
        self.ds_size = max(
            len(self.ds_time),
            self.increment_size,
            round(datarate_sps * (runtime_addition + value_s)),
        )
        self.ds_time.resize((self.ds_size,))
        self.ds_values.resize((self.ds_size, 3))
