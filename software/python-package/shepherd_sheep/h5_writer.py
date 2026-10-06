"""
shepherd.datalog
~~~~~
Provides classes for storing and retrieving sampled IV data to/from
HDF5 files.

"""

from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

from typing_extensions import Self

from . import commons
from .h5_monitor_ntp import NTPMonitor
from .h5_recorder_iv import IVRecorder
from .h5_recorder_power import PowerRecorder

if TYPE_CHECKING:
    import h5py

    from .h5_monitor_abc import Monitor

from shepherd_core.data_models.base.calibration import CalibrationEmulator as CalEmu
from shepherd_core.data_models.base.calibration import CalibrationHarvester as CalHrv
from shepherd_core.data_models.base.calibration import CalibrationSeries as CalSeries
from shepherd_core.data_models.content.enum_datatypes import Compression
from shepherd_core.data_models.experiment import SystemLogging
from shepherd_core.data_models.experiment import UartLogging
from shepherd_core.writer import Writer as CoreWriter

from .h5_monitor_kernel import KernelMonitor
from .h5_monitor_phc2sys import PHC2SYSMonitor
from .h5_monitor_phc2sys_log import PHC2SYSLogMonitor
from .h5_monitor_ptp import PTPMonitor
from .h5_monitor_ptp_log import PTPLogMonitor
from .h5_monitor_sheep import SheepMonitor
from .h5_monitor_sysutil import SysUtilMonitor
from .h5_monitor_uart import UARTMonitor
from .h5_recorder_gpio import GpioRecorder
from .h5_recorder_pru import PruRecorder
from .logger import log
from .shared_mem_gpio_output import GPIOTrace
from .shared_mem_iv_input import IVTrace
from .shared_mem_util_output import UtilTrace


