"""
shepherd.datalog
~~~~~
Provides classes for storing and retrieving sampled IV data to/from
HDF5 files.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import subprocess  # noqa: S404
import threading
import time
from collections import namedtuple
from pathlib import Path
from typing import Optional
from typing import Union

import h5py
import numpy as np
import psutil as psutil
import serial
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
from .logger import get_message_queue
from .shared_memory import DataBuffer


# An entry for an exception to be stored together with the data consists of a
# timestamp, a custom message and an arbitrary integer value
ExceptionRecord = namedtuple("ExceptionRecord", ["timestamp", "message", "value"])

monitors_end = threading.Event()


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

    uart_path = "/dev/ttyS1"

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

        self._write_uart = Path(self.uart_path).exists()

        self.grp_data: h5py.Group = self.h5file["data"]

        # initial sysutil-reading and delta-history
        self.sys_log_enabled: bool = True
        self.sys_log_interval_ns: int = 1 * (10**9)  # step-size is 1 s
        self.sys_log_next_ns: int = 0
        if psutil.disk_io_counters() is None:
            # fake or virtual hardware detected
            self.sys_log_enabled = False
        else:
            self.sysutil_io_last = np.array(psutil.disk_io_counters()[0:4])  # type: ignore
            self.sysutil_nw_last = np.array(psutil.net_io_counters()[0:2])

        self.dmesg_mon_t: Optional[threading.Thread] = None
        self.ptp4l_mon_t: Optional[threading.Thread] = None
        self.uart_mon_t: Optional[threading.Thread] = None
        self.logmsg_mon_t: Optional[threading.Thread] = None

        # Optimization: allowing larger more efficient resizes
        #               (before .resize() was called per element)
        # h5py v3.4 is taking 20% longer for .write_buffer() than v2.1
        # this change speeds up v3.4 by 30% (even system load drops from 90% to 70%), v2.1 by 16%
        inc_duration = int(100)
        inc_length = int(inc_duration * self.samplerate_sps)
        self.data_pos = 0
        self.data_inc = inc_length
        self.gpio_pos = 0
        self.gpio_inc = MAX_GPIO_EVT_PER_BUFFER
        self.sysutil_pos = 0
        self.sysutil_inc = inc_duration * 1
        self.uart_pos = 0
        self.uart_inc = 100
        self.dmesg_pos = 0
        self.dmesg_inc = 100
        self.xcpt_pos = 0
        self.xcpt_inc = 100
        self.logmsg_pos = 0
        self.logmsg_inc = 100
        self.timesync_pos = 0
        self.timesync_inc = inc_duration * 1
        # TODO: these params should be more local in monitors
        # NOTE for possible optimization: align resize with chunk-size
        #      -> rely on autochunking -> inc = h5ds.chunks

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
        self.add_dataset_time(self.gpio_grp, self.gpio_inc)
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

        # Create group for exception logs, entry consists of a timestamp, a message and a value
        self.xcpt_grp = self.h5file.create_group("exceptions")
        self.add_dataset_time(self.xcpt_grp, self.xcpt_inc)
        self.xcpt_grp.create_dataset(
            "message",
            (self.xcpt_inc,),
            dtype=h5py.special_dtype(
                vlen=str,
            ),  # TODO: switch to string_dtype() (h5py >v3.0)
            maxshape=(None,),
            chunks=True,
        )
        self.xcpt_grp.create_dataset(
            "value",
            (self.xcpt_inc,),
            dtype="u4",
            maxshape=(None,),
            chunks=True,
        )
        self.xcpt_grp["value"].attrs["unit"] = "n"

        # Shepherd-logging-handler
        self.logmsg_grp = self.h5file.create_group("shepherd-log")
        self.add_dataset_time(self.logmsg_grp, self.logmsg_inc)
        self.logmsg_grp.create_dataset(
            "message",
            (self.logmsg_inc,),
            dtype=h5py.special_dtype(
                vlen=str,
            ),  # TODO: switch to string_dtype() (h5py >v3.0)
            maxshape=(None,),
            chunks=True,
        )

        # UART-Logger
        if self._write_uart:
            self.uart_grp = self.h5file.create_group("uart")
            self.add_dataset_time(self.uart_grp, self.uart_inc)
            # Every log entry consists of a timestamp and a message
            self.uart_grp.create_dataset(
                "message",
                (self.uart_inc,),
                dtype=h5py.special_dtype(vlen=bytes),
                maxshape=(None,),
                chunks=True,
            )
            self.uart_grp["message"].attrs["description"] = "raw ascii-bytes"

        # Create sys-Logger
        self.sysutil_grp = self.h5file.create_group("sysutil")
        self.add_dataset_time(self.sysutil_grp, self.sysutil_inc, (self.sysutil_inc,))
        self.sysutil_grp["time"].attrs["unit"] = "ns"
        self.sysutil_grp["time"].attrs["description"] = "system time [ns]"
        self.sysutil_grp.create_dataset(
            "cpu",
            (self.sysutil_inc,),
            dtype="u1",
            maxshape=(None,),
            chunks=(self.sysutil_inc,),
        )
        self.sysutil_grp["cpu"].attrs["unit"] = "%"
        self.sysutil_grp["cpu"].attrs["description"] = "cpu_util [%]"
        self.sysutil_grp.create_dataset(
            "ram",
            (self.sysutil_inc, 2),
            dtype="u1",
            maxshape=(None, 2),
            chunks=(self.sysutil_inc, 2),
        )
        self.sysutil_grp["ram"].attrs["unit"] = "%"
        self.sysutil_grp["ram"].attrs["description"] = "ram_available [%], ram_used [%]"
        self.sysutil_grp.create_dataset(
            "io",
            (self.sysutil_inc, 4),
            dtype="u8",
            maxshape=(None, 4),
            chunks=(self.sysutil_inc, 4),
        )
        self.sysutil_grp["io"].attrs["unit"] = "n"
        self.sysutil_grp["io"].attrs[
            "description"
        ] = "io_read [n], io_write [n], io_read [byte], io_write [byte]"
        self.sysutil_grp.create_dataset(
            "net",
            (self.sysutil_inc, 2),
            dtype="u8",
            maxshape=(None, 2),
            chunks=(self.sysutil_inc, 2),
        )
        self.sysutil_grp["net"].attrs["unit"] = "n"
        self.sysutil_grp["net"].attrs["description"] = "nw_sent [byte], nw_recv [byte]"
        self.sys_log_next_ns = int(time.time() * 1e9)
        self.log_sys_stats()

        # Create dmesg-Logger -> consists of a timestamp and a message
        self.dmesg_grp = self.h5file.create_group("dmesg")
        self.add_dataset_time(self.dmesg_grp, self.dmesg_inc)
        self.dmesg_grp.create_dataset(
            "message",
            (self.dmesg_inc,),
            dtype=h5py.special_dtype(vlen=str),
            maxshape=(None,),
            chunks=True,
        )

        # Create timesync-Logger
        self.timesync_grp = self.h5file.create_group("timesync")
        self.add_dataset_time(self.timesync_grp, self.timesync_inc)
        self.timesync_grp.create_dataset(
            "values",
            (self.timesync_inc, 3),
            dtype="i8",
            maxshape=(None, 3),
            chunks=True,
        )
        self.timesync_grp["values"].attrs["unit"] = "ns, Hz, ns"
        self.timesync_grp["values"].attrs[
            "description"
        ] = "main offset [ns], s2 freq [Hz], path delay [ns]"

        return self

    def __exit__(self, *exc):  # type: ignore
        global monitors_end
        monitors_end.set()
        time.sleep(0.1)

        # meantime: trim over-provisioned parts
        self.grp_data["time"].resize((self.data_pos,))
        self.grp_data["voltage"].resize((self.data_pos,))
        self.grp_data["current"].resize((self.data_pos,))

        self.gpio_grp["time"].resize((self.gpio_pos,))
        self.gpio_grp["value"].resize((self.gpio_pos,))

        self.sysutil_grp["time"].resize((self.sysutil_pos,))
        self.sysutil_grp["cpu"].resize((self.sysutil_pos,))
        self.sysutil_grp["ram"].resize((self.sysutil_pos, 2))
        self.sysutil_grp["io"].resize((self.sysutil_pos, 4))
        self.sysutil_grp["net"].resize((self.sysutil_pos, 2))
        if self._write_uart:
            self.uart_grp["time"].resize((self.uart_pos,))
            self.uart_grp["message"].resize((self.uart_pos,))
        self.dmesg_grp["time"].resize((self.dmesg_pos,))
        self.dmesg_grp["message"].resize((self.dmesg_pos,))
        self.xcpt_grp["time"].resize((self.xcpt_pos,))
        self.xcpt_grp["message"].resize((self.xcpt_pos,))
        self.xcpt_grp["value"].resize((self.xcpt_pos,))
        self.logmsg_grp["time"].resize((self.logmsg_pos,))
        self.logmsg_grp["message"].resize((self.logmsg_pos,))
        self.timesync_grp["time"].resize((self.timesync_pos,))
        self.timesync_grp["values"].resize((self.timesync_pos, 3))

        if self.dmesg_mon_t is not None:
            self._logger.info(
                "   DmesgLog has %d entries",
                self.dmesg_grp["time"].shape[0],
            )
            self.dmesg_mon_t = None
        if self.ptp4l_mon_t is not None:
            self._logger.info(
                "   PTPLog has %d entries",
                self.timesync_grp["time"].shape[0],
            )
            self.ptp4l_mon_t = None
        if self.uart_mon_t is not None:
            if self._write_uart:
                self._logger.info(
                    "   UARTLog has %d entries",
                    self.uart_grp["time"].shape[0],
                )
            self.uart_mon_t = None
        if self.logmsg_mon_t is not None:
            self._logger.info(
                "   ShpLog has %d entries",
                self.logmsg_grp["time"].shape[0],
            )
            self.logmsg_mon_t = None

        gpio_events = self.gpio_grp["time"].shape[0]
        xcpt_events = self.xcpt_grp["time"].shape[0]
        super().__exit__()
        self._logger.info(
            "  -> Sheep captured %d gpio-events, %d xcpt-events",
            gpio_events,
            xcpt_events,
        )

    def add_dataset_time(
        self,
        grp: h5py.Group,
        length: int,
        chunks: Union[bool, tuple] = True,
    ) -> None:
        grp.create_dataset(
            "time",
            (length,),
            dtype="u8",
            maxshape=(None,),
            chunks=chunks,
            compression=self._compression,
        )
        grp["time"].attrs["unit"] = "s"
        grp["time"].attrs["description"] = "system time [s] = value * gain + (offset)"
        grp["time"].attrs["gain"] = 1e-9
        grp["time"].attrs["offset"] = 0

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
            warn_msg = (
                f"Pru0 Loop-Util:  "
                f"mean = {buffer.util_mean} %, "
                f"max = {buffer.util_max} % "
                f"-> WARNING: broken real-time-condition"
            )
            # TODO: store pru-util? probably yes
            expt = ExceptionRecord(int(time.time() * 1e9), warn_msg, 42)
            self.write_exception(expt)

        self.log_sys_stats()

    def write_exception(self, exception: ExceptionRecord) -> None:
        """Writes an exception to the hdf5 file.
            TODO: use this fn to log exceptions, redirect logger.error() ?
            TODO: there is a concrete ShepherdIOException(Exception)
        Args:
            exception (ExceptionRecord): The exception to be logged
        """
        if self.xcpt_pos >= self.xcpt_grp["time"].shape[0]:
            data_length = self.xcpt_grp["time"].shape[0] + self.xcpt_inc
            self.xcpt_grp["time"].resize((data_length,))
            self.xcpt_grp["value"].resize((data_length,))
            self.xcpt_grp["message"].resize((data_length,))
        self.xcpt_grp["time"][self.xcpt_pos] = exception.timestamp
        self.xcpt_grp["value"][self.xcpt_pos] = exception.value
        self.xcpt_grp["message"][self.xcpt_pos] = exception.message
        self.xcpt_pos += 1

    def log_sys_stats(self) -> None:
        """captures state of system in a fixed interval
            https://psutil.readthedocs.io/en/latest/#cpu
        :return: none
        """
        if not self.sys_log_enabled:
            return
        ts_now_ns = int(time.time() * 1e9)
        if ts_now_ns >= self.sys_log_next_ns:
            data_length = self.sysutil_grp["time"].shape[0]
            if self.sysutil_pos >= data_length:
                data_length += self.sysutil_inc
                self.sysutil_grp["time"].resize((data_length,))
                self.sysutil_grp["cpu"].resize((data_length,))
                self.sysutil_grp["ram"].resize((data_length, 2))
                self.sysutil_grp["io"].resize((data_length, 4))
                self.sysutil_grp["net"].resize((data_length, 2))
            self.sys_log_next_ns += self.sys_log_interval_ns
            if self.sys_log_next_ns < ts_now_ns:
                self.sys_log_next_ns = int(time.time() * 1e9)
            self.sysutil_grp["time"][self.sysutil_pos] = ts_now_ns
            self.sysutil_grp["cpu"][self.sysutil_pos] = int(
                round(psutil.cpu_percent(0)),
            )
            mem_stat = psutil.virtual_memory()[0:3]
            self.sysutil_grp["ram"][self.sysutil_pos, 0:2] = [
                int(100 * mem_stat[1] / mem_stat[0]),
                int(mem_stat[2]),
            ]
            sysutil_io_now = np.array(psutil.disk_io_counters()[0:4])  # type: ignore
            self.sysutil_grp["io"][self.sysutil_pos, :] = (
                sysutil_io_now - self.sysutil_io_last
            )
            self.sysutil_io_last = sysutil_io_now
            sysutil_nw_now = np.array(psutil.net_io_counters()[0:2])
            self.sysutil_grp["net"][self.sysutil_pos, :] = (
                sysutil_nw_now - self.sysutil_nw_last
            )
            self.sysutil_nw_last = sysutil_nw_now
            self.sysutil_pos += 1
            # TODO: add temp, not working:
            #  https://psutil.readthedocs.io/en/latest/#psutil.sensors_temperatures

    def start_monitors(
        self,
        sys: Optional[SystemLogging] = None,
        gpio: Optional[GpioTracing] = None,
    ) -> None:
        if sys is not None and sys.dmesg:
            self.dmesg_mon_t = threading.Thread(target=self.monitor_dmesg, daemon=True)
            self.dmesg_mon_t.start()
        if sys is not None and sys.ptp:
            self.ptp4l_mon_t = threading.Thread(target=self.monitor_ptp4l, daemon=True)
            self.ptp4l_mon_t.start()
        if gpio is not None and gpio.uart_decode:
            self.uart_mon_t = threading.Thread(
                target=self.monitor_uart,
                args=(gpio.uart_baudrate,),
                daemon=True,
            )
            self.uart_mon_t.start()
        self.logmsg_mon_t = threading.Thread(target=self.monitor_logmsg, daemon=True)
        self.logmsg_mon_t.start()

    def monitor_uart(
        self,
        baudrate: Optional[int],
        poll_intervall: float = 0.01,
    ) -> None:
        # TODO: TEST - Not final, goal: raw bytes in hdf5
        # - uart is bytes-type -> storing in hdf5 is hard,
        #   tried 'S' and opaque-type -> failed with errors
        # - converting is producing ValueError on certain chars,
        #   errors="backslashreplace" does not help
        # TODO: eval https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.to_bytes
        if (not self._write_uart) or (not isinstance(baudrate, int)) or (baudrate == 0):
            return
        global monitors_end
        self._logger.debug(
            "Will start UART-Monitor for target on '%s' @ %d baud",
            self.uart_path,
            baudrate,
        )
        tevent = threading.Event()
        try:
            # open serial as non-exclusive
            with serial.Serial(self.uart_path, baudrate, timeout=0) as uart:
                while True:
                    if monitors_end.is_set():
                        break
                    if uart.in_waiting > 0:
                        # hdf5 can embed raw bytes, but can't handle nullbytes
                        output = uart.read(uart.in_waiting).replace(b"\x00", b"")
                        # TODO: test, this had a .decode("ascii", errors="replace") in between
                        if len(output) > 0:
                            data_length = self.uart_grp["time"].shape[0]
                            if self.uart_pos >= data_length:
                                data_length += self.uart_inc
                                self.uart_grp["time"].resize((data_length,))
                                self.uart_grp["message"].resize((data_length,))
                            self.uart_grp["time"][self.uart_pos] = int(
                                time.time() * 1e9,
                            )
                            self.uart_grp["message"][
                                self.uart_pos
                            ] = output  # np.void(uart_rx)
                            self.uart_pos += 1
                    tevent.wait(poll_intervall)  # rate limiter
        except ValueError as e:
            self._logger.error(  # noqa: G200
                "[UartMonitor] PySerial ValueError '%s' - "
                "couldn't configure serial-port '%s' "
                "with baudrate=%d -> will not be logged",
                e,
                self.uart_path,
                baudrate,
            )
        except serial.SerialException as e:
            self._logger.error(  # noqa: G200
                "[UartMonitor] pySerial SerialException '%s - "
                "Couldn't open Serial-Port '%s' to target -> will not be logged",
                e,
                self.uart_path,
            )
        self._logger.debug("[UartMonitor] ended itself")

    def monitor_dmesg(self, backlog: int = 40, poll_intervall: float = 0.2):
        # var1: ['dmesg', '--follow'] -> not enough control
        global monitors_end
        cmd_dmesg = [
            "sudo",
            "journalctl",
            "--dmesg",
            "--follow",
            f"--lines={backlog}",
            "--output=short-precise",
        ]
        proc_dmesg = subprocess.Popen(  # noqa: S603
            cmd_dmesg,
            stdout=subprocess.PIPE,
            universal_newlines=True,
        )
        if (not hasattr(proc_dmesg, "stdout")) or (proc_dmesg.stdout is None):
            self._logger.error("[DmesgMonitor] Setup failed -> will not be logged")
            return
        tevent = threading.Event()
        for line in iter(proc_dmesg.stdout.readline, ""):  # type: ignore
            if monitors_end.is_set():
                break
            line = str(line).strip()[:128]
            try:
                data_length = self.dmesg_grp["time"].shape[0]
                if self.dmesg_pos >= data_length:
                    data_length += self.dmesg_inc
                    self.dmesg_grp["time"].resize((data_length,))
                    self.dmesg_grp["message"].resize((data_length,))
                self.dmesg_grp["time"][self.dmesg_pos] = int(time.time() * 1e9)
                self.dmesg_grp["message"][self.dmesg_pos] = line
                self.dmesg_pos += 1
            except OSError:
                self._logger.error(
                    "[DmesgMonitor] Caught a Write Error for Line: [%s] %s",
                    type(line),
                    line,
                )
            tevent.wait(poll_intervall)  # rate limiter
        self._logger.debug("[DmesgMonitor] ended itself")

    def monitor_ptp4l(self, poll_intervall: float = 0.25):
        # example:
        # sheep1 ptp4l[378]: [821.629] main offset -4426 s2 freq +285889 path delay 12484
        global monitors_end
        cmd_ptp4l = [
            "sudo",
            "journalctl",
            "--unit=ptp4l@eth0",
            "--follow",
            "--lines=1",
            "--output=short-precise",
        ]  # for client
        proc_ptp4l = subprocess.Popen(  # noqa: S603
            cmd_ptp4l,
            stdout=subprocess.PIPE,
            universal_newlines=True,
        )
        if (not hasattr(proc_ptp4l, "stdout")) or (proc_ptp4l.stdout is None):
            self._logger.error("[PTP4lMonitor] Setup failed -> will not be logged")
            return
        tevent = threading.Event()
        for line in iter(proc_ptp4l.stdout.readline, ""):
            if monitors_end.is_set():
                break
            try:
                words = str(line).split()
                i_start = words.index("offset")
                values = [
                    int(words[i_start + 1]),
                    int(words[i_start + 4]),
                    int(words[i_start + 7]),
                ]
            except ValueError:
                continue
            try:
                data_length = self.timesync_grp["time"].shape[0]
                if self.timesync_pos >= data_length:
                    data_length += self.timesync_inc
                    self.timesync_grp["time"].resize((data_length,))
                    self.timesync_grp["values"].resize((data_length, 3))
                self.timesync_grp["time"][self.timesync_pos] = int(time.time() * 1e9)
                self.timesync_grp["values"][self.timesync_pos, :] = values[0:3]
                self.timesync_pos += 1
            except (OSError, KeyError):
                self._logger.error(
                    "[PTP4lMonitor] Caught a Write Error for Line: [%s] %s",
                    type(line),
                    line,
                )
            tevent.wait(poll_intervall)  # rate limiter
        self._logger.debug("[PTP4lMonitor] ended itself")
        # TODO: also add phc2sys

    def monitor_logmsg(self, poll_intervall: float = 1) -> None:
        global monitors_end
        if not hasattr(self, "logmsg_grp") or "time" not in self.logmsg_grp.keys():
            return
        queue = get_message_queue()
        tevent = threading.Event()

        while not monitors_end.is_set():
            while queue.qsize() > 0:
                rec = queue.get()
                data_length = self.logmsg_grp["time"].shape[0]
                if self.logmsg_pos >= self.logmsg_grp["time"].shape[0]:
                    data_length += self.logmsg_inc
                    self.logmsg_grp["time"].resize((data_length,))
                    self.logmsg_grp["message"].resize((data_length,))
                self.logmsg_grp["time"][self.logmsg_pos] = int(rec.created * 1e9)
                self.logmsg_grp["message"][self.logmsg_pos] = rec.message
                self.logmsg_pos += 1
            tevent.wait(poll_intervall)  # rate limiter
        self._logger.debug("[LogMsgMonitor] ended itself")
