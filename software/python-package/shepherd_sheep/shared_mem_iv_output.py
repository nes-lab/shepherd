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
    N_SAMPLES: int = commons.BUFFER_IV_OUT_SAMPLES_N
    SIZE_SAMPLE: int = 8 + 4 + 4  # timestamp, V, I
    SIZE_SAMPLES: int = N_SAMPLES * SIZE_SAMPLE
    SIZE_CANARY: int = 4
    SIZE_SECTION: int = 4 + SIZE_SAMPLES + SIZE_CANARY
    # ⤷ consist of index, samples, canary

    N_BUFFER_CHUNKS: int = 30
    N_SAMPLES_PER_CHUNK: int = N_SAMPLES // N_BUFFER_CHUNKS
    DURATION_CHUNK_MS: int = N_SAMPLES_PER_CHUNK * commons.SAMPLE_INTERVAL_NS // 10**6
    # Overflow detection
    FILL_GAP: float = 1.0 / N_BUFFER_CHUNKS
    POLL_INTERVAL: float = (0.5 - FILL_GAP) * commons.BUFFER_IV_OUT_INTERVAL_S

    def __init__(self, mem_map: mmap, cfg: PowerTracing | None, ts_xp_start_ns: int) -> None:
        self._mm: mmap = mem_map
        self.size_by_sys: int = sfs.get_trace_iv_out_size()
        self.address: int = sfs.get_trace_iv_out_address()
        self.base: int = sfs.get_trace_iv_inp_address()

        if self.size_by_sys != self.SIZE_SECTION:
            msg = f"[{type(self).__name__}] Size does not match PRU-data"
            raise ValueError(msg)
        if (self.N_SAMPLES % self.N_SAMPLES_PER_CHUNK) != 0:
            msg = f"[{type(self).__name__}] Buffer was not cleanly dividable by chunk-count"
            raise ValueError(msg)
        if (1000 // self.DURATION_CHUNK_MS) * self.DURATION_CHUNK_MS != 1000:
            msg = f"[{type(self).__name__}] Chunk-duration must fit n ∈ ℕ+ times."  # noqa: RUF001
            raise ValueError(msg)
        if self.DURATION_CHUNK_MS % 100 != 0:
            msg = f"[{type(self).__name__}] Chunk-duration must dividable by 0.1s"
            raise ValueError(msg)
        if self.POLL_INTERVAL < 0.1:
            msg = (
                f"[{type(self).__name__}] Poll interval for overflow detection too small"
                f" - increase chunk-size"
            )
            raise ValueError(msg)

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
            msg = f"[{type(self).__name__}] Canary is not at expected position?!?"
            raise ValueError(msg)

        log.debug(
            "[%s] \t@ %s, size: %d byte, %d elements in %d chunks",
            type(self).__name__,
            f"0x{self.address:08X}",
            # ⤷ not directly in message because of colorizer
            self.SIZE_SECTION,
            self.N_SAMPLES,
            self.N_BUFFER_CHUNKS,
        )

        self.fill_level: float = 0
        self.fill_last: float = 0

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
                "[%s] Tracer time-boundaries set to [%.2f, %.2f] => %.0f s",
                type(self).__name__,
                self.ts_start / 1e9,
                self.ts_stop / 1e9,
                (self.ts_stop - self.ts_start) / 1e9,
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
            msg = (
                f"[{type(self).__name__}] Canary was harmed! "
                f"It is 0x{canary:X}, expected 0x{commons.CANARY_VALUE_U32:X}"
            )
            raise BufferError(msg)

    @staticmethod
    def timedelta_to_ns(delta: timedelta | None, default_s: int = 0) -> int:
        if isinstance(delta, timedelta):
            return int(delta.total_seconds() * 10**9)
        return int(timedelta(seconds=default_s).total_seconds() * 10**9)

    def get_size_available(self) -> int:
        # determine current state
        # TODO: add mode to wait blocking?
        self._mm.seek(self._offset_idx_pru)
        index_pru = struct.unpack("=L", self._mm.read(4))[0]
        avail_length = (index_pru - self.index_next) % self.N_SAMPLES
        self.fill_level = avail_length / self.N_SAMPLES
        # detect overflow
        if (self.fill_level <= 0.5 - self.FILL_GAP) and (self.fill_last >= 0.5 + self.FILL_GAP):
            log.error("[%s] Possible overflow detected!", type(self).__name__)
        self.fill_last = self.fill_level
        return avail_length

    def read(self, *, verbose: bool = False) -> IVTrace | None:
        """Extracts trace from PRU-shared buffer in RAM.

        :param verbose: chatter-prevention, performance-critical computation saver

        Returns: IVTrace if available
        """
        avail_length = self.get_size_available()

        if avail_length < self.N_SAMPLES_PER_CHUNK:
            # nothing to do
            # TODO: abandon segment-idea, read up to pru-index, add force to go below segment_size
            return None

        if self.fill_level > 0.8:
            log.warning(
                "[%s] Fill-level critical (80%%)",
                type(self).__name__,
            )

        timestamps_ns = np.frombuffer(
            self._mm,
            np.uint64,
            count=self.N_SAMPLES_PER_CHUNK,
            offset=self._offset_timestamps + self.index_next * 8,
        )
        pru_timestamp = int(timestamps_ns[0])

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

        # prepare & fetch data
        if (not self.ts_set) or (
            (timestamps_ns[0] <= self.ts_stop) and (timestamps_ns[-1] >= self.ts_start)
        ):
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

        if verbose:
            log.debug(
                "[%s] Retrieving index=%6d, len=%d, ts=%.3f, ts_sys=%.3f, %.2f %%fill",
                type(self).__name__,
                self.index_next,
                self.N_SAMPLES_PER_CHUNK,
                pru_timestamp * 1e-9 - self.xp_start,
                time.time() - self.xp_start,
                100 * self.fill_level,
            )

        # TODO: segment in buffer should be reset to ZERO to better detect errors
        self.index_next = (self.index_next + self.N_SAMPLES_PER_CHUNK) % self.N_SAMPLES

        if self.index_next < self.N_SAMPLES_PER_CHUNK:  # once a cycle
            self.check_canary()

        return data