class Writer(CoreWriter):
    """Stores data coming from PRU's in HDF5 format

    NOTE: this is optimized for live measurements.
    Individual recorders/monitors are rate limited and queued to unblock write-commands.

    Args:
        file_path (Path): Name of the HDF5 file that data will be written to
        cal_data (CalibrationEmulator or CalibrationHarvester): Data is written as raw ADC
            values. We need calibration data in order to convert to physical
            units later.
        mode (str): Indicates if this is data from harvester or emulator
        force_overwrite (bool): Overwrite existing file with the same name
    """

    RATES_SUPPORTED = (10, 100, 1_000, 100_000)

    def __init__(  # noqa: PLR0917
        self,
        file_path: Path,
        mode: str | None = None,
        datatype: str | None = None,
        window_samples: int | None = None,
        cal_data: CalSeries | CalEmu | CalHrv | None = None,
        compression: Compression = Compression.default,
        sample_rate: int | None = None,
        *,
        modify_existing: bool = False,
        force_overwrite: bool = False,
        only_power: bool = False,
        verbose: bool | None = True,
    ) -> None:
        # hopefully overwrite defaults from Reader
        self.samplerate_sps: int = 10**9 // commons.SAMPLE_INTERVAL_NS
        self.reduce: bool = False
        self.reduction_factor: int = 1
        if isinstance(sample_rate, int):
            if sample_rate not in self.RATES_SUPPORTED:
                raise ValueError(
                    "Data-rate for Power must be in [Hz, Samples-per-second]: %s",
                    self.RATES_SUPPORTED,
                )
            self.reduce: bool = sample_rate != self.samplerate_sps
            self.reduction_factor: int = self.samplerate_sps // sample_rate
            self.samplerate_sps = sample_rate
        if self.reduce:
            log.info("Activated custom sample-rate: %d", self.samplerate_sps)

        # TODO: derive verbose-state
        super().__init__(
            file_path,
            mode,
            datatype,
            window_samples,
            cal_data,
            compression,
            big_chunks=False,
            modify_existing=modify_existing,
            force_overwrite=force_overwrite,
            verbose=verbose,
        )
        self.only_power = only_power

        self.grp_data: h5py.Group = self.h5file["data"]

        # prepare Monitors
        self.sysutil_log_enabled: bool = True
        self.monitors: list[Monitor] = []

    def __enter__(self) -> Self:
        """Initializes the structure of the HDF5 file

        HDF5 is hierarchically structured and before writing data, we have to
        set up this structure, i.e. creating the right groups with corresponding
        data types. We will store 3 types of data in a Writer database: The
        actual IV samples recorded either from the harvester (during recording)
        or the target (during emulation). Any log messages, that can be used to
        store relevant events or tag some parts of the recorded data. And lastly
        the state of the GPIO pins.

        """
        super().__enter__()

        # Create group for additional recorders
        self.gpio_grp = self.h5file.create_group("gpio")
        self.pru_util_grp = self.h5file.create_group("pru_util")

        # prepare recorders
        self.rec_gpio = GpioRecorder(self.gpio_grp, compression=self._compression)
        self.rec_pru = PruRecorder(self.pru_util_grp, compression=self._compression)
        if self.only_power:
            self.power_grp = self.h5file.create_group("power")
            self.rec_iv = PowerRecorder(
                target=self.power_grp,
                cal_data=self._cal,
                compression=self._compression,
                reduction_factor=self.reduction_factor,
            )
        else:
            self.rec_iv = IVRecorder(self.grp_data, self.reduction_factor)

        # targets for logging-monitor # TODO: redesign? all should be kept in data_0
        self.sheep_grp = self.h5file.create_group("sheep")
        self.uart_grp = self.h5file.create_group("uart")
        self.sys_util_grp = self.h5file.create_group("sys_util")
        self.kernel_grp = self.h5file.create_group("kernel")
        self.ptp_grp = self.h5file.create_group("ptp")
        self.ptp_log_grp = self.h5file.create_group("ptp_log")
        self.phc_grp = self.h5file.create_group("phc2sys")
        self.phc_log_grp = self.h5file.create_group("phc2sys_log")
        self.ntp_grp = self.h5file.create_group("ntp")
        return self

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        # end recorders
        self.rec_pru.__exit__()
        self.rec_gpio.__exit__()
        self.rec_iv.__exit__()  # can be power or iv

        # end monitors
        for monitor in self.monitors:
            monitor.__exit__()
        log.info("Wrote result to: %s", self.file_path.as_posix())
        super().__exit__()

    def write_iv_buffer(self, data: IVTrace) -> None:
        """Writes data from buffer to file-write-queue.

        Note: storage is queued to unblock write-commands, also rate-limited to even load.

        Args:
            data: buffer-segment containing IV data
        """
        self.rec_iv.write(data)  # dynamically power- or iv-recorder

    def write_gpio_buffer(self, data: GPIOTrace) -> None:
        # Note: storage is queued to unblock write-commands, also rate-limited to even load.
        self.rec_gpio.write(data)

    def write_util_buffer(self, data: UtilTrace) -> None:
        # Note: storage is queued to unblock write-commands, also rate-limited to even load.
        self.rec_pru.write(data)

    def flush_queues(self) -> None:
        self.rec_pru.flush_queue()
        self.rec_gpio.flush_queue()
        self.rec_iv.flush_queue()

    def start_monitors(
        self,
        sys: SystemLogging | None = None,
        uart: UartLogging | None = None,
    ) -> None:
        if sys is not None and sys.kernel:
            self.monitors.append(KernelMonitor(self.kernel_grp, self._compression))
        if sys is not None and sys.time_sync:
            self.monitors.append(PTPMonitor(self.ptp_grp, self._compression))
            self.monitors.append(PTPLogMonitor(self.ptp_log_grp, self._compression))
            self.monitors.append(PHC2SYSMonitor(self.phc_grp, self._compression))
            self.monitors.append(PHC2SYSLogMonitor(self.phc_log_grp, self._compression))
            self.monitors.append(NTPMonitor(self.ntp_grp, self._compression))
        if sys is not None and sys.sys_util:
            self.monitors.append(SysUtilMonitor(self.sys_util_grp, self._compression))
        if uart is not None:
            self.monitors.append(
                UARTMonitor(
                    self.uart_grp,
                    compression=self._compression,
                    config=uart,
                ),
            )
        if sys is not None and sys.sheep:
            self.monitors.append(SheepMonitor(self.sheep_grp, self._compression))

    def check_monitors(self) -> None:
        """Check state of Monitors.

        Emitting Warnings and errors is delegated to each monitor.
        """
        for monitor in self.monitors:
            if hasattr(monitor, "check_status"):
                monitor.check_status()
