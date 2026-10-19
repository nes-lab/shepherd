import copy
import threading
from queue import Queue
from types import TracebackType

import h5py
import ryaml
from shepherd_core.data_models.content.enum_datatypes import Compression

from .h5_monitor_abc import Monitor
from .hardware_target_io import GPIO_LOG_BIT_POSITIONS
from .logger import log
from .shared_mem_gpio_output import GPIOTrace
from .shared_mem_gpio_output import SharedMemGPIOOutput


class GpioRecorder(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
    ) -> None:
        super().__init__(
            target,
            compression,
            poll_interval=0.1,
            chunk_size=SharedMemGPIOOutput.N_SAMPLES_PER_CHUNK,
            increment_factor=100,
            # NOTE: 5x to 10x has significantly worse performance
        )

        self.ds_value = self.data.create_dataset(
            name="value",
            shape=(self.increment_size,),
            dtype="u2",
            maxshape=(None,),
            chunks=(self.chunk_size,),
            compression=compression,
            # shuffle does not help here,
            # even for optimal 1-bit changes (size unchanged, performance-hit)
        )
        self.ds_value.attrs["unit"] = "n"
        self.ds_value.attrs["description"] = ryaml.dumps(GPIO_LOG_BIT_POSITIONS)

        self.dropped_data = False
        self.queue_size = int(
            180e6 / (SharedMemGPIOOutput.SIZE_SAMPLE * SharedMemGPIOOutput.N_SAMPLES_PER_CHUNK)
        )  # MB
        self.queue = Queue(maxsize=self.queue_size)
        log.debug("[%s] starts with size_queue = %d", type(self).__name__, self.queue_size)
        self.thread = threading.Thread(
            target=self.thread_fn,
            daemon=True,
            name="Shp.H5Rec.Gpio",
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
        self.ds_value.resize((self.position,))
        super().__exit__()

    def write(self, data: GPIOTrace) -> None:
        if self.queue.full():
            self.dropped_data = True
            return  # drop package
        data_new = copy.deepcopy(data)
        self.queue.put(data_new)

    def thread_fn(self) -> None:
        while not self.event.is_set():
            if self.queue.empty():
                self.event.wait(self.poll_interval)  # rate limiter
            else:
                data = self.queue.get()
                len_new = len(data)
                if len_new < 1:
                    return
                pos_end = self.position + len_new
                data_length = len(self.ds_time)  # a faster .shape[0]
                if pos_end >= data_length:
                    data_length += max(self.increment_size, pos_end - data_length)
                    self.ds_time.resize((data_length,))
                    self.ds_value.resize((data_length,))
                self.ds_time[self.position : pos_end] = data.timestamps_ns
                self.ds_value[self.position : pos_end] = data.bitmasks
                self.position = pos_end

        log.debug("[%s] thread ended itself", type(self).__name__)

    def check_status(self) -> None:
        return

    def preshape_by_runtime(self, value_s: float) -> None:
        """Reshape some datasets with predictable length."""
        # leave as is
