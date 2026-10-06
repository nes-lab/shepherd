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
            increment=10 * SharedMemUtilOutput.N_SAMPLES_PER_CHUNK,
        )

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

        self.dropped_data = False
        self.direct = False
        if not self.direct:
            self.queue_size = int(
                10e6 / (SharedMemUtilOutput.SIZE_SAMPLE * SharedMemUtilOutput.N_SAMPLES_PER_CHUNK)
            )  # MB
            self.queue = Queue(maxsize=self.queue_size)
            log.info("[%s] starts with size_queue = %d", type(self).__name__, self.queue_size)
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
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=20 * self.poll_interval)
            if self.thread.is_alive():
                log.warning(
                    "[%s] thread failed to end itself - will delete that instance",
                    type(self).__name__,
                )
            self.thread = None
        if hasattr(self, "queue"):
            # py313 has shutdown for queue
            pass
        if self.dropped_data:
            log.error("[%s] dropped data due to backpressure", type(self).__name__)
        self.data["values"].resize((self.position, 3))
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
        self.queue.put(data)

    def write_to_file(self, data: UtilTrace) -> None:
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
        while not self.event.is_set():
            if self.queue.empty():
                self.event.wait(self.poll_interval)  # rate limiter
            else:
                self.write_to_file(self.queue.get())
        log.debug("[%s] thread ended itself", type(self).__name__)

    def check_status(self) -> None:
        return
