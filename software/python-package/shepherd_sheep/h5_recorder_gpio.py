import multiprocessing
import threading
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
            increment=SharedMemGPIOOutput.N_SAMPLES_PER_CHUNK,
        )

        self.data.create_dataset(
            name="value",
            shape=(self.increment,),
            dtype="u2",
            maxshape=(None,),
            chunks=(self.increment,),
            compression=compression,
        )
        self.data["value"].attrs["unit"] = "n"
        self.data["value"].attrs["description"] = ryaml.dumps(GPIO_LOG_BIT_POSITIONS)

        self.queue_size = int(
            180e6 / (SharedMemGPIOOutput.SIZE_SAMPLE * SharedMemGPIOOutput.N_SAMPLES_PER_CHUNK)
        )  # MB
        self.queue = multiprocessing.Queue(self.queue_size)
        self.dropped_data = False
        log.info("[%s] starts with size_queue = %d", type(self).__name__, self.queue_size)
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
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=20 * self.poll_interval)
            if self.thread.is_alive():
                log.warning(
                    "[%s] thread failed to end itself - will delete that instance",
                    type(self).__name__,
                )
            self.thread = None
        self.queue.cancel_join_thread()
        self.queue.close()
        if self.dropped_data:
            log.warning("[%s] dropped data due to backpressure", type(self).__name__)
        self.data["value"].resize((self.position,))
        super().__exit__()

    def write(self, data: GPIOTrace) -> None:
        if self.queue.full():
            self.dropped_data = True
            return  # drop package
        self.queue.put(data)

    def thread_fn(self) -> None:
        while not self.queue.empty() or not self.event.wait(self.poll_interval):
            data = self.queue.get()
            len_new = len(data)
            if len_new < 1:
                return
            pos_end = self.position + len_new
            data_length = self.data["time"].shape[0]
            if pos_end >= data_length:
                data_length += max(self.increment, pos_end - data_length)
                self.data["time"].resize((data_length,))
                self.data["value"].resize((data_length,))
            self.data["time"][self.position : pos_end] = data.timestamps_ns
            self.data["value"][self.position : pos_end] = data.bitmasks
            self.position = pos_end
        log.debug("[%s] thread ended itself", type(self).__name__)

    def check_status(self) -> None:
        return
