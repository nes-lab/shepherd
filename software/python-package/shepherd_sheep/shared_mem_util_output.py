import mmap
import struct
import time
from dataclasses import dataclass
from types import TracebackType

import numpy as np
from typing_extensions import Self

from . import commons
from . import sysfs_interface as sfs
from .logger import log


@dataclass
class UtilTrace:
    """Python representation of Util buffer

    Over a sync period the PRU logs ticks needed per sample-loop
    """

    def __init__(
        self,
        timestamps_ns: np.ndarray,
        pru0_tsample_mean: np.ndarray,
        pru0_tsample_max: np.ndarray,
        pru1_tsample_max: np.ndarray,
        sample_count: np.ndarray,
    ) -> None:
        self.timestamps_ns = timestamps_ns
        self.pru0_tsample_mean = pru0_tsample_mean
        self.pru0_tsample_max = pru0_tsample_max
        self.pru1_tsample_max = pru1_tsample_max
        self.sample_count = sample_count

    def __len__(self) -> int:
        return min(
            self.timestamps_ns.size,
            self.pru0_tsample_mean.size,
            self.pru0_tsample_max.size,
            self.pru1_tsample_max.size,
        )


class SharedMemUtilOutput:
    # class is designed for the following size layout (mentioned here mostly for crosscheck)
    N_SAMPLES: int = commons.BUFFER_UTIL_SAMPLES_N
    SIZE_SAMPLE: int = 8 + 4 + 4 + 4 + 4  # timestamp, tick- & sample-count
    SIZE_SAMPLES: int = N_SAMPLES * SIZE_SAMPLE
    SIZE_CANARY: int = 4
    SIZE_SECTION: int = 4 + SIZE_SAMPLES + SIZE_CANARY
    # ⤷ consist of index, samples, canary

    N_BUFFER_CHUNKS: int = 20
    N_SAMPLES_PER_CHUNK: int = N_SAMPLES // N_BUFFER_CHUNKS
    # Overflow detection
    FILL_GAP: float = 1.0 / N_BUFFER_CHUNKS
    POLL_INTERVAL: float = (0.5 - FILL_GAP) * commons.BUFFER_UTIL_INTERVAL_S

    def __init__(self, mem_map: mmap) -> None:
        self._mm: mmap = mem_map
        self.size_by_sys: int = sfs.get_trace_util_size()
        self.address: int = sfs.get_trace_util_address()
        self.base: int = sfs.get_trace_iv_inp_address()

        if self.size_by_sys != self.SIZE_SECTION:
            msg = f"[{type(self).__name__}] Size does not match PRU-data"
            raise ValueError(msg)
        if (self.N_SAMPLES % self.N_SAMPLES_PER_CHUNK) != 0:
            msg = f"[{type(self).__name__}] Buffer was not cleanly dividable by chunk-count"
            raise ValueError(msg)
        if self.POLL_INTERVAL < 0.1:
            msg = (
                f"[{type(self).__name__}] Poll interval for overflow detection too small"
                f" - increase chunk-size"
            )
            raise ValueError(msg)

        self.index_next: int = 0

        self._offset_base: int = self.address - self.base
        self._offset_idx_pru: int = self._offset_base
        self._offset_timestamps: int = self._offset_idx_pru + 4
        self._offset_pru0_tsample_max: int = self._offset_timestamps + self.N_SAMPLES * 8
        self._offset_pru0_tsample_sum: int = self._offset_pru0_tsample_max + self.N_SAMPLES * 4
        self._offset_sample_count: int = self._offset_pru0_tsample_sum + self.N_SAMPLES * 4
        self._offset_pru1_tsample_max: int = self._offset_sample_count + self.N_SAMPLES * 4
        self._offset_canary: int = self._offset_pru1_tsample_max + self.N_SAMPLES * 4

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

        self.warn_counter: int = 10

    def __enter__(self) -> Self:
        # TODO: there should also be alternative access: _mm[a:b] = b'...'
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

    def get_size_available(self) -> int:
        # determine current fill-level
        self._mm.seek(self._offset_idx_pru)
        index_pru: int = struct.unpack("=L", self._mm.read(4))[0]
        avail_length = (index_pru - self.index_next) % self.N_SAMPLES
        self.fill_level = avail_length / self.N_SAMPLES
        # detect overflow
        if (self.fill_level <= 0.5 - self.FILL_GAP) and (self.fill_last >= 0.5 + self.FILL_GAP):
            log.error("[%s] Possible overflow detected!", type(self).__name__)
        self.fill_last = self.fill_level
        return avail_length

    def read(self, *, force: bool = False, verbose: bool = False) -> UtilTrace | None:
        avail_length = self.get_size_available()
        if (avail_length < 1) or (not force and (avail_length < self.N_SAMPLES_PER_CHUNK)):
            return None  # nothing to do

        # adjust read length to stay within chunk-size and also consider end of ring-buffer
        read_length = min(avail_length, self.N_SAMPLES_PER_CHUNK, self.N_SAMPLES - self.index_next)

        if self.fill_level > 0.8:
            log.warning(
                "[%s] Fill-level critical (80%%)",
                type(self).__name__,
            )
        if verbose:
            log.debug(
                "[%s] Retrieving index %4d, len %d, @%.3f sys_ts, %.2f %%fill",
                type(self).__name__,
                self.index_next,
                read_length,
                time.time(),
                100 * self.fill_level,
            )
        # prepare & fetch data
        sample_count = np.frombuffer(
            self._mm,
            np.uint32,
            count=read_length,
            offset=self._offset_sample_count + self.index_next * 4,
        )
        sample_count_safe = sample_count
        sample_count_safe[sample_count_safe < 1] = 1

        data = UtilTrace(
            timestamps_ns=np.frombuffer(
                self._mm,
                np.uint64,
                count=read_length,
                offset=self._offset_timestamps + self.index_next * 8,
            ),
            pru0_tsample_max=np.frombuffer(
                self._mm,
                np.uint32,
                count=read_length,
                offset=self._offset_pru0_tsample_max + self.index_next * 4,
            ),
            pru1_tsample_max=np.frombuffer(
                self._mm,
                np.uint32,
                count=read_length,
                offset=self._offset_pru1_tsample_max + self.index_next * 4,
            ),
            pru0_tsample_mean=np.frombuffer(
                self._mm,
                np.uint32,
                count=read_length,
                offset=self._offset_pru0_tsample_sum + self.index_next * 4,
            )
            / sample_count_safe,
            sample_count=sample_count,
        )
        # TODO: segment should be reset to ZERO to better detect errors
        self.index_next = (self.index_next + read_length) % self.N_SAMPLES
        self.check_status(data, verbose=verbose)

        if self.index_next < self.N_SAMPLES_PER_CHUNK:  # once a cycle
            self.check_canary()

        return data

    def check_status(self, data: UtilTrace, *, verbose: bool = False) -> None:
        # TODO: cleanup, every crit-instance should be reported
        util_mean_val = data.pru0_tsample_mean.mean() * 100 / commons.SAMPLE_INTERVAL_NS
        util_max_val = data.pru0_tsample_max.max() * 100 / commons.SAMPLE_INTERVAL_NS
        util_mean_crit = util_mean_val > 95.0
        util_max_crit = util_max_val >= 100.0

        if (self.warn_counter > 0) and (util_mean_crit or util_max_crit):
            log.warning(
                "Pru0-Util: mean = %.3f %%, max = %.3f %% "
                "-> WARNING: probably broken real-time-condition",
                util_mean_val,
                util_max_val,
            )
            self.warn_counter -= 1
            if self.warn_counter == 0:
                # silenced because this is causing overhead without a cape
                log.warning("Pru0-Util-Warning is silenced now! Is emu running without a cape?")
        elif verbose:
            log.info(
                "Pru0-Util = [%.3f, %.3f] %% (mean,max); "
                "sample-count [%d, %d] n (min,max); "
                "tGpioMax = %d ns",
                util_mean_val,
                util_max_val,
                data.sample_count.min(),
                data.sample_count.max(),
                data.pru1_tsample_max.max(),
            )
