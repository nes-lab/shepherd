import mmap
import struct
import time
from dataclasses import dataclass
from types import TracebackType

import numpy as np
from shepherd_core import CalibrationSeries
from typing_extensions import Self

from . import commons
from . import sysfs_interface as sfs
from .logger import log


@dataclass
class IVTrace:
    """Python representation of an IV buffer.

    Containing IV samples with corresponding timestamp and info about any
    detected GPIO edges
    """

    def __init__(
        self,
        voltage: np.ndarray,
        current: np.ndarray,
        timestamp_ns: np.ndarray | int | None = None,
    ) -> None:
        self.timestamp_ns = timestamp_ns
        self.voltage = voltage
        self.current = current

    def __len__(self) -> int:
        if isinstance(self.timestamp_ns, int | None):
            return min(self.voltage.size, self.current.size)
        if isinstance(self.timestamp_ns, np.ndarray):
            return min(self.voltage.size, self.current.size, self.timestamp_ns.size)
        raise TypeError("Got unexpected timestamp type")

    def timestamp(self) -> float:
        if isinstance(self.timestamp_ns, int):
            return self.timestamp_ns / 1e9
        if isinstance(self.timestamp_ns, np.ndarray):
            return self.timestamp_ns.item(0) / 1e9
        raise TypeError("Got unexpected timestamp type")

    def duration(self) -> float:
        return self.__len__() * commons.SAMPLE_INTERVAL_S


