"""Abstract base class for monitors"""

import threading
from abc import ABC
from abc import abstractmethod
from types import TracebackType

import h5py
from shepherd_core.data_models.content.enum_datatypes import Compression

from .logger import log


class Monitor(ABC):
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
        poll_interval: float = 0.25,
        chunk_size: int = 100,
        increment_factor: int = 10,
    ) -> None:
        self.data: h5py.Group = target
        self.poll_interval: float = poll_interval
        self.rate_limit_interval: float = 0.1 * poll_interval
        self.position: int = 0
        self.chunk_size: int = chunk_size
        self.increment_size: int = increment_factor * chunk_size
        self.event = threading.Event()
        self.thread: threading.Thread | None = None

        # create time, others have to be created in main class
        if "time" not in self.data:
            self.data.create_dataset(
                name="time",
                shape=(self.increment_size,),
                dtype="u8",
                maxshape=(None,),
                chunks=(self.chunk_size,),
                compression=compression,
                shuffle=True,
            )
            self.data["time"].attrs["unit"] = "s"
            self.data["time"].attrs["description"] = "system time [s] = value * gain + (offset)"
            self.data["time"].attrs["gain"] = 1e-9
            self.data["time"].attrs["offset"] = 0
        log.debug(
            "[%s] Activated (t_poll=%.3fs, chunk_size=%d)",
            type(self).__name__,
            self.poll_interval,
            self.chunk_size,
        )

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.data["time"].resize((self.position,))
        log_fn = log.info if len(self.data["time"]) > 0 else log.debug
        log_fn(
            "[%s] recorded %d events",
            type(self).__name__,
            len(self.data["time"]),
        )

    def shutdown_thread(self) -> None:
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=20 * self.poll_interval)
            if self.thread.is_alive():
                log.warning(
                    "[%s] thread failed to end itself - will delete that instance",
                    type(self).__name__,
                )
            self.thread = None

    @abstractmethod
    def thread_fn(self) -> None:
        pass

    @abstractmethod
    def check_status(self) -> None:
        pass

    def flush_queue(self) -> bool:
        if not hasattr(self, "queue"):
            return True
        if self.queue.qsize() > 20:
            log.info(
                "[%s] flushing %d queue-entries to disk (backpressure)",
                type(self).__name__,
                self.queue.qsize(),
            )
        while not self.queue.empty():
            if self.thread is None or not self.thread.is_alive():
                return False
            self.event.wait(self.poll_interval)
        return True

    @abstractmethod
    def preshape_by_runtime(self, value_s: float) -> None:
        """Reshape some datasets with predictable length."""
