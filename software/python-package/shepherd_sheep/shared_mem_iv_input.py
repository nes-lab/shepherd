import mmap
import struct
import time
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from types import TracebackType

import numpy as np
from shepherd_core.data_models.base.calibration import CalibrationSeries
from typing_extensions import Self

from . import commons
from . import sysfs_interface as sysfs
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
        self.ds_time = timestamp_ns
        self.ds_voltage = voltage
        self.ds_current = current

    def __len__(self) -> int:
        if isinstance(self.ds_time, int | None):
            return min(len(self.ds_voltage), len(self.ds_current))
        if isinstance(self.ds_time, np.ndarray):
            return min(len(self.ds_voltage), len(self.ds_current), len(self.ds_time))
        raise TypeError("Got unexpected timestamp type")

    def timestamp_s(self) -> float:
        if isinstance(self.ds_time, int):
            return self.ds_time / 1e9
        if isinstance(self.ds_time, np.ndarray):
            return self.ds_time.item(0) / 1e9
        raise TypeError("Got unexpected timestamp type")

    def timestamp_ns(self) -> int:
        if isinstance(self.ds_time, int):
            return self.ds_time
        if isinstance(self.ds_time, np.ndarray):
            return int(self.ds_time.item(0))
        raise TypeError("Got unexpected timestamp type")

    def duration(self) -> float:
        return len(self) * commons.SAMPLE_INTERVAL_S