class SharedMemIVInput:
    # TODO: it should be possible to optimize further - data is currently copied twice and modified once
    #       pytables (alternative to h5py) allows mmap - maybe we can directly move data?

    # class is designed for the following size layout (mentioned here mostly for crosscheck)
    N_SAMPLES: int = commons.BUFFER_IV_SIZE
    SIZE_SAMPLE: int = 4 + 4  # I & V
    SIZE_SAMPLES: int = N_SAMPLES * SIZE_SAMPLE
    SIZE_CANARY: int = 4
    SIZE_SECTION: int = 4 + 4 + SIZE_SAMPLES + SIZE_CANARY
    # ⤷ consist of index, samples, canary

    N_BUFFER_CHUNKS_DEF: int = 20
    N_SAMPLES_PER_CHUNK_DEF: int = N_SAMPLES // N_BUFFER_CHUNKS_DEF
    # DURATION_CHUNK_MS: int = N_SAMPLES_PER_CHUNK_DEF * commons.SAMPLE_INTERVAL_NS // 10**6

    # TODO: something like that would allow automatic processing
    SIZES: dict[str, int] = {
        "idx_pru": 4,
        "idx_sys": 4,
        "samples": N_SAMPLES * 4,
        "canary": 4,
    }

    def __init__(self, mem_map: mmap, n_samples_per_segment: int | None = None) -> None:
        self._mm: mmap = mem_map

        self.n_samples_per_chunk: int = (
            n_samples_per_segment if n_samples_per_segment else self.N_SAMPLES_PER_CHUNK_DEF
        )
        self.n_buffer_chunks: int = self.N_SAMPLES // self.n_samples_per_chunk

        self.size_by_sys: int = sfs.get_trace_iv_inp_size()
        self.address: int = sfs.get_trace_iv_inp_address()
        self.base: int = sfs.get_trace_iv_inp_address()

        if self.size_by_sys != self.SIZE_SECTION:
            raise ValueError("[%s] Size does not match PRU-data", type(self).__name__)
        if (self.N_SAMPLES % self.n_buffer_chunks) != 0:
            raise ValueError(
                "[%s] Buffer was not cleanly dividable by chunk-count", type(self).__name__
            )

        self.index_next: int | None = None

        self._offset_base: int = self.address - self.base
        self._offset_idx_pru: int = self._offset_base
        self._offset_idx_sys: int = self._offset_idx_pru + 4
        self._offset_samples: int = self._offset_idx_sys + 4
        self._offset_canary: int = self._offset_samples + self.N_SAMPLES * 2 * 4

        if self._offset_canary != self._offset_base + self.SIZE_SECTION - self.SIZE_CANARY:
            raise ValueError("[%s] Canary is not at expected position?!?", type(self).__name__)

        log.debug(
            "[%s] \t@ %s, size: %d byte, %d elements in %d chunks",
            type(self).__name__,
            f"0x{self.address:08X}",
            # ⤷ not directly in message because of colorizer
            self.SIZE_SECTION,
            self.N_SAMPLES,
            self.n_buffer_chunks,
        )

        self.fill_level: float = 0

    def __enter__(self) -> Self:
        self._mm.seek(self._offset_idx_sys)
        self._mm.write(struct.pack("=L", commons.IDX_OUT_OF_BOUND))
        self._mm.seek(self._offset_samples)
        self._mm.write(bytes(bytearray(self.SIZE_SAMPLES)))
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

    def get_free_space(self) -> int:
        if self.index_next is None:
            return min(self.N_SAMPLES, self.n_samples_per_chunk)
        self._mm.seek(self._offset_idx_pru)
        index_pru: int = struct.unpack("=L", self._mm.read(4))[0]
        if index_pru > self.N_SAMPLES:
            # still out-of-bound (u32_max)
            index_pru = 0
        avail_length = (index_pru - self.index_next) % self.N_SAMPLES
        self.fill_level = 100 * (self.N_SAMPLES - avail_length) / self.N_SAMPLES
        return min(
            avail_length,
            self.n_samples_per_chunk,
        )
        # min() avoids boundary handling in write function
        # find cleaner solution here to avoid boundary handling

    def can_fit_new_chunk(self) -> bool:
        return self.get_free_space() >= self.n_samples_per_chunk

    def write(
        self,
        data: IVTrace,
        cal: CalibrationSeries,
        *,
        verbose: bool = False,
    ) -> bool:
        avail_length = self.get_free_space()
        if len(data) > avail_length:
            return False  # no available space
        ts_start = time.time() if verbose else None
        if self.index_next is None:
            self.index_next = 0
        # TODO: This part could be optimized further - write a benchmark
        # transform raw ADC data to SI-Units -> the virtual-source-emulator in PRU expects uV and nV
        data.voltage = cal.voltage.raw_to_si(data.voltage).astype("u4")
        data.current = cal.current.raw_to_si(data.current).astype("u4")
        # interweave data (voltage | current in parallel)
        iv_data = np.empty((2 * len(data),), dtype=data.voltage.dtype)
        iv_data[0::2] = data.voltage[: len(data)]
        iv_data[1::2] = data.current[: len(data)]
        # Seek buffer location in memory and skip header
        self._mm.seek(self._offset_samples + self.index_next * self.SIZE_SAMPLE)
        self._mm.write(iv_data.tobytes())
        # TODO: code does not handle boundaries - !!!!!
        if verbose:
            log.debug(
                "[%s] Sending idx = %d to PRU took %.2f ms, %.2f %%fill",
                type(self).__name__,
                self.index_next,
                1e3 * (time.time() - ts_start),
                self.fill_level,
            )
        # update sys-index
        self.index_next = (self.index_next + len(data)) % self.N_SAMPLES
        self._mm.seek(self._offset_idx_sys)
        self._mm.write(struct.pack("=L", self.index_next))

        if self.index_next == 0:
            self.check_canary()

        return True

    def write_firmware(self, data: bytes) -> int:
        data_size = len(data)
        if data_size > self.SIZE_SAMPLES:
            raise ValueError("Firmware file is larger than the SharedMEM-Buffer")
        if data_size < 1:
            raise ValueError("Firmware file is empty")
        self._mm.seek(self._offset_base)
        self._mm.write(data)
        sfs.write_programmer_datasize(data_size)
        log.debug(
            "[%s] Wrote Firmware-Data to SharedMEM-Buffer (size = %d bytes)",
            type(self).__name__,
            data_size,
        )
        return data_size
