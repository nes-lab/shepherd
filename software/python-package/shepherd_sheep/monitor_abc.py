import threading
from abc import ABC
from abc import abstractmethod
from typing import Optional

import h5py
from shepherd_core import Compression

from .logger import log


class Monitor(ABC):
    def __init__(
        self,
        target: h5py.Group,
        compression: Optional[Compression] = Compression.default,
        poll_intervall: float = 0.25,
    ):
        self.data = target
        self.poll_intervall = poll_intervall
        self.position = 0
        self.increment = 100
        self.event = threading.Event()
        self.thread: Optional[threading.Thread] = None

        # create time, others have to be created in main class
        self.data.create_dataset(
            "time",
            (self.increment,),
            dtype="u8",
            maxshape=(None,),
            chunks=True,
            compression=compression,
        )
        self.data["time"].attrs["unit"] = "s"
        self.data["time"].attrs[
            "description"
        ] = "system time [s] = value * gain + (offset)"
        self.data["time"].attrs["gain"] = 1e-9
        self.data["time"].attrs["offset"] = 0
        log.debug(
            "[%s] was activated",
            type(self).__name__,
        )

    def __exit__(self, *exc):  # type: ignore
        self.data["time"].resize((self.position,))
        log.info(
            "[%s] recorded %d events",
            type(self).__name__,
            self.data["time"].shape[0],
        )

    @abstractmethod
    def thread_fn(self) -> None:
        pass
