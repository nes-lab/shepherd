import mmap
import os
import struct
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from . import commons
from . import sysfs_interface as sfs
from .logger import logger


@dataclass
class GPIOEdges:
    """Python representation of GPIO edge buffer

    On detection of an edge, shepherd stores the state of all sampled GPIO pins
    together with the corresponding timestamp
    """

    def __init__(
        self,
        timestamps_ns: Optional[np.ndarray] = None,
        values: Optional[np.ndarray] = None,
    ):
        self.timestamps_ns = timestamps_ns if timestamps_ns is not None else np.empty(0)
        self.values = values if values is not None else np.empty(0)

    def __len__(self):
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
        timestamp_ns: Optional[int] = None,
        gpio_edges: Optional[GPIOEdges] = None,
        util_mean: float = 0,
        util_max: float = 0,
    ):
        self.timestamp_ns = timestamp_ns if timestamp_ns is not None else 0
        self.voltage = voltage
        self.current = current
        if gpio_edges is not None:
            self.gpio_edges = gpio_edges
        else:
            self.gpio_edges = GPIOEdges()
        self.util_mean = util_mean
        self.util_max = util_max

    def __len__(self):
        return min(self.voltage.size, self.current.size)


class SharedMem:
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
    ):
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
        self.samples_per_buffer = int(samples_per_buffer)
        self.prev_timestamp: int = 0

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
        # TODO: put number in shared-mem or other way around

        self.voltage_offset = 4 + 4 + 8
        self.current_offset = 16 + 1 * 4 * self.samples_per_buffer
        self.gpio_offset = 16 + 2 * 4 * self.samples_per_buffer
        self.gpio_ts_offset = self.gpio_offset + 4 + 4
        self.gpio_vl_offset = self.gpio_offset + 8 + 8 * commons.MAX_GPIO_EVT_PER_BUFFER
        self.pru0_ut_offset = (
            self.gpio_offset + 8 + 10 * commons.MAX_GPIO_EVT_PER_BUFFER
        )

        logger.debug("Size of 1 Buffer:\t%d byte", self.buffer_size)
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

    def __enter__(self):
        return self

    def __exit__(self, *args):  # type: ignore
        if self.mapped_mem is not None:
            self.mapped_mem.close()
        if self.devmem_fd is not None:
            os.close(self.devmem_fd)

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
            logger.debug(
                "Retrieved buffer #%d  (@+%s) "
                "with len %d and timestamp %d ms @%.3f sys_ts",
                index,
                f"0x{(index * self.buffer_size):06X}",
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
                logger.error("ZERO      timestamp detected after recv it from PRU")
            if diff_ms < 0:
                logger.error(
                    "BACKWARDS timestamp-jump detected after recv it from PRU -> %d ms",
                    diff_ms,
                )
            elif diff_ms < 95:
                logger.error(
                    "TOO SMALL timestamp-jump detected after recv it from PRU -> %d ms",
                    diff_ms,
                )
            elif diff_ms > 105:
                logger.error(
                    "FORWARDS  timestamp-jump detected after recv it from PRU -> %d ms",
                    diff_ms,
                )
        self.prev_timestamp = buffer_timestamp

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

        # Read the number of gpio events in the buffer
        self.mapped_mem.seek(buffer_offset + self.gpio_offset)
        canary2, n_gpio_events = struct.unpack("=LL", self.mapped_mem.read(8))

        if canary2 != 0x0F0F0F0F:
            raise BufferError(
                f"CANARY of GpioBuffer was harmed! Is 0x{canary2:X}, expected 0x0F0F0F0F",
            )

        if not (0 <= n_gpio_events <= commons.MAX_GPIO_EVT_PER_BUFFER):
            logger.error(
                "Size of gpio_events out of range with %d entries",
                n_gpio_events,
            )
            # TODO: should be exception, also
            #  put into LogWriter.write_exception() with ShepherdIOException
            n_gpio_events = commons.MAX_GPIO_EVT_PER_BUFFER

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
        gpio_edges = GPIOEdges(gpio_timestamps_ns, gpio_values)

        # pru0 util
        self.mapped_mem.seek(buffer_offset + self.pru0_ut_offset)
        pru0_max_ticks, pru0_sum_ticks = struct.unpack("=LL", self.mapped_mem.read(8))
        pru0_util_max = round(100 * pru0_max_ticks / 2000, 1)
        pru0_util_mean = round(100 * pru0_sum_ticks / n_samples / 2000, 1)
        if pru0_util_mean > pru0_util_max:
            pru0_util_mean = 0.1
        if verbose:
            if (pru0_util_mean > 95) or (pru0_util_max > 100):
                logger.warning(
                    "Pru0 Loop-Util: mean = %d %%, max = %d %% "
                    "-> WARNING: broken real-time-condition",
                    pru0_util_mean,
                    pru0_util_max,
                )
                # TODO: raise ShepherdIOException or add this info into output-file?
                #  WRONG PLACE HERE
            else:
                logger.info(
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
        buffer_offset = self.buffer_size * index
        # Seek buffer location in memory and skip 12B header
        self.mapped_mem.seek(buffer_offset + 12)
        self.mapped_mem.write(voltage.tobytes())
        self.mapped_mem.write(current.tobytes())

    def write_firmware(self, data: bytes):
        data_size = len(data)
        if data_size > self.size:
            raise ValueError("firmware file is larger than the SharedMEM-Buffer")
        if data_size < 1:
            raise ValueError("firmware file is empty")
        sfs.write_programmer_datasize(data_size)
        self.mapped_mem.seek(0)
        self.mapped_mem.write(data)
        logger.debug(
            "wrote Firmware-Data to SharedMEM-Buffer (size = %d bytes)",
            data_size,
        )
        return data_size
