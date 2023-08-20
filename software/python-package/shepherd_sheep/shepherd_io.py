"""
shepherd.shepherd_io
~~~~~
Interface layer, abstracting low-level functionality provided by PRUs and
kernel module. User-space part of the double-buffered data exchange protocol.

:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import time
from contextlib import suppress
from typing import Optional
from typing import Union

from pydantic import validate_call
from shepherd_core import CalibrationEmulator
from shepherd_core import CalibrationHarvester
from shepherd_core.data_models import GpioTracing
from shepherd_core.data_models import PowerTracing
from shepherd_core.data_models.content.virtual_harvester import HarvesterPRUConfig
from shepherd_core.data_models.content.virtual_source import ConverterPRUConfig
from shepherd_core.data_models.testbed import TargetPort

from . import commons
from . import sysfs_interface as sfs
from .logger import log
from .shared_memory import SharedMemory
from .sysfs_interface import check_sys_access

# allow importing shepherd on x86 - for testing
with suppress(ModuleNotFoundError):
    from periphery import GPIO


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

    @classmethod
    def __new__(cls, *args, **kwds):
        """Implements singleton class."""
        if ShepherdIO._instance is None:
            new_class = object.__new__(cls)
            ShepherdIO._instance = new_class
            # was raising on reuse and stored weakref.ref before
            return new_class
        else:
            log.debug("ShepherdIO-Singleton reused")
            return ShepherdIO._instance

    def __init__(
        self,
        mode: str,
        trace_iv: Optional[PowerTracing],
        trace_gpio: Optional[GpioTracing],
    ):
        """Initializes relevant variables.

        Args:
            mode (str): Shepherd mode, see sysfs_interface for more
        """
        check_sys_access()

        if not sfs.pru0_firmware_is_default():
            sfs.load_pru0_firmware("shepherd")

        self.mode = mode
        if mode in ["harvester", "emulator"]:
            self.component = mode  # TODO: still needed?
        else:
            self.component = "emulator"
        self.gpios = {}

        # self.shared_mem: Optional[SharedMem] = None # noqa: E800
        self._buffer_period: float = 0.1  # placeholder value

        self.trace_iv = trace_iv
        self.trace_gpio = trace_gpio

        # placeholders
        self.mem_address = 0
        self.mem_size = 0
        self.samples_per_buffer = 0
        self.buffer_period_ns = 0
        self.n_buffers = 0
        self.shared_mem: SharedMemory

    def __del__(self):
        log.debug("Now deleting ShepherdIO")
        ShepherdIO._instance = None

    def __enter__(self):
        try:
            for name, pin in gpio_pin_nums.items():
                self.gpios[name] = GPIO(pin, "out")

            self.set_shepherd_pcb_power(True)
            self.set_io_level_converter(False)

            log.debug("Shepherd hardware is powered up")

            # If shepherd hasn't been terminated properly
            self.reinitialize_prus()
            log.debug("Switching to '%s'-mode", self.mode)
            sfs.write_mode(self.mode)

            # clean up msg-channel provided by kernel module
            self._flush_msgs()

            self.refresh_shared_mem()

        except Exception:
            log.exception("ShepherdIO.Init caught an exception -> exit now")
            self._cleanup()
            raise

        sfs.wait_for_state("idle", 3)
        return self

    def __exit__(self, *args):  # type: ignore
        log.info("Now exiting ShepherdIO")
        self._cleanup()
        ShepherdIO._instance = None

    @staticmethod
    def _send_msg(msg_type: int, values: Union[int, list]) -> None:
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

    def start(
        self,
        start_time: Optional[float] = None,
        wait_blocking: bool = True,
    ) -> None:
        """Starts sampling either now or at later point in time.

        Args:
            start_time (int): Desired start time in unix time
            wait_blocking (bool): If true, block until start has completed
        """
        if isinstance(start_time, (float, int)):
            log.debug("asking kernel module for start at %.2f", start_time)
        sfs.set_start(start_time)
        if wait_blocking:
            self.wait_for_start(3_000_000)

    @staticmethod
    def wait_for_start(timeout: float) -> None:
        """Waits until shepherd has started sampling.

        Args:
            timeout (float): Time to wait in seconds
        """
        sfs.wait_for_state("running", timeout)

    def reinitialize_prus(self) -> None:
        sfs.set_stop(force=True)  # forces idle
        sfs.wait_for_state("idle", 5)

    def refresh_shared_mem(self):
        if hasattr(self, "shared_mem") and isinstance(self.shared_mem, SharedMemory):
            self.shared_mem.__exit__()

        # Ask PRU for base address of shared mem (reserved with remoteproc)
        self.mem_address = sfs.get_mem_address()
        # Ask PRU for size of shared memory (reserved with remoteproc)
        self.mem_size = sfs.get_mem_size()

        log.debug(
            "Shared memory address: \t%s, size: %d byte",
            f"0x{self.mem_address:08X}",
            # ⤷ not directly in message because of colorizer
            self.mem_size,
        )

        # Ask PRU for size of individual buffers
        self.samples_per_buffer = sfs.get_samples_per_buffer()
        log.debug("Samples per buffer: \t%d", self.samples_per_buffer)

        self.n_buffers = sfs.get_n_buffers()
        log.debug("Number of buffers: \t%d", self.n_buffers)

        self.buffer_period_ns = sfs.get_buffer_period_ns()
        self._buffer_period = self.buffer_period_ns / 1e9
        log.debug("Buffer period: \t\t%.3f s", self._buffer_period)

        self.shared_mem = SharedMemory(
            self.mem_address,
            self.mem_size,
            self.n_buffers,
            self.samples_per_buffer,
            self.trace_iv,
            self.trace_gpio,
        )
        self.shared_mem.__enter__()

    def _cleanup(self):
        log.debug("ShepherdIO is commanded to power down / cleanup")
        count = 1
        while count < 6 and sfs.get_state() != "idle":
            try:
                sfs.set_stop(force=True)
            except sfs.SysfsInterfaceException:
                log.exception(
                    "CleanupRoutine caused an exception while trying to stop PRU (n=%d)",
                    count,
                )
            try:
                sfs.wait_for_state("idle", 3.0)
            except sfs.SysfsInterfaceException:
                log.warning(
                    "CleanupRoutine caused an exception while waiting for PRU to go to idle (n=%d)",
                    count,
                )
            count += 1
        if sfs.get_state() != "idle":
            log.warning(
                "CleanupRoutine gave up changing state, still '%s'",
                sfs.get_state(),
            )
        self.set_aux_target_voltage(0.0)

        if self.shared_mem is not None:
            self.shared_mem.__exit__()
            self.shared_mem = None

        self.set_io_level_converter(False)
        self.set_power_state_emulator(False)
        self.set_power_state_recorder(False)
        self.set_shepherd_pcb_power(False)
        log.debug("Shepherd hardware is now powered down")

    def set_shepherd_pcb_power(self, state: bool) -> None:
        """Controls state of power supplies on shepherd cape.

        Args:
            state (bool): True for on, False for off
        """
        state_str = "enabled" if state else "disabled"
        log.debug("Set power-supplies of shepherd-cape to %s", state_str)
        self.gpios["en_shepherd"].write(state)
        if state:
            time.sleep(0.5)  # time to stabilize voltage-drop

    def set_power_state_recorder(self, state: bool) -> None:
        """
        triggered pin is currently connected to ADCs reset-line
        NOTE: this might be extended to DAC as well

        :param state: bool, enable to get ADC out of reset
        :return:
        """
        state_str = "enabled" if state else "disabled"
        log.debug("Set Recorder of shepherd-cape to %s", state_str)
        self.gpios["en_recorder"].write(state)
        if state:
            time.sleep(0.3)  # time to stabilize voltage-drop

    def set_power_state_emulator(self, state: bool) -> None:
        """
        triggered pin is currently connected to ADCs reset-line
        NOTE: this might be extended to DAC as well

        :param state: bool, enable to get ADC out of reset
        :return:
        """
        state_str = "enabled" if state else "disabled"
        log.debug("Set Emulator of shepherd-cape to %s", state_str)
        self.gpios["en_emulator"].write(state)
        if state:
            time.sleep(0.3)  # time to stabilize voltage-drop

    @staticmethod
    def convert_target_port_to_bool(target: Union[TargetPort, str, bool, None]) -> bool:
        if target is None:
            return True
        elif isinstance(target, str):
            return TargetPort[target] == TargetPort.A
        elif isinstance(target, TargetPort):
            return target == TargetPort.A
        elif isinstance(target, bool):
            return target
        raise ValueError(
            f"Parameter 'target' must be A or B (was {target}, type {type(target)})",
        )

    def select_port_for_power_tracking(
        self,
        target: Union[TargetPort, bool, None],
    ) -> None:
        """
        choose which targets (A or B) gets the supply with current-monitor,

        shepherd hw-rev2 has two ports for targets and two separate power supplies,
        but only one is able to measure current, the other is considered "auxiliary"

        Args:
            target: A or B for that specific Target-Port
        """
        current_state = sfs.get_state()
        if current_state != "idle":
            self.reinitialize_prus()
        value = self.convert_target_port_to_bool(target)
        log.debug(
            "Set routing for (main) supply with current-monitor to target %s",
            target,
        )
        self.gpios["target_pwr_sel"].write(value)
        if current_state != "idle":
            self.start(wait_blocking=True)

    def select_port_for_io_interface(
        self,
        target: Union[TargetPort, bool, None],
    ) -> None:
        """choose which targets (A or B) gets the io-connection (serial, swd, gpio) from beaglebone,

        shepherd hw-rev2 has two ports for targets and can switch independently
        between power supplies

        Args:
            target: A or B for that specific Target-Port
        """
        value = self.convert_target_port_to_bool(target)
        log.debug("Set routing for IO to Target %s", target)
        self.gpios["target_io_sel"].write(value)

    def set_io_level_converter(self, state: bool) -> None:
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
        log.debug("Set target-io level converter to %s", state_str)
        self.gpios["target_io_en"].write(state)

    @staticmethod
    def set_aux_target_voltage(
        voltage: float,
        cal_emu: Optional[CalibrationEmulator] = None,
    ) -> None:
        """Enables or disables the voltage for the second target

        The shepherd cape has two DAC-Channels that each serve as power supply for a target

        Args:
            cal_emu: CalibrationEmulator,
            voltage (float): Desired output voltage in volt. Providing 0 or
                False disables supply, setting it to True will link it
                to the other channel
        """
        sfs.write_dac_aux_voltage(voltage, cal_emu)

    @staticmethod
    def get_aux_voltage(cal_emu: Optional[CalibrationEmulator] = None) -> float:
        """Reads the auxiliary voltage (dac channel B) from the PRU core.

        Args:
            cal_emu: dict with offset/gain

        Returns:
            aux voltage
        """
        return sfs.read_dac_aux_voltage(cal_emu)

    @validate_call
    def send_calibration_settings(
        self,
        cal_: Union[CalibrationEmulator, CalibrationHarvester, None],
    ) -> None:
        """Sends calibration settings to PRU core

        For the virtual source it is required to have the calibration settings.
        Note: to apply these settings the pru has to do a re-init (reset)

        Args:
            cal_ (CalibrationEmulation or CalibrationHarvester): Contains the device's
            calibration settings.
        """
        if not cal_:
            if self.component == "harvester":
                cal_ = CalibrationHarvester()
            else:
                cal_ = CalibrationEmulator()
        cal_dict = cal_.export_for_sysfs()
        sfs.write_calibration_settings(cal_dict)

    @staticmethod
    def send_virtual_converter_settings(
        settings: ConverterPRUConfig,
    ) -> None:
        """Sends virtsource settings to PRU core
        looks like a simple one-liner but is needed by the child-classes
        Note: to apply these settings the pru has to do a re-init (reset)

        :param settings: Contains the settings for the virtual source.
        """
        sfs.write_virtual_converter_settings(settings)

    @staticmethod
    def send_virtual_harvester_settings(
        settings: HarvesterPRUConfig,
    ) -> None:
        """Sends virtsource settings to PRU core
        looks like a simple one-liner but is needed by the child-classes
        Note: to apply these settings the pru has to do a re-init (reset)

        :param settings: Contains the settings for the virtual source.
        """
        sfs.write_virtual_harvester_settings(settings)

    def _return_buffer(self, index: int) -> None:
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

            if msg_type == commons.MSG_BUF_FROM_PRU:
                ts_start = time.time()
                buf = self.shared_mem.read_buffer(value, verbose)
                if verbose:
                    log.debug(
                        "Processing buffer #%d from shared memory took %.2f ms",
                        value,
                        1e3 * (time.time() - ts_start),
                    )
                return value, buf

            elif msg_type == commons.MSG_DBG_PRINT:
                log.info("Received cmd to print: %d", value)
                continue

            elif msg_type == commons.MSG_DEP_ERR_INCMPLT:
                raise ShepherdIOException(
                    "Got incomplete buffer",
                    commons.MSG_DEP_ERR_INCMPLT,
                    value,
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
                    f"got { msg_type }[{ value }]",
                )
