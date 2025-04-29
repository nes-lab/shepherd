import mmap
import os
import threading
from contextlib import ExitStack
from types import TracebackType

from shepherd_core.data_models import GpioTracing
from shepherd_core.data_models import PowerTracing
from typing_extensions import Self

from . import sysfs_interface as sfs
from .logger import log
from .shared_mem_gpio_output import SharedMemGPIOOutput
from .shared_mem_iv_input import SharedMemIVInput
from .shared_mem_iv_output import SharedMemIVOutput
from .shared_mem_util_output import SharedMemUtilOutput


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
        cfg_iv: PowerTracing | None,
        cfg_gpio: GpioTracing | None,
        start_timestamp_ns: int,
        n_samples_per_segment: int | None = None,
        # TODO: add util-config ??
    ) -> None:
        """Initializes relevant parameters for shared memory area.

        Args:

        """
        # With knowledge of structure of each buffer, we calculate its total size
        if (
            sfs.get_trace_iv_inp_size()
            != sfs.get_trace_iv_out_address() - sfs.get_trace_iv_inp_address()
        ):
            raise ValueError("IV-Inp-Buffer does not fit into address-space?!?")
        if (
            sfs.get_trace_iv_out_size()
            > sfs.get_trace_gpio_address() - sfs.get_trace_iv_out_address()
        ):
            raise ValueError("IV-Out-Buffer does not fit into address-space?!?")
        if sfs.get_trace_gpio_size() > sfs.get_trace_util_address() - sfs.get_trace_gpio_address():
            raise ValueError("GPIO-Buffer does not fit into address-space?!?")

        self._address = sfs.get_trace_iv_inp_address()
        self._size = (
            sfs.get_trace_iv_inp_size()
            + sfs.get_trace_iv_out_size()
            + sfs.get_trace_gpio_size()
            + sfs.get_trace_util_size()
        )
        self._fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        self._mm = mmap.mmap(
            fileno=self._fd,
            length=self._size,
            flags=mmap.MAP_SHARED,
            access=mmap.PROT_WRITE,
            offset=self._address,
        )
        # TODO: could it also be async? might be error-source

        self.iv_inp = SharedMemIVInput(self._mm, n_samples_per_segment)
        self.iv_out = SharedMemIVOutput(self._mm, cfg_iv, start_timestamp_ns)
        self.gpio = SharedMemGPIOOutput(self._mm, cfg_gpio, start_timestamp_ns)
        self.util = SharedMemUtilOutput(self._mm)
        self._stack = ExitStack()
        # overflow detector
        self.event = threading.Event()
        self.thread: threading.Thread | None = None
        self.poll_interval: float = min(
            self.iv_inp.poll_interval,
            self.iv_out.poll_interval,
            self.gpio.poll_interval,
            self.util.poll_interval,
        )

    def __enter__(self) -> Self:
        self._stack.enter_context(self.iv_inp)
        self._stack.enter_context(self.iv_out)
        self._stack.enter_context(self.gpio)
        self._stack.enter_context(self.util)
        self.thread = threading.Thread(
            target=self.thread_overflow_detection,
            daemon=True,
            name="Shp.SharedMem.OverflowDetector",
        )
        self.thread.start()
        return self

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=2 * self.poll_interval)
            if self.thread.is_alive():
                log.error(
                    "[%s] thread failed to end itself - will delete that instance",
                    type(self).__name__,
                )
            self.thread = None
        self._stack.close()
        if self._mm is not None:
            self._mm.close()
        if self._fd is not None:
            os.close(self._fd)

    def handle_backpressure(
        self, *, iv_inp: bool = False, iv_out: bool = False, gpio: bool = False, util: bool = True
    ) -> None:
        if (
            (iv_inp and self.iv_inp.fill_level < 20)
            or (iv_out and self.iv_out.fill_level > 80)
            or (gpio and self.gpio.fill_level > 80)
            or (util and self.util.fill_level > 80)
        ):
            # warning will be generated in read()-fn
            self.gpio.read(discard=True)

    def thread_overflow_detection(self) -> None:
        log.debug("[%s] Overflow-Detector started", type(self).__name__)
        while not self.event.is_set():
            # overflow detection is delegated to each buffer
            self.iv_inp.get_size_available()
            self.iv_out.get_size_available()
            self.gpio.get_size_available()
            self.util.get_size_available()
            self.event.wait(self.poll_interval)
        log.debug("[%s] Overflow-Detector stopped", type(self).__name__)
