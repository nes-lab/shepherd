# -*- coding: utf-8 -*-

"""
shepherd.datalog
~~~~~
Provides classes for storing and retrieving sampled IV data to/from
HDF5 files.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""

import logging
import subprocess  # noqa S404
import threading
import time
from typing import NoReturn, Union

import numpy as np
from pathlib import Path
import h5py
from itertools import product
from collections import namedtuple
import psutil as psutil
import serial
import yaml

from .calibration import CalibrationData
from .calibration import cal_channel_hrv_dict
from .calibration import cal_channel_emu_dict
from .calibration import cal_parameter_list

from .shepherd_io import DataBuffer
from .commons import GPIO_LOG_BIT_POSITIONS, MAX_GPIO_EVT_PER_BUFFER

logger = logging.getLogger("shp.datalog.writer")

"""
An entry for an exception to be stored together with the data consists of a
timestamp, a custom message and an arbitrary integer value
"""
ExceptionRecord = namedtuple("ExceptionRecord", ["timestamp", "message", "value"])

monitors_end = threading.Event()


def unique_path(base_path: Union[str, Path], suffix: str):
    counter = 0
    while True:
        path = base_path.with_suffix(f".{ counter }{ suffix }")
        if not path.exists():
            return path
        counter += 1


class LogWriter:
    """Stores data coming from PRU's in HDF5 format
       TODO: replace with shepherd_data.Writer to fully support new datatype

    Args:
        file_path (Path): Name of the HDF5 file that data will be written to
        calibration_data (CalibrationData): Data is written as raw ADC
            values. We need calibration data in order to convert to physical
            units later.
        mode (str): Indicates if this is data from harvester or emulator
        force_overwrite (bool): Overwrite existing file with the same name
        samples_per_buffer (int): Number of samples contained in a single
            shepherd buffer
        samplerate_sps (int): Duration of a single shepherd buffer in
            nanoseconds

    """

    # choose lossless compression filter
    # - lzf:    low to moderate compression, VERY fast, no options
    #           -> 20 % cpu overhead for half the filesize
    # - gzip:   good compression, moderate speed, select level from 1-9,
    #           default is 4 -> lower levels seem fine
    #           --> _algo=number instead of "gzip" is read as compression level for gzip
    #  -> comparison / benchmarks https://www.h5py.org/lzf/
    # NOTE: for quick and easy performance improvements:
    #       remove compression for monitor-datasets, or even group_value
    compression_algo = None
    sys_log_enabled = True
    sys_log_intervall_ns = 1 * (10**9)  # step-size is 1 s
    sys_log_next_ns = 0
    uart_path = "/dev/ttyO1"
    dmesg_mon_t = None
    ptp4l_mon_t = None
    uart_mon_t = None

    mode_default: str = "harvester"
    datatype_default: str = "ivsample"
    mode_dtype_dict = {
        "harvester": ["ivsample", "ivcurve", "isc_voc"],
        "emulator": ["ivsample"],
    }

    def __init__(
        self,
        file_path: Path,
        calibration_data: CalibrationData,
        mode: str = None,
        datatype: str = None,
        force_overwrite: bool = False,
        samples_per_buffer: int = 10_000,
        samplerate_sps: int = 100_000,
        skip_voltage: bool = False,
        skip_current: bool = False,
        skip_gpio: bool = False,
        output_compression: Union[None, str, int] = None,
    ):
        file_path = Path(file_path)
        if force_overwrite or not file_path.exists():
            self.store_path = file_path
            logger.info(f"Storing data to   '{self.store_path}'")
        else:
            base_dir = file_path.resolve().parents[0]
            self.store_path = unique_path(base_dir / file_path.stem, file_path.suffix)
            logger.warning(
                f"File {file_path} already exists.. "
                f"storing under {self.store_path} instead"
            )
        # Refer to shepherd/calibration.py for the format of calibration data
        if not isinstance(mode, (str, type(None))):
            raise TypeError(f"can not handle type '{type(mode)}' for mode")
        if isinstance(mode, str) and mode not in self.mode_dtype_dict:
            raise ValueError(f"can not handle mode '{mode}'")

        if not isinstance(datatype, (str, type(None))):
            raise TypeError(f"can not handle type '{type(datatype)}' for datatype")
        if (
            isinstance(datatype, str)
            and datatype
            not in self.mode_dtype_dict[self.mode_default if (mode is None) else mode]
        ):
            raise ValueError(f"can not handle datatype '{datatype}'")

        self._mode = self.mode_default if (mode is None) else mode
        self._datatype = self.datatype_default if (datatype is None) else datatype

        self.calibration_data = calibration_data
        self.chunk_shape = (samples_per_buffer,)
        self.samplerate_sps = int(samplerate_sps)
        self.sample_interval_ns = int(10**9 // samplerate_sps)
        self.buffer_timeseries = self.sample_interval_ns * np.arange(
            samples_per_buffer
        ).astype("u8")
        self._write_voltage = not skip_voltage
        self._write_current = not skip_current
        self._write_gpio = (not skip_gpio) and ("emulat" in self._mode)
        self._write_uart = Path(self.uart_path).exists()

        if output_compression in [None, "lzf", 1]:  # order of recommendation
            self.compression_algo = output_compression

        logger.debug(
            f"Set log-writing for voltage:     {'enabled' if self._write_voltage else 'disabled'}"
        )
        logger.debug(
            f"Set log-writing for current:     {'enabled' if self._write_current else 'disabled'}"
        )
        logger.debug(
            f"Set log-writing for gpio:        {'enabled' if self._write_gpio else 'disabled'}"
        )

        # initial sysutil-reading and delta-history
        if psutil.disk_io_counters() is None:
            # fake or virtual hardware detected
            self.sys_log_enabled = False
        else:
            self.sysutil_io_last = np.array(psutil.disk_io_counters()[0:4])
            self.sysutil_nw_last = np.array(psutil.net_io_counters()[0:2])
        # Optimization: allowing larger more efficient resizes
        #               (before .resize() was called per element)
        # h5py v3.4 is taking 20% longer for .write_buffer() than v2.1
        # this change speeds up v3.4 by 30% (even system load drops from 90% to 70%), v2.1 by 16%
        inc_duration = int(100)
        inc_length = int(inc_duration * samplerate_sps)
        self.data_pos = 0
        self.data_inc = inc_length
        self.gpio_pos = 0
        self.gpio_inc = MAX_GPIO_EVT_PER_BUFFER
        self.sysutil_pos = 0
        self.sysutil_inc = inc_duration
        self.uart_pos = 0
        self.uart_inc = 100
        self.dmesg_pos = 0
        self.dmesg_inc = 100
        self.xcpt_pos = 0
        self.xcpt_inc = 100
        self.timesync_pos = 0
        self.timesync_inc = inc_duration
        # NOTE for possible optimization: align resize with chunk-size
        #      -> rely on autochunking -> inc = h5ds.chunks

    def __enter__(self):
        """Initializes the structure of the HDF5 file

        HDF5 is hierarchically structured and before writing data, we have to
        setup this structure, i.e. creating the right groups with corresponding
        data types. We will store 3 types of data in a LogWriter database: The
        actual IV samples recorded either from the harvester (during recording)
        or the target (during emulation). Any log messages, that can be used to
        store relevant events or tag some parts of the recorded data. And lastly
        the state of the GPIO pins.

        """
        self._h5file = h5py.File(self.store_path, "w")

        # show key parameters for h5-performance
        settings = list(self._h5file.id.get_access_plist().get_cache())
        logger.debug(f"H5Py Cache_setting={settings} (_mdc, _nslots, _nbytes, _w0)")

        # Store voltage and current samples in the data group, both are stored as 4 Byte uint
        self.data_grp = self._h5file.create_group("data")
        self.data_grp.attrs["window_samples"] = 0  # will be adjusted by .embed_config()

        self.add_dataset_time(self.data_grp, self.data_inc, self.chunk_shape)
        self.data_grp.create_dataset(
            "current",
            (self.data_inc,),
            dtype="u4",
            maxshape=(None,),
            chunks=self.chunk_shape,
            compression=self.compression_algo,
        )
        self.data_grp["current"].attrs["unit"] = "A"
        self.data_grp["current"].attrs[
            "description"
        ] = "current [A] = value * gain + offset"
        self.data_grp.create_dataset(
            "voltage",
            (self.data_inc,),
            dtype="u4",
            maxshape=(None,),
            chunks=self.chunk_shape,
            compression=self.compression_algo,
        )
        self.data_grp["voltage"].attrs["unit"] = "V"
        self.data_grp["voltage"].attrs[
            "description"
        ] = "voltage [V] = value * gain + offset"

        for channel, parameter in product(["current", "voltage"], cal_parameter_list):
            # TODO: not the cleanest cal-selection,
            #       maybe just hand the resulting two and
            #       rename them already to "current, voltage" in calling FN
            cal_channel = (
                cal_channel_hrv_dict[channel]
                if (self._mode == "harvester")
                else cal_channel_emu_dict[channel]
            )
            self.data_grp[channel].attrs[parameter] = self.calibration_data[self._mode][
                cal_channel
            ][parameter]

        if self._write_gpio:
            # Create group for gpio data
            self.gpio_grp = self._h5file.create_group("gpio")
            self.add_dataset_time(self.gpio_grp, self.gpio_inc)
            self.gpio_grp.create_dataset(
                "value",
                (self.gpio_inc,),
                dtype="u2",
                maxshape=(None,),
                chunks=True,
                compression=LogWriter.compression_algo,
            )
            self.gpio_grp["value"].attrs["unit"] = "n"
            self.gpio_grp["value"].attrs["description"] = yaml.safe_dump(
                GPIO_LOG_BIT_POSITIONS,
                default_flow_style=False,
                sort_keys=False,
            )

        # Create group for exception logs, entry consists of a timestamp, a message and a value
        self.xcpt_grp = self._h5file.create_group("exceptions")
        self.add_dataset_time(self.xcpt_grp, self.xcpt_inc)
        self.xcpt_grp.create_dataset(
            "message",
            (self.xcpt_inc,),
            dtype=h5py.special_dtype(
                vlen=str
            ),  # TODO: switch to string_dtype() (h5py >v3.0)
            maxshape=(None,),
            chunks=True,
        )
        self.xcpt_grp.create_dataset(
            "value", (self.xcpt_inc,), dtype="u4", maxshape=(None,), chunks=True
        )
        self.xcpt_grp["value"].attrs["unit"] = "n"

        # UART-Logger
        if self._write_uart:
            self.uart_grp = self._h5file.create_group("uart")
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
        self.sysutil_grp = self._h5file.create_group("sysutil")
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
        self.sys_log_next_ns = int(time.time()) * (10**9)
        self.log_sys_stats()

        # Create dmesg-Logger -> consists of a timestamp and a message
        self.dmesg_grp = self._h5file.create_group("dmesg")
        self.add_dataset_time(self.dmesg_grp, self.dmesg_inc)
        self.dmesg_grp.create_dataset(
            "message",
            (self.dmesg_inc,),
            dtype=h5py.special_dtype(vlen=str),
            maxshape=(None,),
            chunks=True,
        )

        # Create timesync-Logger
        self.timesync_grp = self._h5file.create_group("timesync")
        self.add_dataset_time(self.timesync_grp, self.timesync_inc)
        self.timesync_grp.create_dataset(
            "value",
            (self.timesync_inc, 3),
            dtype="i8",
            maxshape=(None, 3),
            chunks=True,
        )
        self.timesync_grp["value"].attrs["unit"] = "ns, Hz, ns"
        self.timesync_grp["value"].attrs[
            "description"
        ] = "master offset [ns], s2 freq [Hz], path delay [ns]"

        # Store the mode in order to allow user to differentiate harvesting vs emulation data
        if isinstance(self._mode, str) and self._mode in self.mode_dtype_dict:
            self._h5file.attrs["mode"] = self._mode

        if (
            isinstance(self._datatype, str)
            and self._datatype in self.mode_dtype_dict[self.get_mode()]
        ):
            self._h5file["data"].attrs["datatype"] = self._datatype

        return self

    def get_mode(self) -> str:
        if "mode" in self._h5file.attrs:
            return self._h5file.attrs["mode"]
        return ""

    def embed_config(self, data: dict) -> NoReturn:
        """
        Important Step to get a self-describing Output-File
        Note: the window_samples-size is important for reconstruction

        :param data: from virtual harvester or converter / source
        :return: None
        """
        self.data_grp.attrs["config"] = yaml.dump(
            data, default_flow_style=False, sort_keys=False
        )
        if "window_samples" in data:
            self.data_grp.attrs["window_samples"] = data["window_samples"]

    def __exit__(self, *exc):
        global monitors_end
        monitors_end.set()
        time.sleep(0.1)

        # meantime: trim over-provisioned parts
        self.data_grp["time"].resize(
            (self.data_pos if self._write_current or self._write_voltage else 0,)
        )
        self.data_grp["voltage"].resize((self.data_pos if self._write_voltage else 0,))
        self.data_grp["current"].resize((self.data_pos if self._write_current else 0,))
        if self._write_gpio:
            self.gpio_grp["time"].resize((self.gpio_pos if self._write_gpio else 0,))
            self.gpio_grp["value"].resize((self.gpio_pos if self._write_gpio else 0,))
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
        self.timesync_grp["time"].resize((self.timesync_pos,))
        self.timesync_grp["value"].resize((self.timesync_pos, 3))

        if self.dmesg_mon_t is not None:
            logger.info(
                f"[LogWriter] terminate Dmesg-Monitor, "
                f"({self.dmesg_grp['time'].shape[0]} entries)"
            )
            self.dmesg_mon_t = None
        if self.ptp4l_mon_t is not None:
            logger.info(
                f"[LogWriter] terminate PTP4L-Monitor, "
                f"({self.timesync_grp['time'].shape[0]} entries)"
            )
            self.ptp4l_mon_t = None
        if self.uart_mon_t is not None:
            if self._write_uart:
                logger.info(
                    f"[LogWriter] terminate UART-Monitor,  "
                    f"({self.uart_grp['time'].shape[0]} entries)"
                )
            self.uart_mon_t = None
        runtime = round(self.data_grp["time"].shape[0] / self.samplerate_sps, 1)
        gpevents = self.gpio_grp["time"].shape[0] if self._write_gpio else 0
        logger.info(
            f"[LogWriter] flushing hdf5 file ({runtime} s iv-data, "
            f"{gpevents} gpio-events, {self.xcpt_grp['time'].shape[0]} xcpt-events)"
        )
        self._h5file.flush()
        logger.info("[LogWriter] closing  hdf5 file")
        self._h5file.close()

    def write_buffer(self, buffer: DataBuffer) -> NoReturn:
        """Writes data from buffer to file.

        Args:
            buffer (DataBuffer): Buffer containing IV data
        """

        # First, we have to resize the corresponding datasets
        data_end_pos = self.data_pos + len(buffer)
        data_length = self.data_grp["time"].shape[0]
        if data_end_pos >= data_length:
            data_length += self.data_inc
            self.data_grp["time"].resize((data_length,))
            self.data_grp["voltage"].resize(
                (data_length if self._write_voltage else 0,)
            )
            self.data_grp["current"].resize(
                (data_length if self._write_current else 0,)
            )

        if self._write_voltage:
            self.data_grp["voltage"][self.data_pos : data_end_pos] = buffer.voltage

        if self._write_current:
            self.data_grp["current"][self.data_pos : data_end_pos] = buffer.current

        if self._write_voltage or self._write_current:
            self.data_grp["time"][self.data_pos : data_end_pos] = (
                self.buffer_timeseries + buffer.timestamp_ns
            )
            self.data_pos = data_end_pos

        len_edges = len(buffer.gpio_edges)
        if self._write_gpio and (len_edges > 0):
            gpio_new_pos = self.gpio_pos + len_edges
            data_length = self.gpio_grp["time"].shape[0]
            if gpio_new_pos >= data_length:
                data_length += self.gpio_inc
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
            expt = ExceptionRecord(int(time.time() * 1e9), warn_msg, 42)
            self.write_exception(expt)

        self.log_sys_stats()

    def write_exception(self, exception: ExceptionRecord) -> NoReturn:
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

    def log_sys_stats(self) -> NoReturn:
        """captures state of system in a fixed intervall
            https://psutil.readthedocs.io/en/latest/#cpu
        :return: none
        """
        if not self.sys_log_enabled:
            return
        ts_now_ns = int(time.time() * (10**9))
        if ts_now_ns >= self.sys_log_next_ns:
            data_length = self.sysutil_grp["time"].shape[0]
            if self.sysutil_pos >= data_length:
                data_length += self.sysutil_inc
                self.sysutil_grp["time"].resize((data_length,))
                self.sysutil_grp["cpu"].resize((data_length,))
                self.sysutil_grp["ram"].resize((data_length, 2))
                self.sysutil_grp["io"].resize((data_length, 4))
                self.sysutil_grp["net"].resize((data_length, 2))
            self.sys_log_next_ns += self.sys_log_intervall_ns
            if self.sys_log_next_ns < ts_now_ns:
                self.sys_log_next_ns = int(time.time()) * (10**9)
            self.sysutil_grp["time"][self.sysutil_pos] = ts_now_ns
            self.sysutil_grp["cpu"][self.sysutil_pos] = int(
                round(psutil.cpu_percent(0))
            )
            mem_stat = psutil.virtual_memory()[0:3]
            self.sysutil_grp["ram"][self.sysutil_pos, 0:2] = [
                int(100 * mem_stat[1] / mem_stat[0]),
                int(mem_stat[2]),
            ]
            sysutil_io_now = np.array(psutil.disk_io_counters()[0:4])
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

    def start_monitors(self, uart_baudrate: int = 0) -> NoReturn:
        self.dmesg_mon_t = threading.Thread(target=self.monitor_dmesg, daemon=True)
        self.dmesg_mon_t.start()
        self.ptp4l_mon_t = threading.Thread(target=self.monitor_ptp4l, daemon=True)
        self.ptp4l_mon_t.start()
        self.uart_mon_t = threading.Thread(
            target=self.monitor_uart, args=(uart_baudrate,), daemon=True
        )
        self.uart_mon_t.start()

    def monitor_uart(self, baudrate: int, poll_intervall: float = 0.01) -> NoReturn:
        # TODO: TEST - Not final, goal: raw bytes in hdf5
        # - uart is bytes-type -> storing in hdf5 is hard,
        #   tried 'S' and opaque-type -> failed with errors
        # - converting is producing ValueError on certain chars,
        #   errors="backslashreplace" does not help
        # TODO: eval https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.to_bytes
        if (not self._write_uart) or (not isinstance(baudrate, int)) or (baudrate == 0):
            return
        global monitors_end
        logger.debug(
            f"Will start UART-Monitor for target on '{self.uart_path}' @ {baudrate} baud"
        )
        tevent = threading.Event()
        try:
            # open serial as non-exclusive
            with serial.Serial(self.uart_path, baudrate, timeout=0) as uart:
                while True:
                    if monitors_end.is_set():
                        break
                    if uart.in_waiting > 0:
                        output = (
                            uart.read(uart.in_waiting)
                            .decode("ascii", errors="replace")
                            .replace("\x00", "")
                        )
                        if len(output) > 0:
                            data_length = self.uart_grp["time"].shape[0]
                            if self.sysutil_pos >= data_length:
                                data_length += self.uart_inc
                                self.uart_grp["time"].resize((data_length,))
                                self.uart_grp["message"].resize((data_length,))
                            self.uart_grp["time"][self.uart_pos] = int(time.time()) * (
                                10**9
                            )
                            self.uart_grp["message"][
                                self.uart_pos
                            ] = output  # np.void(uart_rx)
                            self.uart_pos += 1
                    tevent.wait(poll_intervall)  # rate limiter
        except ValueError as e:
            logger.error(
                f"[UartMonitor] PySerial ValueError '{e}' - "
                f"couldn't configure serial-port '{self.uart_path}' "
                f"with baudrate={baudrate} -> will skip logging"
            )
        except serial.SerialException as e:
            logger.error(
                f"[UartMonitor] pySerial SerialException '{e} - "
                f"Couldn't open Serial-Port '{self.uart_path}' to target "
                "-> will skip logging"
            )
        logger.debug("[UartMonitor] ended itself")

    def monitor_dmesg(self, backlog: int = 40, poll_intervall: float = 0.1):
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
        proc_dmesg = subprocess.Popen(  # noqa S603
            cmd_dmesg, stdout=subprocess.PIPE, universal_newlines=True
        )
        tevent = threading.Event()
        for line in iter(proc_dmesg.stdout.readline, ""):
            if monitors_end.is_set():
                break
            line = str(line).strip()[:128]
            try:
                data_length = self.dmesg_grp["time"].shape[0]
                if self.dmesg_pos >= data_length:
                    data_length += self.dmesg_inc
                    self.dmesg_grp["time"].resize((data_length,))
                    self.dmesg_grp["message"].resize((data_length,))
                self.dmesg_grp["time"][self.dmesg_pos] = int(time.time() * (10**9))
                self.dmesg_grp["message"][self.dmesg_pos] = line
            except OSError:
                logger.error(
                    f"[DmesgMonitor] Caught a Write Error for Line: [{type(line)}] {line}"
                )
            tevent.wait(poll_intervall)  # rate limiter
        logger.debug("[DmesgMonitor] ended itself")

    def monitor_ptp4l(self, poll_intervall: float = 0.25):
        # example:
        # sheep1 ptp4l[378]: [821.629] master offset -4426 s2 freq +285889 path delay 12484
        global monitors_end
        cmd_ptp4l = [
            "sudo",
            "journalctl",
            "--unit=ptp4l",
            "--follow",
            "--lines=1",
            "--output=short-precise",
        ]  # for client
        proc_ptp4l = subprocess.Popen(  # noqa S603
            cmd_ptp4l, stdout=subprocess.PIPE, universal_newlines=True
        )
        tevent = threading.Event()
        for line in iter(proc_ptp4l.stdout.readline, ""):
            if monitors_end:
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
                if self.timesync_pos > data_length:
                    data_length += self.timesync_inc
                    self.timesync_grp["time"].resize((data_length,))
                    self.timesync_grp["values"].resize((data_length, 3))
                self.timesync_grp["time"][self.timesync_pos] = int(
                    time.time() * (10**9)
                )
                self.timesync_grp["values"][self.timesync_pos, :] = values[0:3]
            except OSError:
                logger.error(
                    f"[PTP4lMonitor] Caught a Write Error for Line: [{type(line)}] {line}"
                )
            tevent.wait(poll_intervall)  # rate limiter
        logger.debug("[PTP4lMonitor] ended itself")

    def add_dataset_time(
        self, grp: h5py.Group, length: int, chunks: Union[bool, tuple] = True
    ) -> NoReturn:
        grp.create_dataset(
            "time",
            (length,),
            dtype="u8",
            maxshape=(None,),
            chunks=chunks,
            compression=self.compression_algo,
        )
        grp["time"].attrs["unit"] = "ns"
        grp["time"].attrs["description"] = "system time [ns]"

    def __setitem__(self, key, item):
        """Offer a convenient interface to store any relevant key-value data"""
        return self._h5file.attrs.__setitem__(key, item)
