import threading
import time
from types import TracebackType

import h5py
import numpy as np
import psutil
from shepherd_core.data_models.content.enum_datatypes import Compression

from .h5_monitor_abc import Monitor
from .logger import log


class SysUtilMonitor(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
    ) -> None:
        super().__init__(target, compression, poll_interval=0.3)
        self.log_interval_ns: int = 1 * (10**9)  # step-size is 1 s
        self.log_timestamp_ns: int = 0

        self.ds_cpu = self.data.create_dataset(
            name="cpu",
            shape=(self.increment_size,),
            dtype="u1",
            maxshape=(None,),
            chunks=(self.chunk_size,),
        )
        self.ds_cpu.attrs["unit"] = "%"
        self.ds_cpu.attrs["description"] = "cpu_util [%]"

        self.ds_ram = self.data.create_dataset(
            name="ram",
            shape=(self.increment_size, 2),
            dtype="u1",
            maxshape=(None, 2),
            chunks=(self.chunk_size, 2),
        )
        self.ds_ram.attrs["unit"] = "%"
        self.ds_ram.attrs["description"] = "ram_available [%], ram_used [%]"

        self.ds_io = self.data.create_dataset(
            name="io",
            shape=(self.increment_size, 4),
            dtype="u8",
            maxshape=(None, 4),
            chunks=(self.chunk_size, 4),
        )
        self.ds_io.attrs["unit"] = "n"
        self.ds_io.attrs["description"] = (
            "io_read [n], io_write [n], io_read [byte], io_write [byte]"
        )
        self.ds_net = self.data.create_dataset(
            name="net",
            shape=(self.increment_size, 2),
            dtype="u8",
            maxshape=(None, 2),
            chunks=(self.chunk_size, 2),
        )
        self.ds_net.attrs["unit"] = "n"
        self.ds_net.attrs["description"] = "nw_sent [byte], nw_recv [byte]"

        if psutil.disk_io_counters() is None:
            log.info(
                "[%s] will not start - mocked or virtual hardware detected",
                type(self).__name__,
            )
        else:
            self.io_last = np.array(psutil.disk_io_counters()[0:4])
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
        self.shutdown_thread()
        self.ds_cpu.resize((self.position,))
        self.ds_ram.resize((self.position, 2))
        self.ds_io.resize((self.position, 4))
        self.ds_net.resize((self.position, 2))
        super().__exit__()

    def thread_fn(self) -> None:
        """Captures state of system in a fixed interval
            https://psutil.readthedocs.io/en/latest/#cpu
        :return: none
        """
        while not self.event.wait(self.poll_interval):  # rate limiter & exit
            ts_now_ns = int(time.time() * 1e9)
            if ts_now_ns >= self.log_timestamp_ns:
                data_length = len(self.ds_time)  # a faster .shape[0]
                if self.position >= data_length:
                    data_length += self.increment_size
                    self.ds_time.resize((data_length,))
                    self.ds_cpu.resize((data_length,))
                    self.ds_ram.resize((data_length, 2))
                    self.ds_io.resize((data_length, 4))
                    self.ds_net.resize((data_length, 2))
                self.log_timestamp_ns += self.log_interval_ns
                if self.log_timestamp_ns < ts_now_ns:
                    self.log_timestamp_ns = int(time.time() * 1e9)
                self.ds_time[self.position] = ts_now_ns
                self.ds_cpu[self.position] = round(psutil.cpu_percent(0))
                mem_stat = psutil.virtual_memory()[0:3]
                self.ds_ram[self.position, 0:2] = [
                    int(100 * mem_stat[1] / mem_stat[0]),
                    int(mem_stat[2]),
                ]
                io_now = np.array(psutil.disk_io_counters()[0:4])
                self.ds_io[self.position, :] = io_now - self.io_last
                self.io_last = io_now
                nw_now = np.array(psutil.net_io_counters()[0:2])
                self.ds_net[self.position, :] = nw_now - self.nw_last
                self.nw_last = nw_now
                self.position += 1
                # TODO: add temp, not working:
                #  https://psutil.readthedocs.io/en/latest/#psutil.sensors_temperatures
        log.debug("[%s] thread ended itself", type(self).__name__)

    def check_status(self) -> None:
        return

    def preshape_by_runtime(self, value_s: float) -> None:
        """Reshape some datasets with predictable length."""
        runtime_addition = 30
        datarate_sps = 1
        data_length = max(
            len(self.ds_time),
            self.increment_size,
            round(datarate_sps * (runtime_addition + value_s)),
        )
        self.ds_time.resize((data_length,))
        self.ds_cpu.resize((data_length,))
        self.ds_ram.resize((data_length, 2))
        self.ds_io.resize((data_length, 4))
        self.ds_net.resize((data_length, 2))
