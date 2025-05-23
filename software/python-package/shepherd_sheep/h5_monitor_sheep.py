import threading
import time
from types import TracebackType

import h5py
from shepherd_core import Compression

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
        self.data.create_dataset(
            name="message",
            shape=(self.increment,),
            dtype=h5py.special_dtype(vlen=str),
            maxshape=(None,),
            chunks=True,
        )
        self.data.create_dataset(
            name="level",
            shape=(self.increment,),
            dtype="uint8",
            maxshape=(None,),
            chunks=True,
        )
        self.data["level"].attrs["unit"] = "n"
        self.data["level"].attrs["description"] = (
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
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=2 * self.poll_interval)
            if self.thread.is_alive():
                log.error(
                    "[%s] thread failed to end itself - will delete that instance",
                    type(self).__name__,
                )
            self.thread = None
        self.data["message"].resize((self.position,))
        self.data["level"].resize((self.position,))
        super().__exit__()

    def thread_fn(self) -> None:
        while not self.event.is_set():
            if self.queue.qsize() > 0:
                rec = self.queue.get()
                try:
                    data_length = self.data["time"].shape[0]
                    if self.position >= data_length:
                        data_length += self.increment
                        self.data["time"].resize((data_length,))
                        self.data["message"].resize((data_length,))
                        self.data["level"].resize((data_length,))
                except RuntimeError:
                    log.error(
                        "[%s] HDF5-File unavailable - will stop",
                        type(self).__name__,
                    )
                    break
                self.data["time"][self.position] = int(rec.created * 1e9)
                self.data["message"][self.position] = rec.message
                self.data["level"][self.position] = rec.levelno
                self.position += 1
            else:
                self.event.wait(self.poll_interval)  # rate limiter
        log.debug("[%s] thread ended itself", type(self).__name__)