class SharedMemIVInput:
    # TODO: it should be possible to optimize further -
    #       data is currently copied twice and modified once
    #       pytables (alternative to h5py) allows mmap -
    #       maybe directly move data?

    # class is designed for the following size layout (mentioned here mostly for crosscheck)
    N_SAMPLES: int = commons.BUFFER_IV_INP_SAMPLES_N
    SIZE_SAMPLE: int = 4 + 4  # V & I
    SIZE_SAMPLES: int = N_SAMPLES * SIZE_SAMPLE
    SIZE_CANARY: int = 4
    SIZE_SECTION: int = 4 + 4 + SIZE_SAMPLES + SIZE_CANARY
    # ⤷ consist of index, samples, canary

    N_BUFFER_CHUNKS_DEF: int = 16
    N_SAMPLES_PER_CHUNK_DEF: int = N_SAMPLES // N_BUFFER_CHUNKS_DEF
    # DURATION_CHUNK_S is dynamic, see below in init
    # Overflow detection
    FILL_GAP: float = 1.0 / N_BUFFER_CHUNKS_DEF
    POLL_INTERVAL: float = (0.5 - FILL_GAP) * commons.BUFFER_IV_INP_INTERVAL_S

    ST_U32 = struct.Struct("=L")
    ST_U64 = struct.Struct("=Q")

    # TODO: something like that would allow automatic processing
    SIZES: Mapping[str, int] = MappingProxyType(
        {
            "idx_pru": 4,
            "idx_sys": 4,
            "samples": N_SAMPLES * 4,
            "canary": 4,
        }
    )

    def __init__(self, mem_map: mmap, n_samples_per_segment: int | None = None) -> None:
        self._mm: mmap = mem_map

        self.n_samples_per_chunk: int = n_samples_per_segment or self.N_SAMPLES_PER_CHUNK_DEF
        self.n_buffer_chunks: int = self.N_SAMPLES // self.n_samples_per_chunk
        self.duration_chunk_s: float = commons.BUFFER_IV_INP_INTERVAL_S / self.n_buffer_chunks

        self.size_by_sys: int = sysfs.get_trace_iv_inp_size()
        self.address: int = sysfs.get_trace_iv_inp_address()
        self.base: int = sysfs.get_trace_iv_inp_address()

        if self.size_by_sys != self.SIZE_SECTION:
            msg = f"[{type(self).__name__}] Size does not match PRU-data"
            raise ValueError(msg)
        if self.POLL_INTERVAL < 0.1:
            msg = (
                f"[{type(self).__name__}] Poll interval for overflow detection too small"
                f" - increase chunk-size"
            )
            raise ValueError(msg)

        self.index_next: int | None = None

        self._offset_base: int = self.address - self.base
        self._offset_idx_pru: int = self._offset_base
        self._offset_idx_sys: int = self._offset_idx_pru + 4
        self._offset_samples: int = self._offset_idx_sys + 4
        self._offset_canary: int = self._offset_samples + self.N_SAMPLES * self.SIZE_SAMPLE

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
            self.n_buffer_chunks,
        )

        self._generate_data_views()

        self.fill_level: float = 0
        self.fill_last: float = 0

    def __enter__(self) -> Self:
        self._mm.seek(self._offset_idx_sys)
        self._mm.write(self.ST_U32.pack(commons.IDX_OUT_OF_BOUND))
        self._mm.seek(self._offset_samples)
        self._mm.write(bytes(bytearray(self.SIZE_SAMPLES)))
        self._mm.seek(self._offset_canary)
        self._mm.write(self.ST_U32.pack(commons.CANARY_VALUE_U32))

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.check_canary()

    def _generate_data_views(self) -> None:
        # this replaces .seek() & .unpack()
        self._mem_canary = np.frombuffer(
            self._mm,
            np.uint32,
            count=1,
            offset=self._offset_canary,
        )
        self._mem_index_pru = np.frombuffer(
            self._mm,
            np.uint32,
            count=1,
            offset=self._offset_idx_pru,
        )
        self._mem_index_sys = np.frombuffer(
            self._mm,
            np.uint32,
            count=1,
            offset=self._offset_idx_sys,
        )

    def check_canary(self) -> None:
        if self._mem_canary[0] != commons.CANARY_VALUE_U32:
            msg = (
                f"[{type(self).__name__}] Canary was harmed! "
                f"It is 0x{self._mem_canary[0]:X}, expected 0x{commons.CANARY_VALUE_U32:X}"
            )
            raise BufferError(msg)

    def get_size_available(self) -> int:
        if self.index_next is None:
            return min(self.N_SAMPLES, self.n_samples_per_chunk)
        index_pru = int(self._mem_index_pru[0])
        if index_pru > self.N_SAMPLES:
            # still out-of-bound (u32_max)
            index_pru = self.N_SAMPLES - 1
        avail_length = (index_pru - self.index_next) % self.N_SAMPLES
        self.fill_level = (self.N_SAMPLES - avail_length) / self.N_SAMPLES
        # detect overflow
        if (self.fill_level <= 0.5 - self.FILL_GAP) and (self.fill_last >= 0.5 + self.FILL_GAP):
            log.error("[%s] Possible overflow detected!", type(self).__name__)
        self.fill_last = self.fill_level
        return min(
            avail_length,
            self.n_samples_per_chunk,
        )
        # min() avoids boundary handling in write function
        # find cleaner solution here to avoid boundary handling

    def can_fit_new_chunk(self) -> bool:
        return self.get_size_available() >= self.n_samples_per_chunk

    def write_iv(
        self,
        data: IVTrace | np.ndarray,
        cal: CalibrationSeries | None,
        *,
        verbose: bool = False,
    ) -> bool:
        len_data = len(data)
        if len_data > self.get_size_available():
            return False  # no available space
        ts_start = time.time() if verbose else None
        if self.index_next is None:
            self.index_next = 0

        if isinstance(data, IVTrace):
            # transform raw ADC data to SI-Units
            # -> the virtual-source-emulator in PRU expects uV and nV
            iv_data = np.empty((len_data, 2), dtype=data.ds_voltage.dtype)
            # option to disable scaling here if already done (performance improvement)
            if cal:
                iv_data[:, 0] = cal.voltage.raw_to_si(data.ds_voltage).astype(np.uint32)
                iv_data[:, 1] = cal.current.raw_to_si(data.ds_current).astype(np.uint32)
            else:
                # interweave data (voltage | current in parallel)
                iv_data[:, 0] = data.ds_voltage[:len_data]
                iv_data[:, 1] = data.ds_current[:len_data]
        else:
            # reshape just to be safe - its cheap
            iv_data = data.reshape((len_data, 2), order="C")

        # Seek buffer location in memory and skip header
        iv_data = np.ascontiguousarray(iv_data)
        offset = self._offset_samples + self.index_next * self.SIZE_SAMPLE
        if self.index_next + len_data <= self.N_SAMPLES:
            self._mm[offset : offset + iv_data.nbytes] = iv_data
            # slice-assignment avoids the extra copy of .tobytes() (also mm.seek & mm.write)
        else:
            cut_position = self.N_SAMPLES - self.index_next
            data_a = iv_data[:cut_position]
            self._mm[offset : offset + data_a.nbytes] = data_a
            if len(iv_data[:cut_position]) + len(iv_data[cut_position:]) > len(iv_data):
                msg = (
                    f"NUMPY specific error "
                    f"{len(iv_data[:cut_position])}, {len(iv_data[cut_position:])}, {len(iv_data)}"
                )
                raise ValueError(msg)
            data_b = iv_data[cut_position:]
            self._mm[self._offset_samples : self._offset_samples + data_b.nbytes] = data_b

        if verbose:
            log.debug(
                "[%s] Sending idx = %d to PRU took %.2f ms, %.2f %%fill",
                type(self).__name__,
                self.index_next,
                1e3 * (time.time() - ts_start),
                100 * self.fill_level,
            )
        # update sys-index
        self.index_next = (self.index_next + len(data)) % self.N_SAMPLES
        self._mem_index_sys[0] = self.index_next
        # NOTE: array-OP replaces mm.seek() & write(.ST_U32.pack(idx)) -> untested
        # TODO: sys-index does not seem to be checked? not writing it causes no error
        if self.index_next < self.n_samples_per_chunk:  # once a cycle
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
        sysfs.write_programmer_datasize(data_size)
        log.debug(
            "[%s] Wrote Firmware-Data to SharedMEM-Buffer (size = %d bytes)",
            type(self).__name__,
            data_size,
        )
        return data_size
