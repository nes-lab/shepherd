import mmap
import os
import struct
import time
from dataclasses import dataclass
from datetime import timedelta
from types import TracebackType

import numpy as np
from shepherd_core.data_models import GpioTracing
from shepherd_core.data_models import PowerTracing
from typing_extensions import Self

from . import commons
from . import sysfs_interface as sfs
from .logger import log


@dataclass
class GPIOEdges:
    """Python representation of GPIO edge buffer

    On detection of an edge, shepherd stores the state of all sampled GPIO pins
    together with the corresponding timestamp
    """

    def __init__(
        self,
        timestamps_ns: np.ndarray | None = None,
        values: np.ndarray | None = None,
    ) -> None:
        self.timestamps_ns = timestamps_ns if timestamps_ns is not None else np.empty(0)
        self.values = values if values is not None else np.empty(0)

    def __len__(self) -> int:
        return min(self.values.size, self.timestamps_ns.size)


@dataclass
class DataBuffer:
    """Python representation of a shepherd buffer.

    Containing IV samples with corresponding timestamp and info about any
    detected GPIO edges
    """

    def __init__(
        self,
        voltage: np.ndarray,
        current: np.ndarray,
        timestamp_ns: int | None = None,
        gpio_edges: GPIOEdges | None = None,
        util_mean: float = 0,
        util_max: float = 0,
    ) -> None:
        self.timestamp_ns = timestamp_ns if timestamp_ns is not None else 0
        self.voltage = voltage
        self.current = current
        if gpio_edges is not None:
            self.gpio_edges = gpio_edges
        else:
            self.gpio_edges = GPIOEdges()
        self.util_mean = util_mean
        self.util_max = util_max

    def __len__(self) -> int:
        return min(self.voltage.size, self.current.size)


