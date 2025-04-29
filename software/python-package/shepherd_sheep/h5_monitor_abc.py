"""Abstract base class for monitors"""

import threading
from abc import ABC
from abc import abstractmethod
from types import TracebackType

import h5py
from shepherd_core import Compression

from .logger import log


class Monitor(ABC):
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
        poll_interval: float = 0.25,
        increment: int = 100,
    ) -> None:
        self.data: h5py.Group = target
        self.poll_interval: float = poll_interval
        self.position: int = 0
        self.increment: int = increment
        self.event = threading.Event()
        self.thread: threading.Thread | None = None

        # create time, others have to be created in main class
        self.data.create_dataset(
            name="time",
            shape=(self.increment,),
            dtype="u8",
            maxshape=(None,),
            chunks=True,
            compression=compression,
        )
        self.data["time"].attrs["unit"] = "s"
        self.data["time"].attrs["description"] = "system time [s] = value * gain + (offset)"
        self.data["time"].attrs["gain"] = 1e-9
        self.data["time"].attrs["offset"] = 0
        log.debug(
            "[%s] was activated",
            type(self).__name__,
        )

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.data["time"].resize((self.position,))
        log.info(
            "[%s] recorded %d events",
            type(self).__name__,
            self.data["time"].shape[0],
        )

    @abstractmethod
    def thread_fn(self) -> None:
        pass
