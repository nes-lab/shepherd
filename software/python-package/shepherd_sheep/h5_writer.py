"""
shepherd.datalog
~~~~~
Provides classes for storing and retrieving sampled IV data to/from
HDF5 files.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
from pathlib import Path
from typing import List
from typing import Optional
from typing import Union

import h5py
import numpy as np
import yaml
from shepherd_core import CalibrationEmulator as CalEmu
from shepherd_core import CalibrationHarvester as CalHrv
from shepherd_core import CalibrationSeries as CalSeries
from shepherd_core import Writer as CoreWriter
from shepherd_core.data_models import GpioTracing
from shepherd_core.data_models import SystemLogging
from shepherd_core.data_models.task import Compression

from .commons import GPIO_LOG_BIT_POSITIONS
from .commons import MAX_GPIO_EVT_PER_BUFFER
from .monitor_abc import Monitor
from .monitor_kernel import KernelMonitor
from .monitor_ptp import PTPMonitor
from .monitor_sheep import SheepMonitor
from .monitor_sysutil import SysUtilMonitor
from .monitor_uart import UARTMonitor
from .shared_memory import DataBuffer


class Writer(CoreWriter):
    """Stores data coming from PRU's in HDF5 format

    Args:
        file_path (Path): Name of the HDF5 file that data will be written to
        cal_data (CalibrationEmulator or CalibrationHarvester): Data is written as raw ADC
            values. We need calibration data in order to convert to physical
            units later.
        mode (str): Indicates if this is data from harvester or emulator
        force_overwrite (bool): Overwrite existing file with the same name
        samples_per_buffer (int): Number of samples contained in a single
            shepherd buffer
        samplerate_sps (int): Duration of a single shepherd buffer in
            nanoseconds
    """

    mode_dtype_dict = {
        "harvester": ["ivsample", "ivcurve", "isc_voc"],
        "emulator": ["ivsample"],
    }

    def __init__(
        self,
        file_path: Path,
        mode: Optional[str] = None,
        datatype: Optional[str] = None,
        window_samples: Optional[int] = None,
        cal_data: Union[CalSeries, CalEmu, CalHrv, None] = None,
        compression: Compression = Compression.default,
        modify_existing: bool = False,
        force_overwrite: bool = False,
        verbose: Optional[bool] = True,
        samples_per_buffer: int = 10_000,
        samplerate_sps: int = 100_000,
    ):
        # hopefully overwrite defaults from Reader
        self.samples_per_buffer: int = samples_per_buffer  # TODO: test
        self.samplerate_sps: int = samplerate_sps

        if compression is None:  # TODO: temp fix for core <= 23.06.03
            compression = Compression.null

        # TODO: derive verbose-state
        super().__init__(
            file_path,
            mode,
            datatype,
            window_samples,
            cal_data,
            compression,
            modify_existing,
            force_overwrite,
            verbose,
        )

        self.buffer_timeseries = self.sample_interval_ns * np.arange(
            self.samples_per_buffer,
        ).astype("u8")
        # TODO: keep this optimization

        self.grp_data: h5py.Group = self.h5file["data"]

        # Optimization: allowing larger more efficient resizes
        #               (before .resize() was called per element)
        # h5py v3.4 is taking 20% longer for .write_buffer() than v2.1
        # this change speeds up v3.4 by 30% (even system load drops from 90% to 70%), v2.1 by 16%
        self.data_pos = 0
        self.data_inc = int(100 * self.samplerate_sps)
        self.gpio_pos = 0
        self.gpio_inc = MAX_GPIO_EVT_PER_BUFFER
        # NOTE for possible optimization: align resize with chunk-size
        #      -> rely on autochunking -> inc = h5ds.chunks

        # prepare Monitors
        self.sysutil_log_enabled: bool = True
        self.monitors: List[Monitor] = []

    def __enter__(self):
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
        # Create group for gpio data
        self.gpio_grp = self.h5file.create_group("gpio")
        self.gpio_grp.create_dataset(
            "time",
            (self.gpio_inc,),
            dtype="u8",
            maxshape=(None,),
            chunks=True,
            compression=self._compression,
        )
        self.gpio_grp["time"].attrs["unit"] = "s"
        self.gpio_grp["time"].attrs[
            "description"
        ] = "system time [s] = value * gain + (offset)"
        self.gpio_grp["time"].attrs["gain"] = 1e-9
        self.gpio_grp["time"].attrs["offset"] = 0

        self.gpio_grp.create_dataset(
            "value",
            (self.gpio_inc,),
            dtype="u2",
            maxshape=(None,),
            chunks=True,
            compression=self._compression,
        )
        self.gpio_grp["value"].attrs["unit"] = "n"
        self.gpio_grp["value"].attrs["description"] = yaml.safe_dump(
            GPIO_LOG_BIT_POSITIONS,
            default_flow_style=False,
            sort_keys=False,
        )

        # targets for logging-monitor
        self.sheep_grp = self.h5file.create_group("sheep")
        self.uart_grp = self.h5file.create_group("uart")
        self.sysutil_grp = self.h5file.create_group("sysutil")
        self.kernel_grp = self.h5file.create_group("kernel")
        self.ptp_grp = self.h5file.create_group("ptp")

        return self

    def __exit__(self, *exc):  # type: ignore
        # trim over-provisioned parts
        self.grp_data["time"].resize((self.data_pos,))
        self.grp_data["voltage"].resize((self.data_pos,))
        self.grp_data["current"].resize((self.data_pos,))

        self.gpio_grp["time"].resize((self.gpio_pos,))
        self.gpio_grp["value"].resize((self.gpio_pos,))
        gpio_events = self.gpio_grp["time"].shape[0]

        for monitor in self.monitors:
            monitor.__exit__()

        super().__exit__()
        self._logger.info(
            "  -> Sheep captured %d gpio-events",
            gpio_events,
        )

    def write_buffer(self, buffer: DataBuffer) -> None:
        """Writes data from buffer to file.

        Args:
            buffer (DataBuffer): Buffer containing IV data
        """

        # First, we have to resize the corresponding datasets
        data_end_pos = self.data_pos + len(buffer)
        data_length = self.grp_data["time"].shape[0]
        if data_end_pos >= data_length:
            data_length += self.data_inc
            self.grp_data["time"].resize((data_length,))
            self.grp_data["voltage"].resize((data_length,))
            self.grp_data["current"].resize((data_length,))

        self.grp_data["voltage"][self.data_pos : data_end_pos] = buffer.voltage
        self.grp_data["current"][self.data_pos : data_end_pos] = buffer.current
        self.grp_data["time"][self.data_pos : data_end_pos] = (
            self.buffer_timeseries + buffer.timestamp_ns
        )
        self.data_pos = data_end_pos

        len_edges = len(buffer.gpio_edges)
        if len_edges > 0:
            gpio_new_pos = self.gpio_pos + len_edges
            data_length = self.gpio_grp["time"].shape[0]
            if gpio_new_pos >= data_length:
                data_length += max(self.gpio_inc, gpio_new_pos - data_length)
                self.gpio_grp["time"].resize((data_length,))
                self.gpio_grp["value"].resize((data_length,))
            self.gpio_grp["time"][
                self.gpio_pos : gpio_new_pos
            ] = buffer.gpio_edges.timestamps_ns
            self.gpio_grp["value"][
                self.gpio_pos : gpio_new_pos
            ] = buffer.gpio_edges.values
            self.gpio_pos = gpio_new_pos

        if (buffer.util_mean > 95) or (buffer.util_max > 100):
            self._logger.warning(
                "WARNING: real-time critical, pru0 Loop-Util: mean = %d %, max = %d %",
                buffer.util_mean,
                buffer.util_max,
            )
            # TODO: store pru-util? probably yes

    def start_monitors(
        self,
        sys: Optional[SystemLogging] = None,
        gpio: Optional[GpioTracing] = None,
    ) -> None:
        if sys is not None and sys.dmesg:
            self.monitors.append(KernelMonitor(self.kernel_grp, self._compression))
        if sys is not None and sys.ptp:
            self.monitors.append(PTPMonitor(self.ptp_grp, self._compression))
        if self.sysutil_log_enabled:
            self.monitors.append(SysUtilMonitor(self.sysutil_grp, self._compression))
        if gpio is not None and gpio.uart_decode:
            self.monitors.append(
                UARTMonitor(
                    self.uart_grp,
                    self._compression,
                    baudrate=gpio.uart_baudrate,
                ),
            )
        self.monitors.append(SheepMonitor(self.uart_grp, self._compression))