class SharedMemory:
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
        address: int,
        size: int,
        n_buffers: int,
        samples_per_buffer: int,
        trace_iv: PowerTracing | None,
        trace_gpio: GpioTracing | None,
    ) -> None:
        """Initializes relevant parameters for shared memory area.

        Args:
            address (int): Physical start address of memory area
            size (int): Total size of memory area in Byte
            n_buffers (int): Number of data buffers that fit into memory area
            samples_per_buffer (int): Number of IV samples per buffer
        """
        self.address = address
        self.size = int(size)
        self.n_buffers = int(n_buffers)
        if samples_per_buffer != 10000:
            raise ValueError(
                "Samples_per_buffer is NOT 10000. External routines expect currently 10k."
            )
        self.samples_per_buffer = int(samples_per_buffer)
        self.prev_timestamp: int = 0
        self.pru_warn: int = 10

        self.trace_iv = trace_iv
        self.trace_gp = trace_gpio
        # placeholders:
        self.ts_start_iv: int = 0
        self.ts_start_gp: int = 0
        self.ts_stop_iv: int = 0
        self.ts_stop_gp: int = 0
        self.ts_unset: bool = True

        # With knowledge of structure of each buffer, we calculate its total size
        self.buffer_size = (
            # Header: 32 bit canary, 32 bit counter, 64 bit timestamp
            4
            + 4
            + 8
            # Actual IV data, 32 bit for each current and voltage
            + 2 * 4 * self.samples_per_buffer
            # GPIO-Header: 32 bit canary, 32 bit edge counter
            + 4
            + 4
            # 64 bit timestamp per GPIO event
            + 8 * commons.MAX_GPIO_EVT_PER_BUFFER
            # 16 bit GPIO state per GPIO event (edge data)
            + 2 * commons.MAX_GPIO_EVT_PER_BUFFER
            # pru0 util stat
            + 2 * 4
        )  # NOTE: atm 4h of bug-search lead to this hardcoded piece
        self.buffer_header_size = 16
        # TODO: put number in shared-mem or other way around

        self.voltage_offset = 4 + 4 + 8
        self.current_offset = 16 + 1 * 4 * self.samples_per_buffer
        self.gpio_offset = 16 + 2 * 4 * self.samples_per_buffer
        self.gpio_ts_offset = self.gpio_offset + 4 + 4
        self.gpio_vl_offset = self.gpio_offset + 8 + 8 * commons.MAX_GPIO_EVT_PER_BUFFER
        self.pru0_ut_offset = self.gpio_offset + 8 + 10 * commons.MAX_GPIO_EVT_PER_BUFFER
        # init zeroed data for clearing buffers
        self.zero_4b = bytes(bytearray(4))
        self.zero_8b = bytes(bytearray(8))
        self.zero_gpio_ts = commons.MAX_GPIO_EVT_PER_BUFFER * self.zero_8b

        log.debug("Size of 1 Buffer:\t%d byte", self.buffer_size)
        if self.buffer_size * self.n_buffers != self.size:
            raise BufferError(
                "Py-estimated mem-size for buffers is different "
                f"from pru-reported size ({self.buffer_size * self.n_buffers} vs. {self.size})",
            )

        self.devmem_fd = os.open(
            "/dev/mem",
            os.O_RDWR | os.O_SYNC,
        )  # TODO: could it also be async? might be error-source

        self.mapped_mem = mmap.mmap(
            self.devmem_fd,
            self.size,
            mmap.MAP_SHARED,
            mmap.PROT_WRITE,
            offset=self.address,
        )

    def __enter__(self) -> Self:
        # zero parts of buffer as a precaution
        for idx in range(self.n_buffers):
            self.clear_buffer(idx)
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

    def config_tracers(self, timestamp_ns: int) -> None:
        if self.trace_iv is not None:
            self.ts_start_iv = timestamp_ns + self.timedelta_to_ns(self.trace_iv.delay)
            self.ts_stop_iv = self.ts_start_iv + self.timedelta_to_ns(
                self.trace_iv.duration,
                10**6,
            )
        if self.trace_gp is not None:
            self.ts_start_gp = timestamp_ns + self.timedelta_to_ns(self.trace_gp.delay)
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

    def read_buffer(self, index: int, verbose: bool = False) -> DataBuffer:
        """Extracts buffer from shared memory.

        Extracts data from buffer with given index from the shared memory area
        in RAM.

        :param index: (int): Buffer index. 0 <= index < n_buffers
        :param verbose: chatter-prevention, performance-critical computation saver

        Returns:
            DataBuffer object pointing to extracted data
        """
        # The buffers are organized as an array in shared memory
        if not (0 <= index < self.n_buffers):
            raise ValueError(
                f"out of bound access (i={index}), tried reading from SharedMEM-Buffer",
            )
        buffer_offset = index * self.buffer_size
        self.mapped_mem.seek(buffer_offset)

        # Read the header consisting of 16 (4 + 4 + 8 Bytes)
        # -> canary, number of samples and 64 bit timestamp
        canary1, n_samples, buffer_timestamp = struct.unpack(
            "=LLQ",
            self.mapped_mem.read(16),
        )
        if verbose:
            log.debug(
                "Retrieved buffer #%d  (@+%s) with len %d and timestamp %d ms @%.3f sys_ts",
                index,
                f"0x{(index * self.buffer_size):06X}",
                # ⤷ not directly in message because of colorizer
                n_samples,
                buffer_timestamp // 1000000,
                time.time(),
            )
        if canary1 != 0x0F0F0F0F:
            raise BufferError(
                f"CANARY of SampleBuffer was harmed! Is 0x{canary1:X}, expected 0x0F0F0F0F",
            )

        # verify received timestamp,
        # TODO: python knows the desired duration between timestamps
        if self.prev_timestamp > 0:
            diff_ms = (buffer_timestamp - self.prev_timestamp) // 10**6
            if buffer_timestamp == 0:
                log.error("ZERO      timestamp detected after recv it from PRU")
            if diff_ms < 0:
                log.error(
                    "BACKWARDS timestamp-jump detected after recv it from PRU -> %d ms",
                    diff_ms,
                )
            elif diff_ms < 95:
                log.error(
                    "TOO SMALL timestamp-jump detected after recv it from PRU -> %d ms",
                    diff_ms,
                )
            elif diff_ms > 105:
                log.error(
                    "FORWARDS  timestamp-jump detected after recv it from PRU -> %d ms",
                    diff_ms,
                )
        self.prev_timestamp = buffer_timestamp

        if self.ts_unset and buffer_timestamp > 0:
            self.config_tracers(buffer_timestamp)

        if self.ts_start_iv <= buffer_timestamp <= self.ts_stop_iv:
            # Each buffer contains (n=) samples_per_buffer values. We have 2 variables
            # (voltage and current), thus samples_per_buffer/2 samples per variable
            voltage = np.frombuffer(
                self.mapped_mem,
                "=u4",
                count=self.samples_per_buffer,
                offset=buffer_offset + self.voltage_offset,
            )
            current = np.frombuffer(
                self.mapped_mem,
                "=u4",
                count=self.samples_per_buffer,
                offset=buffer_offset + self.current_offset,
            )
        else:
            voltage = np.empty(0, dtype=np.uint32)
            current = np.empty(0, dtype=np.uint32)

        # Read the number of gpio events in the buffer
        self.mapped_mem.seek(buffer_offset + self.gpio_offset)
        canary2, n_gpio_events = struct.unpack("=LL", self.mapped_mem.read(8))

        if canary2 != 0x0F0F0F0F:
            raise BufferError(
                f"CANARY of GpioBuffer was harmed! Is 0x{canary2:X}, expected 0x0F0F0F0F",
            )

        if n_gpio_events == commons.MAX_GPIO_EVT_PER_BUFFER:
            log.warning(
                "Current GPIO-Buffer is full @ buffer-ts = %.1f s -> hint for overflow & loss of data",
                buffer_timestamp / 1e9,
            )
        if not (0 <= n_gpio_events <= commons.MAX_GPIO_EVT_PER_BUFFER):
            log.error(
                "Size of gpio_events out of range with %d entries (max=%d)",
                n_gpio_events,
                commons.MAX_GPIO_EVT_PER_BUFFER,
            )
            n_gpio_events = commons.MAX_GPIO_EVT_PER_BUFFER

        if self.ts_start_gp <= buffer_timestamp <= self.ts_stop_gp:
            gpio_timestamps_ns = np.frombuffer(
                self.mapped_mem,
                "=u8",
                count=n_gpio_events,
                offset=buffer_offset + self.gpio_ts_offset,
            )

            gpio_values = np.frombuffer(
                self.mapped_mem,
                "=u2",
                count=n_gpio_events,
                offset=buffer_offset + self.gpio_vl_offset,
            )
        else:
            gpio_timestamps_ns = np.empty(0, dtype=np.uint64)
            gpio_values = np.empty(0, dtype=np.uint16)

        if len(gpio_timestamps_ns) > 0:
            # test if first/last gpio-timestamp is in scope of outer buffer
            ts1_valid = buffer_timestamp <= gpio_timestamps_ns[0] <= buffer_timestamp + 100e6
            ts2_valid = buffer_timestamp <= gpio_timestamps_ns[-1] <= buffer_timestamp + 100e6
            if not (ts1_valid and ts2_valid):
                log.warning(
                    "Timestamps of GPIO-buffer are out of scope of outer buffer-period @ ts = %.1f s",
                    buffer_timestamp / 1e9,
                )

        gpio_edges = GPIOEdges(gpio_timestamps_ns, gpio_values)

        # pru0 util
        self.mapped_mem.seek(buffer_offset + self.pru0_ut_offset)
        pru0_max_ticks, pru0_sum_ticks = struct.unpack("=LL", self.mapped_mem.read(8))
        pru0_util_max = round(100 * pru0_max_ticks / 2000, 1)
        pru0_util_mean = round(100 * pru0_sum_ticks / n_samples / 2000, 1)
        if pru0_util_mean > pru0_util_max:
            pru0_util_mean = 0.1
        if (self.pru_warn > 0) and ((pru0_util_mean > 95) or (pru0_util_max > 100)):
            log.warning(
                "Pru0 Loop-Util: mean = %d %%, max = %d %% "
                "-> WARNING: probably broken real-time-condition",
                pru0_util_mean,
                pru0_util_max,
            )
            self.pru_warn -= 1
            if self.pru_warn == 0:
                log.warning(
                    "Pru0 Loop-Util-Warning is silenced now! Is emu running without a cape?"
                )
            # TODO: this is causing high overhead without a cape
        elif verbose:
            log.info(
                "Pru0 Loop-Util: mean = %d %%, max = %d %%",
                pru0_util_mean,
                pru0_util_max,
            )

        return DataBuffer(
            voltage,
            current,
            buffer_timestamp,
            gpio_edges,
            pru0_util_mean,
            pru0_util_max,
        )

    def clear_buffer(self, index: int) -> None:
        # this fn should be executed before handing the buffer back to PRU
        buffer_offset = self.buffer_size * index
        # IV-Sample len & timestamp
        self.mapped_mem.seek(buffer_offset + 4)  # behind canary
        self.mapped_mem.write(self.zero_4b)  # len
        self.mapped_mem.write(self.zero_8b)  # timestamp
        # GPIO-Edges-Index & timestamps
        self.mapped_mem.seek(buffer_offset + self.gpio_offset + 4)  # behind canary
        self.mapped_mem.write(self.zero_4b)  # idx
        self.mapped_mem.write(self.zero_gpio_ts)  # timestamp-array

    def write_buffer(
        self,
        index: int,
        voltage: np.ndarray,
        current: np.ndarray,
    ) -> None:
        if not (0 <= index < self.n_buffers):
            raise ValueError(
                f"out of bound access (i={index}), tried writing to SharedMEM-Buffer",
            )
        if (voltage.shape[0] != self.samples_per_buffer) or (
            current.shape[0] != self.samples_per_buffer
        ):
            raise ValueError(
                "Buffer #%d has unexpected size (v%d, c%d)",
                index,
                voltage.shape[0],
                current.shape[0],
            )
        buffer_offset = self.buffer_size * index
        # Seek buffer location in memory and skip header
        self.mapped_mem.seek(buffer_offset + self.buffer_header_size)
        self.mapped_mem.write(voltage.tobytes())
        self.mapped_mem.write(current.tobytes())

    def write_firmware(self, data: bytes) -> int:
        data_size = len(data)
        if data_size > self.size:
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
