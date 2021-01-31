# -*- coding: utf-8 -*-

"""
shepherd.shepherd_io
~~~~~
Interface layer, abstracting low-level functionality provided by PRUs and
kernel module. User-space part of the double-buffered data exchange protocol.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""

import os
import weakref
import logging
import time
import atexit
import struct
import mmap
import sys
from typing import NoReturn

import numpy as np
import collections
from pathlib import Path
from periphery import GPIO

from shepherd import sysfs_interface
from shepherd import commons
from shepherd.calibration import CalibrationData
from shepherd.sysfs_interface import SysfsInterfaceException

logger = logging.getLogger(__name__)

ID_ERR_TIMEOUT = 100

gpio_pin_nums = {
    "target_pwr_sel": 31,
    "target_io_en": 60,
    "target_io_sel": 30,
    "en_shepherd": 23,
}

prev_timestamp = 0


def flatten_dict_list(dl) -> list:
    """ small helper FN to convert (multi-dimensional) dicts or lists to 1D list

    Args:
        dl: (multi-dimensional) dicts or lists
    Returns:
        1D list
    """
    if len(dl) == 1:
        if isinstance(dl[0], list):
            result = flatten_dict_list(dl[0])
        else:
            result = dl
    elif isinstance(dl[0], list):
        result = flatten_dict_list(dl[0]) + flatten_dict_list(dl[1:])
    else:
        result = [dl[0]] + flatten_dict_list(dl[1:])
    return result


class ShepherdIOException(Exception):
    def __init__(self, message: str, id: int = 0, value: int = 0):
        super().__init__(message)
        self.id = id
        self.value = value


class GPIOEdges(object):
    """Python representation of GPIO edge buffer

    On detection of an edge, shepherd stores the state of all sampled GPIO pins
    together with the corresponding timestamp
    """

    def __init__(
        self, timestamps_ns: np.ndarray = None, values: np.ndarray = None
    ):
        if timestamps_ns is None:
            self.timestamps_ns = np.empty(0)
            self.values = np.empty(0)
        else:
            self.timestamps_ns = timestamps_ns
            self.values = values

    def __len__(self):
        return self.values.size


class DataBuffer(object):
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
    ):
        self.timestamp_ns = timestamp_ns
        self.voltage = voltage
        self.current = current
        if gpio_edges is not None:
            self.gpio_edges = gpio_edges
        else:
            self.gpio_edges = GPIOEdges()

    def __len__(self):
        return self.voltage.size


class SharedMem(object):
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
        self.size = size
        self.n_buffers = n_buffers
        self.samples_per_buffer = samples_per_buffer

        self.mapped_mem = None
        self.devmem_fd = None

        # With knowledge of structure of each buffer, we calculate its total size
        self.buffer_size = (
            # Header: 64 bit timestamp + 32 bit counter
            8 + 4 +
            # Actual IV data, 32 bit for each current and voltage
            + 2 * 4 * self.samples_per_buffer
            # GPIO edge count
            + 4
            # 64 bit timestamp per GPIO event
            + 8 * commons.MAX_GPIO_EVT_PER_BUFFER
            # 16 bit GPIO state per GPIO event
            + 2 * commons.MAX_GPIO_EVT_PER_BUFFER  # GPIO edge data
        )  # NOTE: atm 4h of bug-search lead to this hardcoded piece
        # TODO: put number in shared-mem

        logger.debug(f"Individual buffer size:\t{ self.buffer_size } byte")

    def __enter__(self):
        self.devmem_fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)

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

    def read_buffer(self, index: int) -> DataBuffer:
        """Extracts buffer from shared memory.

        Extracts data from buffer with given index from the shared memory area
        in RAM.

        Args:
            index (int): Buffer index. 0 <= index < n_buffers

        Returns:
            DataBuffer object pointing to extracted data
        """
        # The buffers are organized as an array in shared memory
        # buffer i starts at i * buffersize
        buffer_offset = index * self.buffer_size
        logger.debug(f"Seeking 0x{index * self.buffer_size:04X}")
        self.mapped_mem.seek(buffer_offset)

        # Read the header consisting of 12 (4 + 8 Bytes)
        header = self.mapped_mem.read(12)

        # First two values are number of samples and 64 bit timestamp
        n_samples, buffer_timestamp = struct.unpack("=LQ", header)
        logger.debug(
            f"Got buffer #{ index } with len {n_samples} and timestamp {buffer_timestamp}"
        )

        # sanity-check of received timestamp, TODO: python knows the duration between timestamps
        global prev_timestamp
        diff_ms = round((buffer_timestamp - prev_timestamp) / 1e6, 3) if (prev_timestamp > 0) else 100
        if buffer_timestamp == 0:
            logger.error(f"ZERO      timestamp detected after recv it from PRU")
        if diff_ms < 0:
            logger.error(f"BACKWARDS timestamp-jump detected after recv it from PRU -> {diff_ms} ms")
        if diff_ms < 95:
            logger.error(f"TOO SMALL timestamp-jump detected after recv it from PRU -> {diff_ms} ms")
        if diff_ms > 105:
            logger.error(f"Forwards  timestamp-jump detected after recv it from PRU -> {diff_ms} ms")
        prev_timestamp = buffer_timestamp

        # Each buffer contains (n=) samples_per_buffer values. We have 2 variables
        # (voltage and current), thus samples_per_buffer/2 samples per variable
        # TODO: this is a hardcoded struct with lots of magic numbers. also: why calculate sub-offsets every time?

        voltage_offset = buffer_offset + 12
        voltage = np.frombuffer(
            self.mapped_mem,
            "=u4",
            count=self.samples_per_buffer,
            offset=voltage_offset,
        )

        current_offset = voltage_offset + 4 * self.samples_per_buffer
        current = np.frombuffer(
            self.mapped_mem,
            "=u4",
            count=self.samples_per_buffer,
            offset=current_offset,
        )

        gpio_struct_offset = (
            buffer_offset
            + 12  # header
            + 2
            * 4
            * self.samples_per_buffer  # current and voltage samples (4B)
        )
        # Jump over header and all sampled data
        self.mapped_mem.seek(gpio_struct_offset)
        # Read the number of gpio events in the buffer
        (n_gpio_events,) = struct.unpack("=L", self.mapped_mem.read(4))
        if n_gpio_events > 0:
            logger.info(f"Buffer contains {n_gpio_events} gpio events")

        gpio_ts_offset = gpio_struct_offset + 4
        gpio_timestamps_ns = np.frombuffer(
            self.mapped_mem, "=u8", count=n_gpio_events, offset=gpio_ts_offset
        )
        gpio_values_offset = (
            gpio_ts_offset + 8 * commons.MAX_GPIO_EVT_PER_BUFFER
        )
        gpio_values = np.frombuffer(
            self.mapped_mem,
            "=u2",
            count=n_gpio_events,
            offset=gpio_values_offset,
        )
        gpio_edges = GPIOEdges(gpio_timestamps_ns, gpio_values)

        return DataBuffer(voltage, current, buffer_timestamp, gpio_edges)

    def write_buffer(self, index, voltage, current) -> NoReturn:

        buffer_offset = self.buffer_size * index
        # Seek buffer location in memory and skip 12B header
        self.mapped_mem.seek(buffer_offset + 12)
        self.mapped_mem.write(voltage)
        self.mapped_mem.write(current)


class VirtualSourceData(object):
    """
    Container for VS Settings, Data will be checked and completed
    - settings will be created from default values when omitted
    - internal settings are derived from existing values (PRU has no FPU, so it is done here)
    - settings can be exported in required format
    """
    vss: dict = None

    def __init__(self, vs_settings: dict = None):
        """ Container for VS Settings, Data will be checked and completed

        Args:
            vs_settings: if omitted, the data is generated from default values
        """
        if vs_settings is None:
            self.vss = dict()
        elif isinstance(vs_settings, VirtualSourceData):
            self.vss = vs_settings.vss
        elif isinstance(vs_settings, dict):
            self.vss = vs_settings
        else:
            raise NotImplementedError(f"VirtualSourceData was instantiated with {type(vs_settings)}, can't be handled")
        self.check_and_complete()

    def get_as_dict(self) -> dict:
        """ offers a checked and completed version of the settings

        Returns:
            internal settings container
        """
        return self.vss

    def get_as_list(self) -> list:
        """ multi-level dict is flattened, good for testing

        Returns:
            1D-Content
        """
        return flatten_dict_list(self.vss)

    def export_for_sysfs(self) -> list:
        """ prepares virtsource settings for PRU core (a lot of unit-conversions)

        The current emulator in PRU relies on the virtsource settings.
        This Fn add values in correct order and convert to requested unit

        Returns:
            int-list (2nd level for LUTs) that can be feed into sysFS
        """
        vs_list = list([])

        vs_list.append(int(self.vss["converter_mode"]))

        vs_list.append(int(self.vss["c_output_uf"] * 1e3))  # nF

        vs_list.append(int(self.vss["v_input_boost_threshold_mV"] * 1e3))  # uV

        vs_list.append(int(self.vss["c_storage_uf"] * 1e3))  # nF
        vs_list.append(int(self.vss["v_storage_init_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["v_storage_max_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["v_storage_leak_nA"] * 1))  # nA

        vs_list.append(int(self.vss["v_storage_enable_threshold_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["v_storage_disable_threshold_mV"] * 1e3))  # uV

        vs_list.append(int(self.vss["interval_check_thresholds_ms"] * 1e6))  # ns

        vs_list.append(int(self.vss["v_pwr_good_low_threshold_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["v_pwr_good_high_threshold_mV"] * 1e3))  # uV

        vs_list.append(int(self.vss["dV_store_en_mV"] * 1e3))  # uV

        vs_list.append(int(self.vss["v_output_mV"] * 1e3))  # uV

        vs_list.append(int(self.vss["dV_store_low_mV"] * 1e3))  # uV

        vs_list.append([int(value) for value in self.vss["LUT_inp_efficiency_n8"]])

        # was n8, is now n10
        vs_list.append([int((2 ** 18) / value) for value in self.vss["LUT_output_efficiency_n8"]])
        return vs_list

    def add_enable_voltage_drop(self) -> NoReturn:
        """
        compensate for (hard to detect) current-surge of real capacitors when converter gets turned on
        -> this can be const value, because the converter always turns on with "V_storage_enable_threshold_uV"
        TODO: currently neglecting: delay after disabling converter, boost only has simpler formula, second enabling when V_Cap >= V_out

        Math behind this calculation:
        Energy-Change Storage Cap   ->  E_new = E_old - E_output
        with Energy of a Cap 	    -> 	E_x = C_x * V_x^2 / 2
        combine formulas 		    -> 	C_store * V_store_new^2 / 2 = C_store * V_store_old^2 / 2 - C_out * V_out^2 / 2
        convert formula to V_new 	->	V_store_new^2 = V_store_old^2 - (C_out / C_store) * V_out^2
        convert into dV	 	        ->	dV = V_store_new - V_store_old
        in case of V_cap = V_out 	-> 	dV = V_store_old * (sqrt(1 - C_out / C_store) - 1)
        -> dV values will be reversed (negated), because dV is always negative (Voltage drop)
        """

        # first case: storage cap outside of en/dis-thresholds
        v_old = self.vss["v_storage_enable_threshold_mV"]
        if 1:  # TODO: this is boost-buck case, boost-only has v_out = v_old
            v_out = self.vss["v_output_mV"]
        else:
            v_out = v_old
        c_store = self.vss["c_storage_uf"]
        c_out = self.vss["c_output_uf"]
        self.vss["dV_store_en_mV"] = v_old - pow(pow(v_old, 2) - (c_out / c_store) * pow(v_out, 2), 0.5)

        # second case: storage cap below v_out (only different for enabled buck), enable when >= v_out
        # v_enable is either bucks v_out or same dV-Value is calculated a second time
        self.vss["dV_store_low_mV"] = v_out * (1 - pow(1 - c_out / c_store, 0.5))

    def check_and_complete(self) -> NoReturn:
        """ checks virtual-source-settings for present values, adds default values to missing ones, checks limits
        TODO: fill with values from real BQ-IC
        """
        self._check_num("converter_mode", 100, 4e9)

        self._check_num("c_output_uf", 1, 4e6)

        self._check_num("v_input_boost_threshold_mV", 130, 5000)

        self._check_num("c_storage_uf", 1000, 4e6)
        self._check_num("v_storage_init_mV", 3500, 10000)
        self._check_num("v_storage_max_mV", 4200, 10000)
        self._check_num("v_storage_leak_nA", 10, 4e9)

        self._check_num("v_storage_enable_threshold_mV", 3000, 4e6)
        self._check_num("v_storage_disable_threshold_mV", 2300, 4e6)

        self._check_num("interval_check_thresholds_ms", 65, 4e3)

        self._check_num("v_pwr_good_low_threshold_mV", 2400, 4e6)
        self._check_num("v_pwr_good_high_threshold_mV", 5000, 4e6)

        self._check_num("v_output_mV", 2300, 5000)

        self.add_enable_voltage_drop()
        self._check_num("dV_store_en_mV", 0, 4e6)
        self._check_num("dV_store_low_mV", 0, 4e6)

        # Look up tables, TODO: test if order in PRU-2d-array is maintained,
        self._check_list("LUT_inp_efficiency_n8", 12 * [12 * [128]], 255)
        self._check_list("LUT_output_efficiency_n8", 12 * [200], 255)

    def _check_num(self, setting_key: str, default: float, max_value: float = None) -> NoReturn:
        try:
            set_value = self.vss[setting_key]
        except KeyError:
            set_value = default
            logger.warning(f"[virtSource] Setting {setting_key} was not provided, will be set to default = {default}")
        if not (isinstance(set_value, int) or isinstance(set_value, float)) or (set_value < 0):
            raise NotImplementedError(f"[virtSource] {setting_key} must a single positive number, but is '{set_value}'")
        if (max_value is not None) and (set_value > max_value):
            raise NotImplementedError(f"[virtSource] {setting_key} = {set_value} must be smaller than {max_value}")
        self.vss[setting_key] = set_value

    def _check_list(self, settings_key: str, default: list, max_value: float = 255) -> NoReturn:
        default = flatten_dict_list(default)
        try:
            values = flatten_dict_list(self.vss[settings_key])
        except KeyError:
            values = default
            logger.warning(f"[virtSource] Setting {settings_key} was not provided, will be set to default = {values[0]}")
        if (len(values) != len(default)) or (min(values) < 0) or (max(values) > 255):
            raise NotImplementedError(f"{settings_key} must a list of {len(default)} values, within range of [0; {max_value}]")
        self.vss[settings_key] = values


class ShepherdIO(object):
    """Generic ShepherdIO interface.

    This class acts as interface between kernel module and firmware on the PRUs,
    and user space code. It handles the user space part of the double-buffered
    data-exchange protocol between user space and PRUs and configures the
    hardware by setting corresponding GPIO pins. This class should usually not
    be instantiated, but instead serve as parent class for e.g. Recorder or
    Emulator (see __init__.py).
    """

    # This is part of the singleton implementation
    _instance = None

    def __new__(cls, *args, **kwds):
        """Implements singleton class."""
        if ShepherdIO._instance is None:
            new_class = object.__new__(cls)
            ShepherdIO._instance = weakref.ref(new_class)
        else:
            raise IndexError("ShepherdIO already exists")

        return new_class

    def __init__(self, mode: str):
        """Initializes relevant variables.

        Args:
            mode (str): Shepherd mode, see sysfs_interface for more
        """

        self.rpmsg_fd = None
        self.mode = mode
        self.gpios = dict()
        self.shared_mem = None

    def __del__(self):
        ShepherdIO._instance = None

    def __enter__(self):
        try:

            for name, pin in gpio_pin_nums.items():
                self.gpios[name] = GPIO(pin, "out")

            self._set_shepherd_pcb_power(True)
            self.set_target_io_level_conv(False)

            logger.debug("Shepherd hardware is powered")

            # If shepherd hasn't been terminated properly
            if sysfs_interface.get_state() != "idle":
                sysfs_interface.set_stop()

            sysfs_interface.wait_for_state("idle", 5)
            logger.debug(f"Switching to '{ self.mode }' mode")
            sysfs_interface.write_mode(self.mode)

            # Open the RPMSG channel provided by rpmsg_pru kernel module
            rpmsg_dev = Path("/dev/rpmsg_pru0")
            self.rpmsg_fd = os.open(str(rpmsg_dev), os.O_RDWR | os.O_SYNC)
            os.set_blocking(self.rpmsg_fd, False)
            self._flush_msgs()

            # Ask PRU for base address of shared mem (reserved with remoteproc)
            mem_address = sysfs_interface.get_mem_address()
            # Ask PRU for size of shared memory (reserved with remoteproc)
            mem_size = sysfs_interface.get_mem_size()

            logger.debug(
                f"Shared memory address: \t0x{mem_address:08X}, size: {mem_size} byte"
            )

            # Ask PRU for size of individual buffers
            samples_per_buffer = sysfs_interface.get_samples_per_buffer()
            logger.debug(f"Samples per buffer: \t{ samples_per_buffer }")

            self.n_buffers = sysfs_interface.get_n_buffers()
            logger.debug(f"Number of buffers: \t{ self.n_buffers }")

            self.buffer_period_ns = sysfs_interface.get_buffer_period_ns()
            logger.debug(f"Buffer period: \t\t{ self.buffer_period_ns } ns")

            self.shared_mem = SharedMem(
                mem_address, mem_size, self.n_buffers, samples_per_buffer
            )

            self.shared_mem.__enter__()

        except Exception:
            self._cleanup()
            raise

        sysfs_interface.wait_for_state("idle", 3)
        return self

    def __exit__(self, *args):
        logger.info("exiting analog shepherd_io")
        self._cleanup()

    def _send_msg(self, msg_type: int, value: int) -> NoReturn:
        """Sends a formatted message to PRU0 via rpmsg channel.

        Args:
            msg_type (int): Indicates type of message, must be one of the agreed
                message types part of the data exchange protocol
            value (int): Actual content of the message
        """
        msg = struct.pack("=ii", msg_type, value)
        os.write(self.rpmsg_fd, msg)

    def _get_msg(self, timeout: float = 0.5):
        """Tries to retrieve formatted message from PRU0 via rpmsg channel.

        Args:
            timeout (float): Maximum number of seconds to wait for a message
                before raising timeout exception
        """
        ts_end = time.time() + timeout
        while time.time() < ts_end:
            try:
                rep = os.read(self.rpmsg_fd, 8)
                return struct.unpack("=ii", rep)
            except BlockingIOError:
                time.sleep(0.1)
                continue
        raise ShepherdIOException("Timeout waiting for message", ID_ERR_TIMEOUT)

    def _flush_msgs(self):
        """Flushes rpmsg channel by reading all available bytes."""
        while True:
            try:
                os.read(self.rpmsg_fd, 1)
            except BlockingIOError:
                break

    def start(self, start_time: float = None, wait_blocking: bool = True) -> NoReturn:
        """Starts sampling either now or at later point in time.

        Args:
            start_time (int): Desired start time in unix time
            wait_blocking (bool): If true, block until start has completed
        """
        logger.debug(f"asking kernel module for start at {round(start_time, 2)}")
        sysfs_interface.set_start(int(start_time))
        if wait_blocking:
            self.wait_for_start(1_000_000)

    @staticmethod
    def wait_for_start(timeout: float) -> NoReturn:
        """Waits until shepherd has started sampling.

        Args:
            timeout (float): Time to wait in seconds
        """
        sysfs_interface.wait_for_state("running", timeout)

    def _cleanup(self):

        while sysfs_interface.get_state() != "idle":
            try:
                sysfs_interface.set_stop()
            except Exception as e:
                print(e)
            try:
               sysfs_interface.wait_for_state("idle", 3.0)
            except SysfsInterfaceException:
                logger.warning("CleanupRoutine - send stop-command and waiting for PRU to go to idle")
        self.set_aux_target_voltage(None, 0.0)

        if self.shared_mem is not None:
            self.shared_mem.__exit__()

        if self.rpmsg_fd is not None:
            os.close(self.rpmsg_fd)

        self.set_target_io_level_conv(False)
        self._set_shepherd_pcb_power(False)
        logger.debug("Shepherd hardware is powered down")

    def _set_shepherd_pcb_power(self, state: bool) -> NoReturn:
        """ Controls state of power supplies on shepherd cape.

        Args:
            state (bool): True for on, False for off
        """
        state_str = "enabled" if state else "disabled"
        logger.debug(f"Set power-supplies of shepherd-pcb to {state_str}")
        self.gpios["en_shepherd"].write(state)

    def select_main_target_for_power(self, sel_target_a: bool) -> NoReturn:
        """ choose which targets gets the supply with current-monitor, True = Target A, False = Target B

        shepherd hw-rev2 has two ports for targets and two separate power supplies,
        but only one is able to measure current, the other is considered "auxiliary"

        Args:
            sel_target_a: True to select A, False for B
        """
        current_state = sysfs_interface.get_state()
        if current_state != "idle":
            raise ShepherdIOException(f"Can't switch target-power when shepherd is {current_state}")
        if sel_target_a is None:
            # Target A is Default
            sel_target_a = True
        target = "A" if sel_target_a else "B"
        logger.debug(f"Set routing for (main) supply with current-monitor to target {target}")
        self.gpios["target_pwr_sel"].write(sel_target_a)

    def select_main_target_for_io(self, sel_target_a: bool) -> NoReturn:
        """ choose which targets gets the io-connection (serial, swd, gpio) from beaglebone, True = Target A, False = Target B

        shepherd hw-rev2 has two ports for targets and can switch independently from power supplies

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

        The shepherd cape has bi-directional logic level translators (LSF0108)
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
    def set_aux_target_voltage(cal_settings: CalibrationData, voltage: float) -> NoReturn:
        """ Enables or disables the voltage for the second target

        The shepherd cape has two DAC-Channels that each serve as power supply for a target

        Args:
            cal_settings: CalibrationData, TODO: should it be a class-variable?
            voltage (float): Desired output voltage in volt. Providing 0 or
                False disables supply, setting it to True will link it
                to the other channel
        """
        logger.debug(f"Set voltage of supply for auxiliary Target to {voltage}")
        sysfs_interface.write_dac_aux_voltage(cal_settings, voltage)

    @staticmethod
    def get_aux_voltage(cal_settings: CalibrationData) -> float:
        """ Reads the auxiliary voltage (dac channel B) from the PRU core.

        Args:
            cal_settings: dict with offset/gain

        Returns:
            aux voltage
        """
        return sysfs_interface.read_dac_aux_voltage(cal_settings)

    @staticmethod
    def send_calibration_settings(cal_settings: CalibrationData) -> NoReturn:
        """Sends calibration settings to PRU core

        For the virtual source it is required to have the calibration settings.

        Args:
            cal_settings (CalibrationData): Contains the device's
            calibration settings.
        """
        sysfs_interface.write_calibration_settings(cal_settings.export_for_sysfs())

    def send_virtsource_settings(self, vs_settings: VirtualSourceData) -> NoReturn:
        """ Sends virtsource settings to PRU core
            looks like a dumb one-liner but is needed by the child-classes

        Args:
            vs_settings: Contains the settings for the virtual source.
        """
        if vs_settings is None:
            vs_settings = VirtualSourceData()
        if isinstance(vs_settings, dict):
            vs_settings = VirtualSourceData(vs_settings)
        values = vs_settings.export_for_sysfs()
        sysfs_interface.write_virtsource_settings(values)

    def _return_buffer(self, index: int) -> NoReturn:
        """Returns a buffer to the PRU

        After reading the content of a buffer and potentially filling it with
        emulation data, we have to release the buffer to the PRU to avoid it
        running out of buffers.

        Args:
            index (int): Index of the buffer. 0 <= index < n_buffers
        """

        logger.debug(f"return buffer #{ index } to PRU")
        self._send_msg(commons.MSG_DEP_BUF_FROM_HOST, index)

    def get_buffer(self, timeout: float = 1.0) -> NoReturn:
        """Reads a data buffer from shared memory.

        Polls the RPMSG channel for a message from PRU0 and, if the message
        points to a filled buffer in memory, returns the data in the
        corresponding memory location as DataBuffer.

        Args:
            timeout (float): Time in seconds that should be waited for an
                incoming RPMSG
        Returns:
            Index and content of corresponding data buffer
        Raises:
            TimeoutException: If no message is received on RPMSG within
                specified timeout

        """
        while True:
            msg_type, value = self._get_msg(timeout)
            logger.debug(f"received msg type {msg_type}")
            if msg_type == commons.MSG_DEP_DBG_PRINT:
                logger.info(f"Received print: {value}")
                continue

            elif msg_type == commons.MSG_DEP_BUF_FROM_PRU:
                logger.debug(f"Retrieving buffer { value } from shared memory")
                buf = self.shared_mem.read_buffer(value)
                return value, buf

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
                    (
                        f"Expected msg type { commons.MSG_DEP_BUF_FROM_PRU } "
                        f"got { msg_type }[{ value }]"
                    )
                )
