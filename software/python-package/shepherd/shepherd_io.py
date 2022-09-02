# -*- coding: utf-8 -*-

"""
shepherd.shepherd_io
~~~~~
Interface layer, abstracting low-level functionality provided by PRUs and
kernel module. User-space part of the double-buffered data exchange protocol.
TODO: these files are getting to big, ~ 1000 LOC, refactor into class_X.py

:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""

import os
import weakref
import logging
import time
import struct
import mmap
from typing import NoReturn, Union, Optional
import numpy as np
from periphery import GPIO

from shepherd import sysfs_interface as sfs
from shepherd import commons
from .calibration import CalibrationData, cal_component_list
from .virtual_source_config import VirtualSourceConfig
from .virtual_harvester_config import VirtualHarvesterConfig

logger = logging.getLogger(__name__)

ID_ERR_TIMEOUT = 100

gpio_pin_nums = {
    "target_pwr_sel": 31,
    "target_io_en": 60,
    "target_io_sel": 30,
    "en_shepherd": 23,
    "en_recorder": 50,
    "en_emulator": 51,
}


class ShepherdIOException(Exception):
    def __init__(self, message: str, id_num: int = 0, value: int = 0):
        super().__init__(message + f" [id=0x{id_num:x}, val=0x{value:x}]")
        self.id_num = id_num
        self.value = value


class GPIOEdges:
    """Python representation of GPIO edge buffer

    On detection of an edge, shepherd stores the state of all sampled GPIO pins
    together with the corresponding timestamp
    """

    def __init__(self, timestamps_ns: np.ndarray = None, values: np.ndarray = None):
        if timestamps_ns is None:
            self.timestamps_ns = np.empty(0)
            self.values = np.empty(0)
        else:
            self.timestamps_ns = timestamps_ns
            self.values = values

    def __len__(self):
        return min(self.values.size, self.timestamps_ns.size)


class DataBuffer:
    """Python representation of a shepherd buffer.

    Containing IV samples with corresponding timestamp and info about any
    detected GPIO edges
    """

    def __init__(
        self,
        voltage: np.ndarray,
        current: np.ndarray,
        timestamp_ns: int = None,
        gpio_edges: GPIOEdges = None,
        util_mean: float = 0,
        util_max: float = 0,
    ):
        self.timestamp_ns = timestamp_ns
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
        self, address: int, size: int, n_buffers: int, samples_per_buffer: int
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

        self.mapped_mem = None
        self.devmem_fd = None

        # With knowledge of structure of each buffer, we calculate its total size
        self.buffer_size = (
            # Header: 64 bit timestamp + 32 bit counter
            8
            + 4
            # Actual IV data, 32 bit for each current and voltage
            + 2 * 4 * self.samples_per_buffer
            # GPIO edge count
            + 4
            # 64 bit timestamp per GPIO event
            + 8 * commons.MAX_GPIO_EVT_PER_BUFFER
            # 16 bit GPIO state per GPIO event
            + 2 * commons.MAX_GPIO_EVT_PER_BUFFER  # GPIO edge data
            # pru0 util stat
            + 2 * 4
        )  # NOTE: atm 4h of bug-search lead to this hardcoded piece
        # TODO: put number in shared-mem or other way around

        self.voltage_offset = 12
        self.current_offset = 12 + 1 * 4 * self.samples_per_buffer
        self.gpiostr_offset = 12 + 2 * 4 * self.samples_per_buffer
        self.gpio_ts_offset = self.gpiostr_offset + 4
        self.gpio_vl_offset = (
            self.gpiostr_offset + 4 + 8 * commons.MAX_GPIO_EVT_PER_BUFFER
        )
        self.pru0_ut_offset = (
            self.gpiostr_offset + 4 + 10 * commons.MAX_GPIO_EVT_PER_BUFFER
        )

        logger.debug(f"Size of 1 Buffer:\t{ self.buffer_size } byte")

    def __enter__(self):
        self.devmem_fd = os.open(
            "/dev/mem", os.O_RDWR | os.O_SYNC
        )  # TODO: could it also be async? might be error-source

        self.mapped_mem = mmap.mmap(
            self.devmem_fd,
            self.size,
            mmap.MAP_SHARED,
            mmap.PROT_WRITE,
            offset=self.address,
        )

        return self

    def __exit__(self, *args):
        self.mapped_mem.close()
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
            ValueError(
                f"out of bound access (i={index}), tried reading from SharedMEM-Buffer"
            )
        buffer_offset = index * self.buffer_size
        self.mapped_mem.seek(buffer_offset)

        # Read the header consisting of 12 (4 + 8 Bytes)
        # First two values are number of samples and 64 bit timestamp
        n_samples, buffer_timestamp = struct.unpack("=LQ", self.mapped_mem.read(12))
        if verbose:
            logger.debug(
                f"Retrieved buffer #{ index }  (@+0x{index * self.buffer_size:06X}) "
                f"with len {n_samples} and timestamp {buffer_timestamp // 1000000} ms "
                f"@{round(time.time(), 3)} sys_ts"
            )

        # sanity-check of received timestamp, TODO: python knows the desired duration between timestamps
        if self.prev_timestamp > 0:
            diff_ms = (buffer_timestamp - self.prev_timestamp) // 10**6
            if buffer_timestamp == 0:
                logger.error("ZERO      timestamp detected after recv it from PRU")
            if diff_ms < 0:
                logger.error(
                    f"BACKWARDS timestamp-jump detected after recv it from PRU -> {diff_ms} ms"
                )
            elif diff_ms < 95:
                logger.error(
                    f"TOO SMALL timestamp-jump detected after recv it from PRU -> {diff_ms} ms"
                )
            elif diff_ms > 105:
                logger.error(
                    f"FORWARDS  timestamp-jump detected after recv it from PRU -> {diff_ms} ms"
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
        self.mapped_mem.seek(buffer_offset + self.gpiostr_offset)
        (n_gpio_events,) = struct.unpack("=L", self.mapped_mem.read(4))

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
                warn_msg = (
                    f"Pru0 Loop-Util:  "
                    f"mean = {pru0_util_mean} %, "
                    f"max = {pru0_util_max} % "
                    f"-> WARNING: broken real-time-condition"
                )
                logger.warning(warn_msg)
                # TODO: raise ShepherdIOException or add this info into output-file? WRONG PLACE HERE
            else:
                logger.info(
                    f"Pru0 Loop-Util: mean = {pru0_util_mean} %, max = {pru0_util_max} %"
                )

        return DataBuffer(
            voltage,
            current,
            buffer_timestamp,
            gpio_edges,
            pru0_util_mean,
            pru0_util_max,
        )

    def write_buffer(self, index: int, voltage, current) -> NoReturn:

        if not (0 <= index < self.n_buffers):
            ValueError(
                f"out of bound access (i={index}), tried writing to SharedMEM-Buffer"
            )
        buffer_offset = self.buffer_size * index
        # Seek buffer location in memory and skip 12B header
        self.mapped_mem.seek(buffer_offset + 12)
        self.mapped_mem.write(voltage)
        self.mapped_mem.write(current)

    def write_firmware(self, data: bytes):
        data_size = len(data)
        if data_size > self.size:
            ValueError("firmware file is larger than the SharedMEM-Buffer")
        sfs.write_programmer_datasize(data_size)
        self.mapped_mem.seek(0)
        self.mapped_mem.write(data)
        logger.debug(
            f"wrote Firmware-Data to SharedMEM-Buffer (size = {data_size} bytes)"
        )
        return data_size


class ShepherdIO:
    """Generic ShepherdIO interface.

    This class acts as interface between kernel module and firmware on the PRUs,
    and user space code. It handles the user space part of the double-buffered
    data-exchange protocol between user space and PRUs and configures the
    hardware by setting corresponding GPIO pins. This class should usually not
    be instantiated, but instead serve as parent class for e.g. Recorder or
    Emulator (see __init__.py).
    """

    # This _instance-element is part of the singleton implementation
    _instance = None
    _buffer_period = 0.1  # placeholder
    shared_mem: SharedMem = None

    def __new__(cls, *args, **kwds):
        """Implements singleton class."""
        if ShepherdIO._instance is None:
            new_class = object.__new__(cls)
            ShepherdIO._instance = weakref.ref(new_class)
            return new_class
        else:
            raise IndexError("ShepherdIO already exists")

    def __init__(self, mode: str):
        """Initializes relevant variables.

        Args:
            mode (str): Shepherd mode, see sysfs_interface for more
        """
        self.mode = mode
        if mode in cal_component_list:
            self.component = mode
        else:
            self.component = "emulator"
        self.gpios = {}

    def __del__(self):
        ShepherdIO._instance = None

    def __enter__(self):
        try:
            for name, pin in gpio_pin_nums.items():
                self.gpios[name] = GPIO(pin, "out")

            self._set_shepherd_pcb_power(True)
            self.set_target_io_level_conv(False)

            logger.debug("Shepherd hardware is powered up")

            # If shepherd hasn't been terminated properly
            self.reinitialize_prus()
            logger.debug(f"Switching to '{ self.mode }'-mode")
            sfs.write_mode(self.mode)

            # clean up msg-channel provided by kernel module
            self._flush_msgs()

            # Ask PRU for base address of shared mem (reserved with remoteproc)
            mem_address = sfs.get_mem_address()
            # Ask PRU for size of shared memory (reserved with remoteproc)
            mem_size = sfs.get_mem_size()

            logger.debug(
                f"Shared memory address: \t0x{mem_address:08X}, size: {mem_size} byte"
            )

            # Ask PRU for size of individual buffers
            self.samples_per_buffer = sfs.get_samples_per_buffer()
            logger.debug(f"Samples per buffer: \t{ self.samples_per_buffer }")

            self.n_buffers = sfs.get_n_buffers()
            logger.debug(f"Number of buffers: \t{ self.n_buffers }")

            self.buffer_period_ns = sfs.get_buffer_period_ns()
            self._buffer_period = self.buffer_period_ns / 1e9
            logger.debug(f"Buffer period: \t\t{ self._buffer_period } s")

            self.shared_mem = SharedMem(
                mem_address, mem_size, self.n_buffers, self.samples_per_buffer
            )

            self.shared_mem.__enter__()

        except Exception as xcp:
            logger.warning(f"ShepherdIO.Init caught an exception ({xcp}) -> exit now")
            self._cleanup()
            raise

        sfs.wait_for_state("idle", 3)
        return self

    def __exit__(self, *args):
        logger.info("Now exiting ShepherdIO")
        self._cleanup()

    @staticmethod
    def _send_msg(msg_type: int, values: Union[int, list]) -> NoReturn:
        """Sends a formatted message to PRU0.

        Args:
            msg_type (int): Indicates type of message, must be one of the agreed
                message types part of the data exchange protocol
            values (int): Actual content of the message
        """
        sfs.write_pru_msg(msg_type, values)

    def _get_msg(self, timeout_n: int = 5):
        """Tries to retrieve formatted message from PRU0.

        Args:
            timeout_n (int): Maximum number of buffer_periods to wait for a message
                before raising timeout exception

        """  # TODO: cleanest way without exception: ask sysfs-file with current msg-count
        for _ in range(timeout_n):
            try:
                return sfs.read_pru_msg()
            except sfs.SysfsInterfaceException:
                time.sleep(self._buffer_period)
                continue
        raise ShepherdIOException("Timeout waiting for message", ID_ERR_TIMEOUT)

    @staticmethod
    def _flush_msgs():
        """Flushes msg_channel by reading all available bytes."""
        while True:
            try:
                sfs.read_pru_msg()
            except sfs.SysfsInterfaceException:
                break

    def start(self, start_time: float = None, wait_blocking: bool = True) -> NoReturn:
        """Starts sampling either now or at later point in time.

        Args:
            start_time (int): Desired start time in unix time
            wait_blocking (bool): If true, block until start has completed
        """
        if isinstance(start_time, (float, int)):
            logger.debug(f"asking kernel module for start at {round(start_time, 2)}")
        sfs.set_start(start_time)
        if wait_blocking:
            self.wait_for_start(3_000_000)

    @staticmethod
    def wait_for_start(timeout: float) -> NoReturn:
        """Waits until shepherd has started sampling.

        Args:
            timeout (float): Time to wait in seconds
        """
        sfs.wait_for_state("running", timeout)

    def reinitialize_prus(self) -> NoReturn:
        sfs.set_stop(force=True)  # forces idle
        sfs.wait_for_state("idle", 5)

    def _cleanup(self):
        logger.debug("ShepherdIO is commanded to power down / cleanup")
        while sfs.get_state() != "idle":
            try:
                sfs.set_stop(force=True)
            except Exception as e:
                print(e)
            try:
                sfs.wait_for_state("idle", 3.0)
            except sfs.SysfsInterfaceException:
                logger.warning(
                    "CleanupRoutine - send stop-command and waiting for PRU to go to idle"
                )
        self.set_aux_target_voltage(None, 0.0)

        if self.shared_mem is not None:
            self.shared_mem.__exit__()

        self.set_target_io_level_conv(False)
        self.set_power_state_emulator(False)
        self.set_power_state_recorder(False)
        self._set_shepherd_pcb_power(False)
        logger.debug("Shepherd hardware is now powered down")

    def _set_shepherd_pcb_power(self, state: bool) -> NoReturn:
        """Controls state of power supplies on shepherd cape.

        Args:
            state (bool): True for on, False for off
        """
        state_str = "enabled" if state else "disabled"
        logger.debug(f"Set power-supplies of shepherd-pcb to {state_str}")
        self.gpios["en_shepherd"].write(state)

    def set_power_state_recorder(self, state: bool) -> NoReturn:
        """
        triggered pin is currently connected to ADCs reset-line
        NOTE: this might be extended to DAC as well

        :param state: bool, enable to get ADC out of reset
        :return:
        """
        state_str = "enabled" if state else "disabled"
        logger.debug(f"Set Recorder of shepherd-pcb to {state_str}")
        self.gpios["en_recorder"].write(state)

    def set_power_state_emulator(self, state: bool) -> NoReturn:
        """
        triggered pin is currently connected to ADCs reset-line
        NOTE: this might be extended to DAC as well

        :param state: bool, enable to get ADC out of reset
        :return:
        """
        state_str = "enabled" if state else "disabled"
        logger.debug(f"Set Emulator of shepherd-pcb to {state_str}")
        self.gpios["en_emulator"].write(state)

    def select_main_target_for_power(self, sel_target_a: bool) -> NoReturn:
        """choose which targets gets the supply with current-monitor, True = Target A, False = Target B

        shepherd hw-rev2 has two ports for targets and two separate power supplies,
        but only one is able to measure current, the other is considered "auxiliary"

        Args:
            sel_target_a: True to select A, False for B
        """
        current_state = sfs.get_state()
        if current_state != "idle":
            self.reinitialize_prus()
        if sel_target_a is None:
            # Target A is Default
            sel_target_a = True
        target = "A" if sel_target_a else "B"
        logger.debug(
            f"Set routing for (main) supply with current-monitor to target {target}"
        )
        self.gpios["target_pwr_sel"].write(sel_target_a)
        if current_state != "idle":
            self.start(wait_blocking=True)

    def select_main_target_for_io(self, sel_target_a: bool) -> NoReturn:
        """choose which targets gets the io-connection (serial, swd, gpio) from beaglebone,
            True = Target A,
            False = Target B

        shepherd hw-rev2 has two ports for targets and can switch independently between power supplies

        Args:
            sel_target_a: True to select A, False for B
        """
        if sel_target_a is None:
            # Target A is Default
            sel_target_a = True
        target = "A" if sel_target_a else "B"
        logger.debug(f"Set routing for IO to Target {target}")
        self.gpios["target_io_sel"].write(sel_target_a)

    def set_target_io_level_conv(self, state: bool) -> NoReturn:
        """Enables or disables the GPIO level converter to targets.

        The shepherd cape has bidirectional logic level translators (LSF0108)
        for translating UART, GPIO and SWD signals between BeagleBone and target
        voltage levels. This function enables or disables the converter and
        additional switches (NLAS4684) to keep leakage low.

        Args:
            state (bool): True for enabling converter, False for disabling
        """
        if state is None:
            state = False
        state_str = "enabled" if state else "disabled"
        logger.debug(f"Set target-io level converter to {state_str}")
        self.gpios["target_io_en"].write(state)

    @staticmethod
    def set_aux_target_voltage(
        cal_settings: Optional[CalibrationData], voltage: float
    ) -> NoReturn:
        """Enables or disables the voltage for the second target

        The shepherd cape has two DAC-Channels that each serve as power supply for a target

        Args:
            cal_settings: CalibrationData, TODO: should it be a class-variable?
            voltage (float): Desired output voltage in volt. Providing 0 or
                False disables supply, setting it to True will link it
                to the other channel
        """
        sfs.write_dac_aux_voltage(cal_settings, voltage)

    @staticmethod
    def get_aux_voltage(cal_settings: CalibrationData) -> float:
        """Reads the auxiliary voltage (dac channel B) from the PRU core.

        Args:
            cal_settings: dict with offset/gain

        Returns:
            aux voltage
        """
        return sfs.read_dac_aux_voltage(cal_settings)

    def send_calibration_settings(self, cal_settings: CalibrationData) -> NoReturn:
        """Sends calibration settings to PRU core

        For the virtual source it is required to have the calibration settings.
        Note: to apply these settings the pru has to do a re-init (reset)

        Args:
            cal_settings (CalibrationData): Contains the device's
            calibration settings.
        """
        if cal_settings is None:
            cal_settings = CalibrationData.from_default()
        cal_dict = cal_settings.export_for_sysfs(self.component)
        sfs.write_calibration_settings(cal_dict)

    @staticmethod
    def send_virtual_converter_settings(
        settings: VirtualSourceConfig,
    ) -> NoReturn:
        """Sends virtsource settings to PRU core
        looks like a simple one-liner but is needed by the child-classes
        Note: to apply these settings the pru has to do a re-init (reset)

        :param settings: Contains the settings for the virtual source.
        """
        sfs.write_virtual_converter_settings(settings.export_for_sysfs())

    @staticmethod
    def send_virtual_harvester_settings(
        settings: VirtualHarvesterConfig,
    ) -> NoReturn:
        """Sends virtsource settings to PRU core
        looks like a simple one-liner but is needed by the child-classes
        Note: to apply these settings the pru has to do a re-init (reset)

        :param settings: Contains the settings for the virtual source.
        """
        sfs.write_virtual_harvester_settings(settings.export_for_sysfs())

    def _return_buffer(self, index: int) -> NoReturn:
        """Returns a buffer to the PRU

        After reading the content of a buffer and potentially filling it with
        emulation data, we have to release the buffer to the PRU to avoid it
        running out of buffers.

        Args:
            index (int): Index of the buffer. 0 <= index < n_buffers
        """
        self._send_msg(commons.MSG_BUF_FROM_HOST, index)

    def get_buffer(self, timeout_n: int = 10, verbose: bool = False):
        """Reads a data buffer from shared memory.

        Polls the msg-channel for a message from PRU0 and, if the message
        points to a filled buffer in memory, returns the data in the
        corresponding memory location as DataBuffer.

        Args:
            :param timeout_n: (int) Time in buffer_periods that should be waited for an
                incoming msg
            :param verbose: (bool) more debug output
        Returns:
            Index and content of corresponding data buffer
        Raises:
            TimeoutException: If no message is received within
                specified timeout
        """
        while True:
            msg_type, value = self._get_msg(timeout_n)
            value = value[0]
            # logger.debug(f"received msg type {msg_type}")

            if msg_type == commons.MSG_BUF_FROM_PRU:
                ts_start = time.time()
                buf = self.shared_mem.read_buffer(value, verbose)
                if verbose:
                    logger.debug(
                        f"Processing buffer #{ value } from shared memory took "
                        f"{ round(1e3 * (time.time()-ts_start), 2) } ms"
                    )
                return value, buf

            elif msg_type == commons.MSG_DBG_PRINT:
                logger.info(f"Received cmd to print: {value}")
                continue

            elif msg_type == commons.MSG_DEP_ERR_INCMPLT:
                raise ShepherdIOException(
                    "Got incomplete buffer", commons.MSG_DEP_ERR_INCMPLT, value
                )

            elif msg_type == commons.MSG_DEP_ERR_INVLDCMD:
                raise ShepherdIOException(
                    "PRU received invalid command",
                    commons.MSG_DEP_ERR_INVLDCMD,
                    value,
                )
            elif msg_type == commons.MSG_DEP_ERR_NOFREEBUF:
                raise ShepherdIOException(
                    "PRU ran out of buffers",
                    commons.MSG_DEP_ERR_NOFREEBUF,
                    value,
                )
            else:
                raise ShepherdIOException(
                    f"Expected msg type { commons.MSG_BUF_FROM_PRU } "
                    f"got { msg_type }[{ value }]"
                )
