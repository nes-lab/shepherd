import threading
import time
from types import TracebackType

import h5py
import numpy as np
import psutil
from shepherd_core import Compression

from .h5_monitor_abc import Monitor
from .logger import log


class SysUtilMonitor(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
    ) -> None:
        super().__init__(target, compression, poll_intervall=0.3)
        self.log_interval_ns: int = 1 * (10**9)  # step-size is 1 s
        self.log_timestamp_ns: int = 0

        self.data.create_dataset(
            name="cpu",
            shape=(self.increment,),
            dtype="u1",
            maxshape=(None,),
            chunks=self.increment,
        )
        self.data["cpu"].attrs["unit"] = "%"
        self.data["cpu"].attrs["description"] = "cpu_util [%]"
        self.data.create_dataset(
            name="ram",
            shape=(self.increment, 2),
            dtype="u1",
            maxshape=(None, 2),
            chunks=(self.increment, 2),
        )
        self.data["ram"].attrs["unit"] = "%"
        self.data["ram"].attrs["description"] = "ram_available [%], ram_used [%]"
        self.data.create_dataset(
            name="io",
            shape=(self.increment, 4),
            dtype="u8",
            maxshape=(None, 4),
            chunks=(self.increment, 4),
        )
        self.data["io"].attrs["unit"] = "n"
        self.data["io"].attrs["description"] = (
            "io_read [n], io_write [n], io_read [byte], io_write [byte]"
        )
        self.data.create_dataset(
            name="net",
            shape=(self.increment, 2),
            dtype="u8",
            maxshape=(None, 2),
            chunks=(self.increment, 2),
        )
        self.data["net"].attrs["unit"] = "n"
        self.data["net"].attrs["description"] = "nw_sent [byte], nw_recv [byte]"

        if psutil.disk_io_counters() is None:
            log.info(
                "[%s] will not start - mocked or virtual hardware detected",
                type(self).__name__,
            )
        else:
            self.io_last = np.array(psutil.disk_io_counters()[0:4])  # type: ignore
            self.nw_last = np.array(psutil.net_io_counters()[0:2])
            self.thread = threading.Thread(
                target=self.thread_fn,
                daemon=True,
                name="Shp.H5Mon.Sys",
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
            self.thread.join(timeout=2 * self.poll_intervall)
            if self.thread.is_alive():
                log.error(
                    "[%s] thread failed to end itself - will delete that instance",
                    type(self).__name__,
                )
            self.thread = None
        self.data["cpu"].resize((self.position,))
        self.data["ram"].resize((self.position, 2))
        self.data["io"].resize((self.position, 4))
        self.data["net"].resize((self.position, 2))
        super().__exit__()

    def thread_fn(self) -> None:
        """captures state of system in a fixed interval
            https://psutil.readthedocs.io/en/latest/#cpu
        :return: none
        """
        while not self.event.wait(self.poll_intervall):  # rate limiter & exit
            ts_now_ns = int(time.time() * 1e9)
            if ts_now_ns >= self.log_timestamp_ns:
                data_length = self.data["time"].shape[0]
                if self.position >= data_length:
                    data_length += self.increment
                    self.data["time"].resize((data_length,))
                    self.data["cpu"].resize((data_length,))
                    self.data["ram"].resize((data_length, 2))
                    self.data["io"].resize((data_length, 4))
                    self.data["net"].resize((data_length, 2))
                self.log_timestamp_ns += self.log_interval_ns
                if self.log_timestamp_ns < ts_now_ns:
                    self.log_timestamp_ns = int(time.time() * 1e9)
                self.data["time"][self.position] = ts_now_ns
                self.data["cpu"][self.position] = int(
                    round(psutil.cpu_percent(0)),
                )
                mem_stat = psutil.virtual_memory()[0:3]
                self.data["ram"][self.position, 0:2] = [
                    int(100 * mem_stat[1] / mem_stat[0]),
                    int(mem_stat[2]),
                ]
                io_now = np.array(psutil.disk_io_counters()[0:4])  # type: ignore
                self.data["io"][self.position, :] = io_now - self.io_last
                self.io_last = io_now
                nw_now = np.array(psutil.net_io_counters()[0:2])
                self.data["net"][self.position, :] = nw_now - self.nw_last
                self.nw_last = nw_now
                self.position += 1
                # TODO: add temp, not working:
                #  https://psutil.readthedocs.io/en/latest/#psutil.sensors_temperatures
        log.debug("[%s] thread ended itself", type(self).__name__)
