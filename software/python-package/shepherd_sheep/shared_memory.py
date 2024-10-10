import mmap
import os
import struct
import time
from dataclasses import dataclass
from datetime import timedelta
from types import TracebackType

import numpy as np
from shepherd_core import CalibrationSeries
from shepherd_core.data_models import GpioTracing
from shepherd_core.data_models import PowerTracing
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
        if isinstance(self.timestamp_ns, int):
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


@dataclass
class UtilTrace:
    """Python representation of Util buffer

    Over a sync period the PRU the logs ticks needed per sample-loop
    """

    def __init__(
        self,
        timestamps_ns: np.ndarray,
        ticks_max: np.ndarray,
        ticks_mean: np.ndarray,
    ) -> None:
        self.timestamps_ns = timestamps_ns
        self.ticks_max = ticks_max
        self.ticks_mean = ticks_mean

    def __len__(self) -> int:
        return min(self.timestamps_ns.size, self.ticks_mean.size, self.ticks_max.size)


class SharedMemory:  # TODO: rename to RamBuffer, as shared mem is precoined for mem between PRUs
    """Represents shared RAM used to exchange data between PRUs and userspace.

    A large area of contiguous memory is allocated through remoteproc. The PRUs
    have access to this memory and store/retrieve IV data from this area. It is
    one of the two key components in the double-buffered data exchange protocol.
    The userspace application has to map this memory area into its own memory
    space. This is achieved through /dev/mem which allow to map physical memory
    locations into userspace under linux.
    """

    def __init__(
        self,
        trace_iv: PowerTracing | None,
        trace_gpio: GpioTracing | None,
        start_timestamp_ns: int,
        iv_segment_size: int | None = None,
        # TODO: add util-config ??
    ) -> None:
        """Initializes relevant parameters for shared memory area.

        Args:

        """
        self.prev_timestamp: int = 0
        self.pru_warn_counter: int = 10

        # placeholder timestamps for tracers:
        self.ts_start_iv: int = 0
        self.ts_start_gp: int = 0
        self.ts_stop_iv: int = 0
        self.ts_stop_gp: int = 0
        self.ts_unset: bool = True

        # configure tracers
        self.trace_iv = trace_iv
        self.trace_gp = trace_gpio
        self.config_tracers(start_timestamp_ns)

        # With knowledge of structure of each buffer, we calculate its total size
        self.iv_trace_size = (
            # Index & timestamp
            4
            + 8
            # IVSamples
            + commons.BUFFER_IV_SIZE * (4 + 4)
            # Canary
            + 4
        )
        self.gpio_trace_size = (
            # Index
            4
            # timestamps & bitmasks
            + commons.BUFFER_GPIO_SIZE * (8 + 2)
            # canary
            + 4
        )
        self.util_trace_size = (
            # indices
            4
            # timestamps & ticks
            + commons.BUFFER_UTIL_SIZE * (8 + 4 + 4)
            # canary
            + 4
        )
        if self.iv_trace_size != sfs.get_trace_iv_size():
            raise ValueError("Size for IV-Buffer does not match PRU-Version")
        if self.gpio_trace_size != sfs.get_trace_gpio_size():
            raise ValueError("Size for GPIO-Buffer does not match PRU-Version")
        if self.util_trace_size != sfs.get_trace_util_size():
            raise ValueError("Size for Util-Buffer does not match PRU-Version")

        self.iv_trace_index_read = 0
        self.iv_trace_index_write: int | None = None  # dual state to simplify initial fill
        self.iv_trace_index_pru = 0
        self.iv_trace_offset = 0
        self.iv_samples_offset = self.iv_trace_offset + 4 + 8
        self.iv_samples_size = 2 * 4
        self.iv_canary_offset = self.iv_trace_offset + 4 + 8 + commons.BUFFER_IV_SIZE * (4 + 4)

        self.gpio_trace_index = 0
        self.gpio_trace_offset = self.iv_trace_offset + self.iv_trace_size
        self.gpio_timestamps_offset = self.gpio_trace_offset + 4
        self.gpio_bitmasks_offset = self.gpio_trace_offset + 4 + commons.BUFFER_GPIO_SIZE * 8
        self.gpio_canary_offset = self.gpio_trace_offset + 4 + commons.BUFFER_GPIO_SIZE * (8 + 2)

        self.util_trace_index = 0
        self.util_trace_offset = self.gpio_trace_offset + self.gpio_trace_size
        self.util_timestamps_offset = self.util_trace_offset + 4
        self.util_ticks_max_offset = self.util_trace_offset + 4 + commons.BUFFER_UTIL_SIZE * 8
        self.util_ticks_sum_offset = self.util_trace_offset + 4 + commons.BUFFER_UTIL_SIZE * (8 + 4)
        self.util_canary_offset = (
            self.util_trace_offset + 4 + commons.BUFFER_UTIL_SIZE * (8 + 4 + 4)
        )

        if self.iv_canary_offset < self.iv_trace_size:
            raise ValueError("Canary of IV-Buffer is not inside buffer?!?")
        if self.gpio_canary_offset < self.gpio_trace_size:
            raise ValueError("Canary of GPIO-Buffer is not inside buffer?!?")
        if self.util_canary_offset < self.util_trace_size:
            raise ValueError("Canary of Util-Buffer is not inside buffer?!?")

        if self.iv_trace_size <= sfs.get_trace_gpio_address() - sfs.get_trace_iv_address():
            raise ValueError("IV-Buffer does not fit into address-space?!?")
        if self.gpio_trace_size <= sfs.get_trace_util_address() - sfs.get_trace_gpio_address():
            raise ValueError("GPIO-Buffer does not fit into address-space?!?")

        self.iv_trace_timestamp_last = 0
        self.gpio_trace_timestamp_last = 0
        self.util_trace_timestamp_last = 0

        self.buffer_address = sfs.get_trace_iv_address()
        self.buffer_size = self.iv_trace_size + self.gpio_trace_size + self.util_trace_size
        log.debug(
            "Shared RAM-Buffer:\t%s, size: %d byte",
            f"0x{self.buffer_address:08X}",
            # ⤷ not directly in message because of colorizer
            self.buffer_size,
        )
        log.debug("\tIV:\t%d byte", self.iv_trace_size)
        log.debug("\tGPIO:\t%d byte", self.gpio_trace_size)
        log.debug("\tUtil:\t%d byte", self.util_trace_size)

        # introduce buffer-segments to get cleaner chunks
        self.buffer_segment_count = 20
        if iv_segment_size is None:
            self.iv_segment_size = commons.BUFFER_IV_SIZE // self.buffer_segment_count
        elif commons.BUFFER_IV_SIZE % iv_segment_size == 0:
            self.iv_segment_size = iv_segment_size
        else:
            raise ValueError("Size of IV-Buffer-Segment must be integer quotient of buffer-size")
        self.gpio_segment_size = commons.BUFFER_GPIO_SIZE // self.buffer_segment_count
        self.util_segment_size = commons.BUFFER_UTIL_SIZE // self.buffer_segment_count
        if self.iv_segment_size * self.buffer_segment_count != commons.BUFFER_IV_SIZE:
            raise ValueError("IV-Buffer was not cleanly dividable by chunk-count.")
        if self.gpio_segment_size * self.buffer_segment_count != commons.BUFFER_GPIO_SIZE:
            raise ValueError("GPIO-Buffer was not cleanly dividable by chunk-count.")
        if self.util_segment_size * self.buffer_segment_count != commons.BUFFER_UTIL_SIZE:
            raise ValueError("UTIL-Buffer was not cleanly dividable by chunk-count.")

        # init zeroed data for clearing buffers
        self.zero_2b = bytes(bytearray(2))
        self.zero_4b = bytes(bytearray(4))
        self.zero_8b = bytes(bytearray(8))

        self.devmem_fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        # TODO: could it also be async? might be error-source

        self.mapped_mem = mmap.mmap(
            self.devmem_fd,
            self.buffer_size,
            mmap.MAP_SHARED,
            access=mmap.PROT_WRITE,
            offset=self.buffer_address,
        )

    def __enter__(self) -> Self:
        # init whole buffer
        self.init_buffer_iv()
        self.init_buffer_gpio()
        self.init_buffer_util()
        return self

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        if self.mapped_mem is not None:
            self.mapped_mem.close()
        if self.devmem_fd is not None:
            os.close(self.devmem_fd)

    @staticmethod
    def timedelta_to_ns(delta: timedelta | None, default_s: int = 0) -> int:
        if isinstance(delta, timedelta):
            return int(delta.total_seconds() * 10**9)
        return int(timedelta(seconds=default_s).total_seconds() * 10**9)

    def config_tracers(self, start_timestamp_ns: int) -> None:
        if self.trace_iv is not None:
            self.ts_start_iv = start_timestamp_ns + self.timedelta_to_ns(self.trace_iv.delay)
            self.ts_stop_iv = self.ts_start_iv + self.timedelta_to_ns(
                self.trace_iv.duration,
                10**6,
            )
        if self.trace_gp is not None:
            self.ts_start_gp = start_timestamp_ns + self.timedelta_to_ns(self.trace_gp.delay)
            self.ts_stop_gp = self.ts_start_gp + self.timedelta_to_ns(
                self.trace_gp.duration,
                10**6,
            )
        # ⤷ duration defaults to ~ 100 days (10**6 seconds)
        log.debug(
            "[Tracer] time-boundaries set to IV[%.2f, %.2f], GPIO[%.2f, %.2f]",
            self.ts_start_iv / 1e9,
            self.ts_stop_iv / 1e9,
            self.ts_start_gp / 1e9,
            self.ts_stop_gp / 1e9,
        )
        self.ts_unset = False

    def init_buffer_iv(self) -> None:
        self.mapped_mem.seek(self.iv_trace_offset)
        self.mapped_mem.write(bytes(bytearray(self.iv_trace_size)))
        self.mapped_mem.seek(self.iv_canary_offset)
        self.mapped_mem.write(struct.pack("=L", commons.CANARY_VALUE_U32))

    def init_buffer_gpio(self) -> None:
        self.mapped_mem.seek(self.gpio_trace_offset)
        self.mapped_mem.write(bytes(bytearray(self.gpio_trace_size)))
        self.mapped_mem.seek(self.gpio_canary_offset)
        self.mapped_mem.write(struct.pack("=L", commons.CANARY_VALUE_U32))

    def init_buffer_util(self) -> None:
        self.mapped_mem.seek(self.util_trace_offset)
        self.mapped_mem.write(bytes(bytearray(self.util_trace_size)))
        self.mapped_mem.seek(self.util_canary_offset)
        self.mapped_mem.write(struct.pack("=L", commons.CANARY_VALUE_U32))

    def read_buffer_iv(self, *, verbose: bool = False) -> IVTrace | None:
        """Extracts trace from PRU-shared buffer in RAM.

        :param verbose: chatter-prevention, performance-critical computation saver

        Returns: IVTrace if available
        """
        # determine current state
        # TODO: add mode to wait blocking?
        self.mapped_mem.seek(self.iv_trace_offset)
        self.iv_trace_index_pru, pru_timestamp = struct.unpack("=LQ", self.mapped_mem.read(12))
        avail_length = (self.iv_trace_index_pru - self.iv_trace_index_read) % commons.BUFFER_IV_SIZE
        if avail_length < self.iv_segment_size:
            # nothing to do
            # TODO: detect overflow!!!
            # TODO: abandon segment-idea, read up to pru-index, add force to go below segment_size
            return None
        if verbose:
            log.debug(
                "Retrieve IV-Buffer index %d with len %d @%.3f sys_ts",
                self.iv_trace_index_read,
                self.iv_segment_size,
                time.time(),
            )
        if self.iv_trace_index_read != 0:
            # Timestamp is referenced to sample 0
            pru_timestamp = None
        if (self.iv_trace_timestamp_last > 0) and pru_timestamp is not None:
            diff_ms = (pru_timestamp - self.iv_trace_timestamp_last) // 10**6
            if pru_timestamp == 0:
                log.error("ZERO      timestamp detected after recv it from PRU")
            if diff_ms < 0:
                log.error(
                    "BACKWARDS timestamp-jump detected after recv it from PRU -> %d ms",
                    diff_ms,
                )
            elif diff_ms < commons.BUFFER_IV_INTERVAL_MS - 5:
                log.error(
                    "TOO SMALL timestamp-jump detected after recv it from PRU -> %d ms",
                    diff_ms,
                )
            elif diff_ms > commons.BUFFER_IV_INTERVAL_MS + 5:
                log.error(
                    "FORWARDS  timestamp-jump detected after recv it from PRU -> %d ms",
                    diff_ms,
                )
        if pru_timestamp is not None:
            self.iv_trace_timestamp_last = pru_timestamp
        segment_timestamp = (
            self.iv_trace_timestamp_last + self.iv_trace_index_read * commons.SAMPLE_INTERVAL_NS
        )

        # prepare & fetch data
        if self.ts_start_iv <= segment_timestamp <= self.ts_stop_iv:
            # TODO: honor boundary - check count + offset
            ivsamples = np.frombuffer(
                self.mapped_mem,
                np.uint32,
                count=2 * self.iv_segment_size,
                offset=self.iv_samples_offset + self.iv_trace_index_read * self.iv_samples_size,
            ).reshape((self.iv_segment_size, 2), order="C")  # TODO: test for correctness
            # TODO: interweave code from write_buffer might be faster
            data = IVTrace(
                voltage=ivsamples[:, 0], current=ivsamples[:, 1], timestamp_ns=segment_timestamp
            )
        else:
            data = None
        # TODO: segment in buffer should be reset to ZERO to better detect errors
        # advance index
        self.iv_trace_index_read += (
            self.iv_trace_index_read + self.iv_segment_size
        ) % commons.BUFFER_IV_SIZE
        # test canary
        self.mapped_mem.seek(self.iv_canary_offset)
        # TODO: canary can be tested less often (only on reset)
        canary = struct.unpack("=L", self.mapped_mem.read(4))
        if canary != commons.CANARY_VALUE_U32:
            raise BufferError(
                "Canary of IV-Buffer was harmed! It is 0x%X, expected 0x%X",
                canary,
                commons.CANARY_VALUE_U32,
            )
        return data

    def read_buffer_gpio(self, *, verbose: bool = False) -> GPIOTrace | None:
        # determine current state
        self.mapped_mem.seek(self.gpio_trace_offset)
        (index_pru,) = struct.unpack("=L", self.mapped_mem.read(4))
        avail_length = (index_pru - self.gpio_trace_index) % commons.BUFFER_GPIO_SIZE
        if avail_length < self.gpio_segment_size:
            # nothing to do
            # TODO: detect overflow!!!
            # TODO: abandon segment-idea, read up to pru-index, add force to go below segment_size
            return None
        if verbose:
            log.debug(
                "Retrieve GPIO-Buffer index %d with len %d @%.3f sys_ts",
                self.gpio_trace_index,
                self.gpio_segment_size,
                time.time(),
            )
        # prepare & fetch data
        # TODO: honor boundary - check count + offset
        data = GPIOTrace(
            timestamps_ns=np.frombuffer(
                self.mapped_mem,
                np.uint64,
                count=self.gpio_segment_size,
                offset=self.gpio_timestamps_offset + self.gpio_trace_index * 8,
            ),
            bitmasks=np.frombuffer(
                self.mapped_mem,
                np.uint16,
                count=self.gpio_segment_size,
                offset=self.gpio_bitmasks_offset + self.gpio_trace_index * 2,
            ),
        )
        # TODO: filter dataset with self.ts_start_gp <= buffer_timestamp <= self.ts_stop_gp
        # TODO: segment should be reset to ZERO to better detect errors
        # advance index
        self.gpio_trace_index += (
            self.gpio_trace_index + self.gpio_segment_size
        ) % commons.BUFFER_GPIO_SIZE
        # test canary
        self.mapped_mem.seek(self.gpio_canary_offset)
        # TODO: canary can be tested less often (only on reset)
        canary = struct.unpack("=L", self.mapped_mem.read(4))
        if canary != commons.CANARY_VALUE_U32:
            raise BufferError(
                "Canary of GPIO-Buffer was harmed! It is 0x%X, expected 0x%X",
                canary,
                commons.CANARY_VALUE_U32,
            )
        return data

    def read_buffer_util(self, *, verbose: bool = False) -> UtilTrace | None:
        # determine current state
        self.mapped_mem.seek(self.util_trace_offset)
        index_pru: int = struct.unpack("=L", self.mapped_mem.read(4))
        avail_length = (index_pru - self.util_trace_index) % commons.BUFFER_UTIL_SIZE
        if avail_length < self.util_segment_size:
            # nothing to do
            # TODO: detect overflow!!!
            # TODO: abandon segment-idea, read up to pru-index, add force to go below segment_size
            return None
        if verbose:
            log.debug(
                "Retrieve Util-Buffer index %d with len %d @%.3f sys_ts",
                self.util_trace_index,
                self.util_segment_size,
                time.time(),
            )
        # prepare & fetch data
        # TODO: honor boundary - check count + offset
        data = UtilTrace(
            timestamps_ns=np.frombuffer(
                self.mapped_mem,
                np.uint64,
                count=self.util_segment_size,
                offset=self.util_timestamps_offset + self.util_trace_index * 8,
            ),
            ticks_max=np.frombuffer(
                self.mapped_mem,
                np.uint32,
                count=self.util_segment_size,
                offset=self.util_ticks_max_offset + self.util_trace_index * 4,
            ),
            ticks_mean=np.frombuffer(
                self.mapped_mem,
                np.uint32,
                count=self.util_segment_size,
                offset=self.util_ticks_sum_offset + self.util_trace_index * 4,
            )
            / commons.SAMPLES_PER_SYNC,
        )
        # TODO: cleanup, every crit-instance should be reported
        util_mean_crit = data.ticks_mean.max() > 0.95 * commons.SAMPLE_INTERVAL_TICKS
        util_max_crit = data.ticks_max.max() > 1 * commons.SAMPLE_INTERVAL_TICKS

        if (self.pru_warn_counter > 0) and (util_mean_crit or util_max_crit):
            log.warning(
                "Pru0 Loop-Util: mean = %d %%, max = %d %% "
                "-> WARNING: probably broken real-time-condition",
                util_mean_crit,
                util_max_crit,
            )
            self.pru_warn_counter -= 1
            if self.pru_warn_counter == 0:
                # silenced because this is causing overhead without a cape
                log.warning(
                    "Pru0 Loop-Util-Warning is silenced now! Is emu running without a cape?"
                )
        elif verbose:
            log.info(
                "Pru0 Loop-Util: mean = %d %%, max = %d %%",
                data.ticks_mean.max(),
                data.ticks_max.max(),
            )

        # TODO: segment should be reset to ZERO to better detect errors
        # advance index
        self.util_trace_index += (
            self.util_trace_index + self.util_segment_size
        ) % commons.BUFFER_UTIL_SIZE
        # test canary
        self.mapped_mem.seek(self.util_canary_offset)
        # TODO: canary can be tested less often (only on reset)
        canary = struct.unpack("=L", self.mapped_mem.read(4))
        if canary != commons.CANARY_VALUE_U32:
            raise BufferError(
                "Canary of Util-Buffer was harmed! It is 0x%X, expected 0x%X",
                canary,
                commons.CANARY_VALUE_U32,
            )
        return data

    def get_space_to_write_iv(self) -> int:
        if self.iv_trace_index_write is None:
            # return commons.BUFFER_IV_SIZE - self.iv_trace_index_read
            return min(commons.BUFFER_IV_SIZE - self.iv_trace_index_read, self.iv_segment_size)
        return min(
            (self.iv_trace_index_read - self.iv_trace_index_write) % commons.BUFFER_IV_SIZE,
            self.iv_segment_size,
        )
        # min() avoids boundary handling in write function
        # find cleaner solution here to avoid boundary handling

    def can_fit_iv_segment(self) -> bool:
        return self.get_space_to_write_iv() >= self.iv_segment_size

    def write_buffer_iv(
        self,
        data: IVTrace,
        cal: CalibrationSeries,
        *,
        verbose: bool = False,
    ) -> None:
        avail_length = self.get_space_to_write_iv()
        if len(data) > avail_length:
            raise ValueError(
                "IVTrace to write is larger (%d) than the available space (%d)",
                len(data),
                avail_length,
            )
        ts_start = time.time() if verbose else None
        if self.iv_trace_index_write is None:
            self.iv_trace_index_write = 0
        # transform raw ADC data to SI-Units -> the virtual-source-emulator in PRU expects uV and nV
        data.voltage = cal.voltage.raw_to_si(data.voltage).astype("u4")
        data.current = cal.current.raw_to_si(data.current).astype("u4")
        # interweave data (voltage | current in parallel)
        iv_data = np.empty((2 * len(data),), dtype=data.voltage.dtype)
        iv_data[0::2] = data.voltage[: len(data)]
        iv_data[1::2] = data.current[: len(data)]
        # Seek buffer location in memory and skip header
        self.mapped_mem.seek(self.iv_samples_offset + 8 * self.iv_trace_index_write)
        self.mapped_mem.write(iv_data.tobytes())
        self.iv_trace_index_write = (self.iv_trace_index_write + len(data)) % commons.BUFFER_IV_SIZE
        # TODO: code does not handle boundaries - !!!!!
        # TODO: should we write or test timestamp? otherwise remove entry in pru-sharedmem
        if verbose:
            log.debug(
                "Sending emu-buffer to PRU took %.2f ms",
                1e3 * (time.time() - ts_start),
            )

    def write_firmware(self, data: bytes) -> int:
        data_size = len(data)
        if data_size > self.buffer_size:
            raise ValueError("firmware file is larger than the SharedMEM-Buffer")
        if data_size < 1:
            raise ValueError("firmware file is empty")
        sfs.write_programmer_datasize(data_size)
        self.mapped_mem.seek(0)
        self.mapped_mem.write(data)
        log.debug(
            "wrote Firmware-Data to SharedMEM-Buffer (size = %d bytes)",
            data_size,
        )
        return data_size
