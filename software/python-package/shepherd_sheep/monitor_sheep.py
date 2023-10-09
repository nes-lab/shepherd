import threading
from typing import Optional

import h5py
from shepherd_core import Compression

from .logger import get_message_queue
from .logger import log
from .monitor_abc import Monitor


class SheepMonitor(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Optional[Compression] = Compression.default,
    ):
        super().__init__(target, compression, poll_intervall=0.25)
        self.queue = get_message_queue()
        self.data.create_dataset(
            "message",
            (self.increment,),
            dtype=h5py.special_dtype(vlen=str),
            maxshape=(None,),
            chunks=True,
        )
        self.data.create_dataset(
            "level",
            (self.increment,),
            dtype="uint8",
            maxshape=(None,),
            chunks=True,
        )
        self.data["level"].attrs["unit"] = "n"
        self.data["level"].attrs[
            "description"
        ] = "from [0..+10..50] = [NOTSET, DEBUG, INFO, WARNING, ERROR, CRITICAL]"

        self.thread = threading.Thread(target=self.thread_fn, daemon=True)
        self.thread.start()

    def __exit__(self, *exc):  # type: ignore
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=self.poll_intervall)
            self.thread = None
        self.data["message"].resize((self.position,))
        self.data["level"].resize((self.position,))
        super().__exit__()

    def thread_fn(self) -> None:
        while not self.event.is_set():
            if self.queue.qsize() > 0:
                rec = self.queue.get()
                data_length = self.data["time"].shape[0]
                if self.position >= data_length:
                    data_length += self.increment
                    self.data["time"].resize((data_length,))
                    self.data["message"].resize((data_length,))
                    self.data["level"].resize((data_length,))
                self.data["time"][self.position] = int(rec.created * 1e9)
                self.data["message"][self.position] = rec.message
                self.data["level"][self.position] = rec.levelno
                self.position += 1
            else:
                self.event.wait(self.poll_intervall)  # rate limiter
        log.debug("[%s] thread ended itself", type(self).__name__)
