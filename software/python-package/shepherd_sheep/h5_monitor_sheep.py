import threading
import time
from types import TracebackType

import h5py
from shepherd_core.data_models.content.enum_datatypes import Compression

from .h5_monitor_abc import Monitor
from .logger import get_message_queue
from .logger import log


class SheepMonitor(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
    ) -> None:
        super().__init__(target, compression, poll_interval=0.25)
        self.queue = get_message_queue()
        self.ds_message = self.data.create_dataset(
            name="message",
            shape=(self.ds_size,),
            dtype=h5py.special_dtype(vlen=str),
            maxshape=(None,),
            chunks=(self.chunk_size,),
        )
        self.ds_level = self.data.create_dataset(
            name="level",
            shape=(self.ds_size,),
            dtype="uint8",
            maxshape=(None,),
            chunks=(self.chunk_size,),
        )
        self.ds_level.attrs["unit"] = "n"
        self.ds_level.attrs["description"] = (
            "from [0..+10..50] = [NOTSET, DEBUG, INFO, WARNING, ERROR, CRITICAL]"
        )

        self.thread = threading.Thread(
            target=self.thread_fn,
            daemon=True,
            name="Shp.H5Mon.Sheep",
        )
        self.thread.start()

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        time.sleep(2 * self.poll_interval)  # give thread time to write last bits
        self.shutdown_thread()
        self.ds_message.resize((self.position,))
        self.ds_level.resize((self.position,))
        super().__exit__()

    def thread_fn(self) -> None:
        while not self.event.is_set():
            if self.queue.empty():
                self.event.wait(self.poll_interval)  # rate limiter
            else:
                self.event.wait(self.rate_limit_interval)
                rec = self.queue.get()
                try:
                    if self.position >= self.ds_size:
                        self.ds_size += self.increment_size
                        self.ds_time.resize((self.ds_size,))
                        self.ds_message.resize((self.ds_size,))
                        self.ds_level.resize((self.ds_size,))
                except RuntimeError:
                    log.error(
                        "[%s] HDF5-File unavailable - will stop",
                        type(self).__name__,
                    )
                    break
                self.ds_time[self.position] = int(rec.created * 1e9)
                self.ds_message[self.position] = rec.message
                self.ds_level[self.position] = rec.levelno
                self.position += 1

        log.debug("[%s] thread ended itself", type(self).__name__)

    def check_status(self) -> None:
        return

    def preshape_by_runtime(self, value_s: float) -> None:
        """Reshape some datasets with predictable length."""
        # leave as is
