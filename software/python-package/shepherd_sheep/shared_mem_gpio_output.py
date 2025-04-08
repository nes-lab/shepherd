import mmap
import struct
import time
from dataclasses import dataclass
from datetime import timedelta
from types import TracebackType

import numpy as np
from shepherd_core.data_models import GpioTracing
from typing_extensions import Self

from . import commons
from . import sysfs_interface as sfs
from .logger import log


@dataclass
class GPIOTrace:
    """Python representation of a GPIO edge buffer

    On detection of an edge, shepherd stores the state of all sampled GPIO pins
    together with the corresponding timestamp
    """

    def __init__(
        self,
        timestamps_ns: np.ndarray,
        bitmasks: np.ndarray,
    ) -> None:
        self.timestamps_ns = timestamps_ns
        self.bitmasks = bitmasks

    def __len__(self) -> int:
        return min(self.timestamps_ns.size, self.bitmasks.size)


class SharedMemGPIOOutput:
    # class is designed for the following size layout (mentioned here mostly for crosscheck)
    N_SAMPLES: int = commons.BUFFER_GPIO_SIZE
    SIZE_SAMPLE: int = 8 + 2  # timestamp & GPIOTrace
    SIZE_SAMPLES: int = N_SAMPLES * SIZE_SAMPLE
    SIZE_CANARY: int = 4
    SIZE_SECTION: int = 4 + SIZE_SAMPLES + SIZE_CANARY
    # ⤷ consist of index, samples, canary

    N_BUFFER_CHUNKS: int = 20
    N_SAMPLES_PER_CHUNK: int = N_SAMPLES // N_BUFFER_CHUNKS

    def __init__(self, mem_map: mmap, cfg: GpioTracing | None, ts_xp_start_ns: int) -> None:
        self._mm: mmap = mem_map
        self.size_by_sys: int = sfs.get_trace_gpio_size()
        self.address: int = sfs.get_trace_gpio_address()
        self.base: int = sfs.get_trace_iv_inp_address()

        if self.size_by_sys != self.SIZE_SECTION:
            raise ValueError("[%s] Size does not match PRU-data", type(self).__name__)
        if (self.N_SAMPLES % self.N_SAMPLES_PER_CHUNK) != 0:
            raise ValueError(
                "[%s] Buffer was not cleanly dividable by chunk-count", type(self).__name__
            )

        self.index_next: int = 0

        self._offset_base: int = self.address - self.base
        self._offset_idx_pru: int = self._offset_base
        self._offset_timestamps: int = self._offset_idx_pru + 4
        self._offset_bitmasks: int = self._offset_timestamps + self.N_SAMPLES * 8
        self._offset_canary: int = self._offset_bitmasks + self.N_SAMPLES * 2

        if self._offset_canary != self._offset_base + self.SIZE_SECTION - self.SIZE_CANARY:
            raise ValueError("[%s] Canary is not at expected position?!?", type(self).__name__)

        log.debug(
            "[%s] \t@ %s, size: %d byte, %d elements in %d chunks",
            type(self).__name__,
            f"0x{self.address:08X}",
            # ⤷ not directly in message because of colorizer
            self.SIZE_SECTION,
            self.N_SAMPLES,
            self.N_BUFFER_CHUNKS,
        )

        self.ts_start: int | None = None
        self.ts_stop: int | None = None
        self.ts_set: bool = False

        if cfg is not None:
            self.ts_set = True
            self.ts_start = ts_xp_start_ns + self.timedelta_to_ns(cfg.delay)
            self.ts_stop = self.ts_start + self.timedelta_to_ns(cfg.duration, default_s=10**6)
            # ⤷ duration defaults to ~ 100 days (10**6 seconds)
            log.debug(
                "[%s] Tracer time-boundaries set to [%.2f, %.2f]",
                type(self).__name__,
                self.ts_start / 1e9,
                self.ts_stop / 1e9,
            )

        # self.timestamp_last: int = 0

    def __enter__(self) -> Self:
        self._mm.seek(self._offset_base)
        self._mm.write(bytes(bytearray(self.SIZE_SECTION - self.SIZE_CANARY)))
        self._mm.seek(self._offset_canary)
        self._mm.write(struct.pack("=L", commons.CANARY_VALUE_U32))

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.check_canary()

    def check_canary(self) -> None:
        self._mm.seek(self._offset_canary)
        canary: int = struct.unpack("=L", self._mm.read(4))[0]
        if canary != commons.CANARY_VALUE_U32:
            raise BufferError(
                "[%s] Canary was harmed! It is 0x%X, expected 0x%X",
                type(self).__name__,
                canary,
                commons.CANARY_VALUE_U32,
            )

    @staticmethod
    def timedelta_to_ns(delta: timedelta | None, default_s: int = 0) -> int:
        if isinstance(delta, timedelta):
            return int(delta.total_seconds() * 10**9)
        return int(timedelta(seconds=default_s).total_seconds() * 10**9)

    def read(self, *, force: bool = False, verbose: bool = False) -> GPIOTrace | None:
        # determine current fill-level
        self._mm.seek(self._offset_idx_pru)
        index_pru: int = struct.unpack("=L", self._mm.read(4))[0]
        avail_length = (index_pru - self.index_next) % self.N_SAMPLES
        if not force and (avail_length < self.N_SAMPLES_PER_CHUNK):
            return None  # nothing to do
        # adjust read length to stay within chunk-size and also consider end of ring-buffer
        read_length = min(avail_length, self.N_SAMPLES_PER_CHUNK, self.N_SAMPLES - self.index_next)
        fill_level = 100 * avail_length / self.N_SAMPLES
        if fill_level > 80:
            log.warning(
                "[%s] Fill-level critical (80%%) - should discard Chunks",
                type(self).__name__,
            )
            # TODO: implement discarding chunks
        if verbose:
            log.debug(
                "[%s] Retrieving index %6d with len %d @sys_ts %.3f, fill%%=%.2f",
                type(self).__name__,
                self.index_next,
                read_length,
                time.time(),
                fill_level,
            )
        # prepare & fetch data
        data = GPIOTrace(
            timestamps_ns=np.frombuffer(
                self._mm,
                np.uint64,
                count=read_length,
                offset=self._offset_timestamps + self.index_next * 8,
            ),
            bitmasks=np.frombuffer(
                self._mm,
                np.uint16,
                count=read_length,
                offset=self._offset_bitmasks + self.index_next * 2,
            ),
        )
        # TODO: filter dataset with self.ts_start_gp <= buffer_timestamp <= self.ts_stop_gp
        # TODO: segment should be reset to ZERO to better detect errors
        self.index_next = (self.index_next + read_length) % self.N_SAMPLES

        if self.index_next == 0:
            self.check_canary()

        return data
