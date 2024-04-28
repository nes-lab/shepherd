import time
from types import TracebackType

import h5py
import numpy as np
from shepherd_core import Compression

from .h5_monitor_abc import Monitor
from .logger import log
from .shared_memory import DataBuffer


class PruRecorder(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
    ) -> None:
        super().__init__(target, compression, poll_intervall=0)

        self.data.create_dataset(
            name="values",
            shape=(self.increment, 4),
            dtype="u8",
            maxshape=(None, 4),
            chunks=(self.increment, 4),
            compression=compression,
        )

        self.data["values"].attrs["unit"] = "ns, n, %, %"
        self.data["values"].attrs["description"] = (
            "buffer_timestamp [ns], "
            "buffer_elements [n], "
            "pru0_util_mean [%], "
            "pru0_util_max [%]"
        )
        # reset increment AFTER creating all dsets are created
        self.increment = 1000  # 100 s

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.data["values"].resize((self.position, 4))
        super().__exit__()

    def write(self, buffer: DataBuffer) -> None:
        """this data allows to
        - reconstruct timestamp-stream later (runtime-optimization, 33% less load)
        - identify critical pru0-timeframes
        """
        data_length = self.data["values"].shape[0]
        if self.position >= data_length:
            data_length += self.increment
            self.data["values"].resize((data_length, 4))
            self.data["time"].resize((data_length,))
        self.data["time"][self.position] = int(time.time() * 1e9)
        self.data["values"][self.position, :] = [
            buffer.timestamp_ns,
            len(buffer),
            buffer.util_mean,
            buffer.util_max,
        ]
        self.position += 1

    def add_timestamps(self, data_iv: h5py.Group, tseries: np.ndarray) -> None:
        """Add timestamps to Group - only when previously omitted."""
        # TODO: may be more useful on server -> so move to core-writer
        if data_iv["time"].shape[0] == data_iv["voltage"].shape[0]:
            return  # no action needed
        log.logger.info(
            "[%s] will add timestamps (omitted during run for performance)", type(self).__name__
        )
        self.data["values"].resize((self.position, 4))
        buf_size = np.sum(self.data["values"][: self.position, 1])
        if buf_size == 0:
            return
        data_iv["time"].resize((buf_size,))
        data_pos = 0
        for buf_iter in range(self.position):
            buf_len = self.data["values"][buf_iter, 1]
            if buf_len == 0:
                continue
            data_pos_end = int(data_pos + buf_len)
            buf_ts_ns = self.data["values"][buf_iter, 0]
            data_iv["time"][data_pos:data_pos_end] = tseries + buf_ts_ns
            # TODO: not clean - buf_len is read fresh (dynamic), but self.buf_timeseries is static
            # BUT buf_len is either 0 or the static value
            data_pos = data_pos_end

    def thread_fn(self) -> None:
        raise NotImplementedError
