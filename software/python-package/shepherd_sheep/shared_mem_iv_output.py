import mmap
import struct
import time
from datetime import timedelta
from types import TracebackType

import numpy as np
from shepherd_core.data_models import PowerTracing
from typing_extensions import Self

from . import commons
from . import sysfs_interface as sfs
from .logger import log
from .shared_mem_iv_input import IVTrace


class SharedMemIVOutput:
    # class is designed for the following size layout (mentioned here mostly for crosscheck)
    N_SAMPLES: int = commons.BUFFER_IV_SIZE
    SIZE_SAMPLE: int = 8 + 4 + 4  # timestamp, V, I
    SIZE_SAMPLES: int = N_SAMPLES * SIZE_SAMPLE
    SIZE_CANARY: int = 4
    SIZE_SECTION: int = 4 + SIZE_SAMPLES + SIZE_CANARY
    # ⤷ consist of index, samples, canary

    N_BUFFER_CHUNKS: int = 20
    N_SAMPLES_PER_CHUNK: int = N_SAMPLES // N_BUFFER_CHUNKS
    DURATION_CHUNK_MS: int = N_SAMPLES_PER_CHUNK * commons.SAMPLE_INTERVAL_NS // 10**6

    def __init__(self, mem_map: mmap, cfg: PowerTracing | None, ts_xp_start_ns: int) -> None:
        self._mm: mmap = mem_map
        self.size_by_sys: int = sfs.get_trace_iv_out_size()
        self.address: int = sfs.get_trace_iv_out_address()
        self.base: int = sfs.get_trace_iv_inp_address()

        if self.size_by_sys != self.SIZE_SECTION:
            raise ValueError("[%s] Size does not match PRU-data", type(self).__name__)
        if (self.N_SAMPLES % self.N_SAMPLES_PER_CHUNK) != 0:
            raise ValueError(
                "[%s] Buffer was not cleanly dividable by chunk-count", type(self).__name__
            )

        self.ts_start: int | None = None
        self.ts_stop: int | None = None

        self.index_next: int = 0

        self._offset_base: int = self.address - self.base
        self._offset_idx_pru: int = self._offset_base
        self._offset_timestamps: int = self._offset_idx_pru + 4
        self._offset_voltages: int = self._offset_timestamps + self.N_SAMPLES * 8
        self._offset_currents: int = self._offset_voltages + self.N_SAMPLES * 4
        self._offset_canary: int = self._offset_currents + self.N_SAMPLES * 4

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

        self.xp_start: float = ts_xp_start_ns * 1e-9
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

        self.timestamp_last: int = 0

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
                "[%s] Canary of was harmed! It is 0x%X, expected 0x%X",
                type(self).__name__,
                canary,
                commons.CANARY_VALUE_U32,
            )

    @staticmethod
    def timedelta_to_ns(delta: timedelta | None, default_s: int = 0) -> int:
        if isinstance(delta, timedelta):
            return int(delta.total_seconds() * 10**9)
        return int(timedelta(seconds=default_s).total_seconds() * 10**9)

    def read(self, *, verbose: bool = False) -> IVTrace | None:
        """Extracts trace from PRU-shared buffer in RAM.

        :param verbose: chatter-prevention, performance-critical computation saver

        Returns: IVTrace if available
        """
        # determine current state
        # TODO: add mode to wait blocking?
        self._mm.seek(self._offset_idx_pru)
        index_pru = struct.unpack("=L", self._mm.read(4))[0]
        avail_length = (index_pru - self.index_next) % self.N_SAMPLES
        if avail_length < self.N_SAMPLES_PER_CHUNK:
            # nothing to do
            # TODO: detect overflow!!!
            # TODO: abandon segment-idea, read up to pru-index, add force to go below segment_size
            return None

        fill_level = 100 * avail_length / self.N_SAMPLES
        if fill_level > 80:
            log.warning(
                "[%s] Fill-level critical (80%%)",
                type(self).__name__,
            )

        fetch_all_ts: bool = True  # TODO: move 2 init
        if fetch_all_ts:
            timestamps_ns = np.frombuffer(
                self._mm,
                np.uint64,
                count=self.N_SAMPLES_PER_CHUNK,
                offset=self._offset_timestamps + self.index_next * 8,
            )
            pru_timestamp = int(timestamps_ns[0])
        else:
            self._mm.seek(self._offset_timestamps + self.index_next * 8)
            timestamps_ns = struct.unpack("=Q", self._mm.read(8))[0]
            pru_timestamp = int(timestamps_ns)

        if self.timestamp_last > 0:
            diff_ms = (pru_timestamp - self.timestamp_last) // 10**6
            if pru_timestamp == 0:
                log.error("ZERO      timestamp detected after recv it from PRU")
            if diff_ms < 0:
                log.error(
                    "BACKWARDS timestamp-jump detected after recv it from PRU -> %d ms",
                    diff_ms,
                )
            elif diff_ms < self.DURATION_CHUNK_MS - 5:
                log.error(
                    "TOO SMALL timestamp-jump detected after recv it from PRU -> %d ms",
                    diff_ms,
                )
            elif diff_ms > self.DURATION_CHUNK_MS + 5:
                log.error(
                    "FORWARDS  timestamp-jump detected after recv it from PRU -> %d ms",
                    diff_ms,
                )
        self.timestamp_last = pru_timestamp

        if verbose:
            log.debug(
                "[%s] Retrieving index=%6d, len=%d, ts=%.3f, ts_sys=%.3f, fill%%=%.2f",
                type(self).__name__,
                self.index_next,
                self.N_SAMPLES_PER_CHUNK,
                pru_timestamp * 1e-9 - self.xp_start,
                time.time() - self.xp_start,
                fill_level,
            )

        # prepare & fetch data
        if self.ts_start <= pru_timestamp <= self.ts_stop:
            # TODO: honor boundary - check count + offset
            data = IVTrace(
                voltage=np.frombuffer(
                    self._mm,
                    np.uint32,
                    count=self.N_SAMPLES_PER_CHUNK,
                    offset=self._offset_voltages + self.index_next * 4,
                ),
                current=np.frombuffer(
                    self._mm,
                    np.uint32,
                    count=self.N_SAMPLES_PER_CHUNK,
                    offset=self._offset_currents + self.index_next * 4,
                ),
                timestamp_ns=timestamps_ns,
            )
        else:
            data = None
            log.debug(
                "[%s] Discarded data - out of time-boundary (t_pru = %d).",
                type(self).__name__,
                pru_timestamp,
            )

        # TODO: segment in buffer should be reset to ZERO to better detect errors
        self.index_next = (self.index_next + self.N_SAMPLES_PER_CHUNK) % self.N_SAMPLES

        if self.index_next == 0:
            self.check_canary()

        return data
