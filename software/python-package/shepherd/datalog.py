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
import subprocess
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

from shepherd.calibration import CalibrationData
from shepherd.calibration import cal_channel_harvest_dict
from shepherd.calibration import cal_channel_emulation_dict
from shepherd.calibration import cal_parameter_list

from shepherd.shepherd_io import DataBuffer
from shepherd.commons import GPIO_LOG_BIT_POSITIONS, SAMPLE_INTERVAL_US, MAX_GPIO_EVT_PER_BUFFER, ADC_SAMPLES_PER_BUFFER

logger = logging.getLogger(__name__)

"""
An entry for an exception to be stored together with the data consists of a
timestamp, a custom message and an arbitrary integer value
"""
ExceptionRecord = namedtuple(
    "ExceptionRecord", ["timestamp", "message", "value"]
)

monitors_end = threading.Event()


h5_drivers = {h5py.h5fd.CORE: "CORE",
              h5py.h5fd.FAMILY: "FAMILY",
              h5py.h5fd.fileobj_driver: "fileobj_driver",
              h5py.h5fd.LOG: "LOG",
              h5py.h5fd.MULTI: "MULTI",
              h5py.h5fd.SEC2: "SEC2",
              h5py.h5fd.STDIO: "STDIO",
              h5py.h5fd.WINDOWS: "WINDOWS",
              }


def unique_path(base_path: Union[str, Path], suffix: str):
    counter = 0
    while True:
        path = base_path.with_suffix(f".{ counter }{ suffix }")
        if not path.exists():
            return path
        counter += 1


def add_dataset_time(grp: h5py.Group, length: int, chunks: Union[bool, tuple] = True) -> NoReturn:
    grp.create_dataset(
        "time",
        (length,),
        dtype="u8",
        maxshape=(None,),
        chunks=chunks,
        compression=LogWriter.compression_algo,
    )
    grp["time"].attrs["unit"] = f"ns"
    grp["time"].attrs["description"] = "system time [ns]"


class LogWriter(object):
    """Stores data coming from PRU's in HDF5 format

    Args:
        store_path (Path): Name of the HDF5 file that data will be written to
        calibration_data (CalibrationData): Data is written as raw ADC
            values. We need calibration data in order to convert to physical
            units later.
        mode (str): Indicates if this is data from recording or emulation
        force_overwrite (bool): Overwrite existing file with the same name
        samples_per_buffer (int): Number of samples contained in a single
            shepherd buffer
        buffer_period_ns (int): Duration of a single shepherd buffer in
            nanoseconds

    """

    # choose lossless compression filter
    # - gzip: good compression, moderate speed, select level from 1-9, default is 4
    # - lzf: low to moderate compression, very fast, no options
    compression_algo = "lzf"
    sys_log_intervall_ns = 1 * (10 ** 9)  # step-size is 1 s
    sys_log_last_ns = 0
    dmesg_mon_t = None
    ptp4l_mon_t = None
    uart_mon_t = None

    def __init__(
            self,
            store_path: Path,
            calibration_data: CalibrationData,
            mode: str = "harvesting",
            force_overwrite: bool = False,
            samples_per_buffer: int = 10_000,
            buffer_period_ns: int = 100_000_000,
            skip_voltage: bool = False,
            skip_current: bool = False,
            skip_gpio: bool = False,
    ):
        if force_overwrite or not store_path.exists():
            self.store_path = store_path
            logger.info(f"Storing data under '{self.store_path}'")
        else:
            base_dir = store_path.resolve().parents[0]
            self.store_path = unique_path(
                base_dir / store_path.stem, store_path.suffix
            )
            logger.warning(
                    f"File {str(store_path)} already exists.. "
                    f"storing under {str(self.store_path)} instead"
            )
        # Refer to shepherd/calibration.py for the format of calibration data
        if mode == "harvesting_test":
            self.mode = "harvesting"
        elif mode == "emulation_test":
            self.mode = "emulation"
        else:
            self.mode = mode

        self.calibration_data = calibration_data
        self.chunk_shape = (samples_per_buffer,)
        self.sampling_interval = int(buffer_period_ns // samples_per_buffer)
        self.buffer_timeseries = self.sampling_interval * np.arange(samples_per_buffer).astype("u8")
        self._write_voltage = not skip_voltage
        self._write_current = not skip_current
        self._write_gpio = (not skip_gpio) and ("emulat" in mode)
        logger.debug(f"Set log-writing for voltage:     {'enabled' if self._write_voltage else 'disabled'}")
        logger.debug(f"Set log-writing for current:     {'enabled' if self._write_current else 'disabled'}")
        logger.debug(f"Set log-writing for gpio:        {'enabled' if self._write_gpio else 'disabled'}")

        # initial sysutil-reading and delta-history
        self.sysutil_io_last = np.array(psutil.disk_io_counters()[0:4])
        self.sysutil_nw_last = np.array(psutil.net_io_counters()[0:2])
        # todo: test-implementation, inc by chunk-size where needed! gpio chunks can be max_gpio...
        # h5py v3.4 is taking 20% longer for .write_buffer() than v2.1
        # this change speeds up v3.4 by 30% (even system load drops from 90% to 70%), v2.1 by 16%
        inc_duration = int(100)
        inc_length = int(inc_duration * 10**6 // SAMPLE_INTERVAL_US)
        self.data_pos = 0
        self.data_inc = inc_length
        self.gpio_pos = 0
        self.gpio_inc = MAX_GPIO_EVT_PER_BUFFER
        self.sysutil_pos = 0
        self.sysutil_inc = inc_duration + 20
        self.uart_pos = 0
        self.uart_inc = 100
        self.dmesg_pos = 0
        self.dmesg_inc = 100
        self.xcpt_pos = 0
        self.xcpt_inc = 100
        self.timesync_pos = 0
        self.timesync_inc = inc_duration + 20

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
        driver = h5_drivers[self._h5file.id.get_access_plist().get_driver()]
        logger.debug(f"H5Py: driver={driver}, cache_setting={settings} (_mdc, _nslots, _nbytes, _w0)")

        # Store the mode in order to allow user to differentiate harvesting vs emulation data
        self._h5file.attrs.__setitem__("mode", self.mode)

        # Store voltage and current samples in the data group, both are stored as 4 Byte unsigned int
        self.data_grp = self._h5file.create_group("data")
        # TODO: add filter-step, delta-offset is static 10_000 ns
        # TODO: time-dataset should be replaced - it is not the real time, but just a post-calculated sequence
        add_dataset_time(self.data_grp, self.data_inc, self.chunk_shape)
        self.data_grp.create_dataset(
            "current",
            (self.data_inc,),
            dtype="u4",
            maxshape=(None,),
            chunks=self.chunk_shape,
            compression=self.compression_algo,
        )
        self.data_grp["current"].attrs["unit"] = "A"
        self.data_grp["current"].attrs["description"] = "current [A] = value * gain + offset"
        self.data_grp.create_dataset(
            "voltage",
            (self.data_inc,),
            dtype="u4",
            maxshape=(None,),
            chunks=self.chunk_shape,
            compression=LogWriter.compression_algo,
        )
        self.data_grp["voltage"].attrs["unit"] = "V"
        self.data_grp["voltage"].attrs["description"] = "voltage [V] = value * gain + offset"

        for channel, parameter in product(["current", "voltage"], cal_parameter_list):
            # TODO: not the cleanest cal-selection, maybe just hand the resulting two and rename them already to "current, voltage" in calling FN
            cal_channel = cal_channel_harvest_dict[channel] if (self.mode == "harvesting") else cal_channel_emulation_dict[channel]
            self.data_grp[channel].attrs[parameter] = self.calibration_data[self.mode][cal_channel][parameter]

        # Create group for gpio data
        self.gpio_grp = self._h5file.create_group("gpio")
        add_dataset_time(self.gpio_grp, self.gpio_inc)
        self.gpio_grp.create_dataset(
            "value",
            (self.gpio_inc,),
            dtype="u2",
            maxshape=(None,),
            chunks=True,
            compression=LogWriter.compression_algo,
        )
        self.gpio_grp["value"].attrs["unit"] = "n"
        self.gpio_grp["value"].attrs["description"] = GPIO_LOG_BIT_POSITIONS

        # Create group for exception logs, entry consists of a timestamp, a message and a value
        self.xcpt_grp = self._h5file.create_group("exceptions")
        add_dataset_time(self.xcpt_grp, self.xcpt_inc)
        self.xcpt_grp.create_dataset(
            "message",
            (self.xcpt_inc,),
            dtype=h5py.special_dtype(vlen=str),
            maxshape=(None,),
            chunks=True,
        )
        self.xcpt_grp.create_dataset("value", (0,), dtype="u4", maxshape=(None,), chunks=True)
        self.xcpt_grp["value"].attrs["unit"] = "n"

        # UART-Logger
        self.uart_grp = self._h5file.create_group("uart")
        add_dataset_time(self.uart_grp, self.uart_inc)
        # Every log entry consists of a timestamp and a message
        self.uart_grp.create_dataset(
            "message",
            (self.uart_inc,),
            dtype=h5py.special_dtype(vlen=bytes),
            maxshape=(None,),
            chunks=True,
        )
        self.uart_grp["message"].attrs["description"] = f"raw ascii-bytes"

        # Create sys-Logger
        self.sysutil_grp = self._h5file.create_group("sysutil")
        add_dataset_time(self.sysutil_grp, self.sysutil_inc)
        self.sysutil_grp["time"].attrs["unit"] = "ns"
        self.sysutil_grp["time"].attrs["description"] = "system time [ns]"
        self.sysutil_grp.create_dataset("cpu", (self.sysutil_inc,), dtype="u1", maxshape=(None,), chunks=True, )
        self.sysutil_grp["cpu"].attrs["unit"] = "%"
        self.sysutil_grp["cpu"].attrs["description"] = "cpu_util [%]"
        self.sysutil_grp.create_dataset("ram", (self.sysutil_inc, 2), dtype="u1", maxshape=(None, 2), chunks=True, )
        self.sysutil_grp["ram"].attrs["unit"] = "%"
        self.sysutil_grp["ram"].attrs["description"] = "ram_available [%], ram_used [%]"
        self.sysutil_grp.create_dataset("io", (self.sysutil_inc, 4), dtype="u8", maxshape=(None, 4), chunks=True, )
        self.sysutil_grp["io"].attrs["unit"] = "n"
        self.sysutil_grp["io"].attrs["description"] = "io_read [n], io_write [n], io_read [byte], io_write [byte]"
        self.sysutil_grp.create_dataset("net", (self.sysutil_inc, 2), dtype="u8", maxshape=(None, 2), chunks=True, )
        self.sysutil_grp["net"].attrs["unit"] = "n"
        self.sysutil_grp["net"].attrs["description"] = "nw_sent [byte], nw_recv [byte]"
        self.log_sys_stats()

        # Create dmesg-Logger -> consists of a timestamp and a message
        self.dmesg_grp = self._h5file.create_group("dmesg")
        add_dataset_time(self.dmesg_grp, self.dmesg_inc)
        self.dmesg_grp.create_dataset(
            "message",
            (self.dmesg_inc,),
            dtype=h5py.special_dtype(vlen=str),
            maxshape=(None,),
            chunks=True,
        )

        # Create timesync-Logger
        self.timesync_grp = self._h5file.create_group("timesync")
        add_dataset_time(self.timesync_grp, self.timesync_inc)
        self.timesync_grp.create_dataset("value", (self.timesync_inc, 3), dtype="i8", maxshape=(None, 3), chunks=True)
        self.timesync_grp["value"].attrs["unit"] = "ns, Hz, ns"
        self.timesync_grp["value"].attrs["description"] = "master offset [ns], s2 freq [Hz], path delay [ns]"
        # h5_structure_printer(self._h5file)  # TODO: just for debug
        return self

    def __exit__(self, *exc):
        global monitors_end
        monitors_end.set()

        # meantime: trim over-provisioned parts
        self.data_grp["time"].resize((self.data_pos if self._write_current or self._write_voltage else 0,))
        self.data_grp["voltage"].resize((self.data_pos if self._write_voltage else 0,))
        self.data_grp["current"].resize((self.data_pos if self._write_current else 0,))
        self.gpio_grp["time"].resize((self.gpio_pos if self._write_gpio else 0,))
        self.gpio_grp["value"].resize((self.gpio_pos if self._write_gpio else 0,))
        self.sysutil_grp["time"].resize((self.sysutil_pos,))
        self.sysutil_grp["cpu"].resize((self.sysutil_pos,))
        self.sysutil_grp["ram"].resize((self.sysutil_pos, 2))
        self.sysutil_grp["io"].resize((self.sysutil_pos, 4))
        self.sysutil_grp["net"].resize((self.sysutil_pos, 2))
        self.uart_grp["time"].resize((self.uart_pos,))
        self.uart_grp["message"].resize((self.uart_pos,))
        self.dmesg_grp["time"].resize((self.dmesg_pos,))
        self.dmesg_grp["message"].resize((self.dmesg_pos,))
        self.xcpt_grp["time"].resize((self.xcpt_pos,))
        self.xcpt_grp["message"].resize((self.xcpt_pos,))
        self.timesync_grp["time"].resize((self.timesync_pos,))
        self.timesync_grp["message"].resize((self.timesync_pos,))

        time.sleep(1)  # TODO: should work propably without it
        if self.dmesg_mon_t is not None:
            logger.info(f"[LogWriter] terminate Dmesg-Monitor ({self.dmesg_grp['time'].shape[0]} entries)")
            self.dmesg_mon_t = None
        if self.ptp4l_mon_t is not None:
            logger.info(f"[LogWriter] terminate PTP4L-Monitor ({self.timesync_grp['time'].shape[0]} entries)")
            self.ptp4l_mon_t = None
        if self.uart_mon_t is not None:
            logger.info(f"[LogWriter] terminate UART-Monitor  ({self.uart_grp['time'].shape[0]} entries)")
            self.uart_mon_t = None
        runtime = round(self.data_grp['time'].shape[0] * SAMPLE_INTERVAL_US / 1e6, 1)
        logger.info(f"[LogWriter] flushing hdf5 file ({runtime} s iv-data, {self.gpio_grp['time'].shape[0]} gpio-entries)")
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
            self.data_grp["voltage"].resize((data_length if self._write_voltage else 0,))
            self.data_grp["current"].resize((data_length if self._write_current else 0,))

        if self._write_voltage:
            self.data_grp["voltage"][self.data_pos:data_end_pos] = buffer.voltage

        if self._write_current:
            self.data_grp["current"][self.data_pos:data_end_pos] = buffer.current

        if self._write_voltage or self._write_current:
            self.data_grp["time"][self.data_pos:data_end_pos] = (
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
            self.gpio_grp["time"][self.gpio_pos:gpio_new_pos] = buffer.gpio_edges.timestamps_ns
            self.gpio_grp["value"][self.gpio_pos:gpio_new_pos] = buffer.gpio_edges.values
            self.gpio_pos = gpio_new_pos

        self.log_sys_stats()

    def write_exception(self, exception: ExceptionRecord) -> NoReturn:
        """ Writes an exception to the hdf5 file.
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
        """ captures state of system in a fixed intervall
            https://psutil.readthedocs.io/en/latest/#cpu
        :return: none
        """
        ts_now_ns = int(time.time() * (10 ** 9))
        if ts_now_ns >= (self.sys_log_last_ns + self.sys_log_intervall_ns):
            data_length = self.sysutil_grp["time"].shape[0]
            if self.sysutil_pos >= data_length:
                data_length += self.sysutil_inc
                self.sysutil_grp["time"].resize((data_length,))
                self.sysutil_grp["cpu"].resize((data_length,))
                self.sysutil_grp["ram"].resize((data_length, 2))
                self.sysutil_grp["io"].resize((data_length, 4))
                self.sysutil_grp["net"].resize((data_length, 2))
            self.sys_log_last_ns = ts_now_ns
            self.sysutil_grp["time"][self.sysutil_pos] = ts_now_ns
            self.sysutil_grp["cpu"][self.sysutil_pos] = int(round(psutil.cpu_percent(0)))
            mem_stat = psutil.virtual_memory()[0:3]
            self.sysutil_grp["ram"][self.sysutil_pos, 0:2] = [int(100 * mem_stat[1] / mem_stat[0]), int(mem_stat[2])]
            sysutil_io_now = np.array(psutil.disk_io_counters()[0:4])
            self.sysutil_grp["io"][self.sysutil_pos, :] = sysutil_io_now - self.sysutil_io_last
            self.sysutil_io_last = sysutil_io_now
            sysutil_nw_now = np.array(psutil.net_io_counters()[0:2])
            self.sysutil_grp["net"][self.sysutil_pos, :] = sysutil_nw_now - self.sysutil_nw_last
            self.sysutil_nw_last = sysutil_nw_now
            self.sysutil_pos += 1
            # TODO: add temp, not working: https://psutil.readthedocs.io/en/latest/#psutil.sensors_temperatures

    def start_monitors(self, uart_baudrate: int = 0) -> NoReturn:
        self.dmesg_mon_t = threading.Thread(target=self.monitor_dmesg, daemon=True)
        self.dmesg_mon_t.start()
        self.ptp4l_mon_t = threading.Thread(target=self.monitor_ptp4l, daemon=True)
        self.ptp4l_mon_t.start()
        self.uart_mon_t = threading.Thread(target=self.monitor_uart, args=(uart_baudrate,), daemon=True)
        self.uart_mon_t.start()

    def monitor_uart(self, baudrate: int, poll_intervall: float = 0.01) -> NoReturn:
        # TODO: TEST - Not final, goal: raw bytes in hdf5
        # - uart is bytes-type -> storing in hdf5 is hard, tried 'S' and opaque-type -> failed with errors
        # - converting is producing ValueError on certain chars, errors="backslashreplace" does not help
        # TODO: evaluate https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.to_bytes
        if not isinstance(baudrate, int) or baudrate == 0:
            return
        global monitors_end
        uart_path = '/dev/ttyO1'
        logger.debug(f"Will start UART-Monitor for target on '{uart_path}' @ {baudrate} baud")
        tevent = threading.Event()
        try:
            # open serial as non-exclusive
            with serial.Serial(uart_path, baudrate, timeout=0) as uart:
                while True:
                    if monitors_end.is_set():
                        break
                    if uart.in_waiting > 0:
                        output = uart.read(uart.in_waiting).decode("ascii", errors="replace").replace('\x00', '')
                        if len(output) > 0:
                            dataset_length = self.uart_grp["time"].shape[0] # TODO: convert and test
                            self.uart_grp["time"].resize((dataset_length + 1,))
                            self.uart_grp["time"][dataset_length] = int(time.time()) * (10 ** 9)
                            self.uart_grp["message"].resize((dataset_length + 1,))
                            self.uart_grp["message"][dataset_length] = output  # np.void(uart_rx)
                    tevent.wait(poll_intervall)  # rate limiter
        except ValueError as e:
            logger.error(
                f"[UartMonitor] PySerial ValueError '{e}' - couldn't configure serial-port '{uart_path}' with baudrate={baudrate} -> will skip logging")
        except serial.SerialException as e:
            logger.error(
                f"[UartMonitor] pySerial SerialException '{e} - Couldn't open Serial-Port '{uart_path}' to target -> will skip logging")
        logger.debug(f"[UartMonitor] ended itself")

    def monitor_dmesg(self, backlog: int = 40, poll_intervall: float = 0.1):
        # var1: ['dmesg', '--follow'] -> not enough control
        global monitors_end
        cmd_dmesg = ['sudo', 'journalctl', '--dmesg', '--follow', f'--lines={backlog}', '--output=short-precise']
        proc_dmesg = subprocess.Popen(cmd_dmesg, stdout=subprocess.PIPE, universal_newlines=True)
        tevent = threading.Event()
        for line in iter(proc_dmesg.stdout.readline, ""):
            if monitors_end.is_set():
                break
            line = str(line).strip()[:128]
            try:
                dataset_length = self.dmesg_grp["time"].shape[0]  # TODO: convert and test
                self.dmesg_grp["time"].resize((dataset_length + 1,))
                self.dmesg_grp["time"][dataset_length] = int(time.time() * (10 ** 9))
                self.dmesg_grp["message"].resize((dataset_length + 1,))
                self.dmesg_grp["message"][dataset_length] = line
            except OSError:
                logger.error(f"[DmesgMonitor] Caught a Write Error for Line: [{type(line)}] {line}")
            tevent.wait(poll_intervall)  # rate limiter
        logger.debug(f"[DmesgMonitor] ended itself")

    def monitor_ptp4l(self, poll_intervall: float = 0.25):
        # example: Feb 16 10:58:37 sheep1 ptp4l[378]: [821.629] master offset      -4426 s2 freq +285889 path delay     12484
        global monitors_end
        cmd_ptp4l = ['sudo', 'journalctl', '--unit=ptp4l', '--follow', '--lines=1', '--output=short-precise']  # for client
        proc_ptp4l = subprocess.Popen(cmd_ptp4l, stdout=subprocess.PIPE, universal_newlines=True)
        tevent = threading.Event()
        for line in iter(proc_ptp4l.stdout.readline, ""):
            if monitors_end:
                break
            try:
                words = str(line).split()
                i_start = words.index("offset")
                values = [int(words[i_start + 1]), int(words[i_start + 4]), int(words[i_start + 7])]
            except ValueError:
                continue
            try:
                dataset_length = self.timesync_grp["time"].shape[0]  # TODO: convert and test
                self.timesync_grp["time"].resize((dataset_length + 1,))
                self.timesync_grp["time"][dataset_length] = int(time.time() * (10 ** 9))
                self.timesync_grp["values"].resize((dataset_length + 1, 3))
                self.timesync_grp["values"][dataset_length, :] = values[0:3]
            except OSError:
                logger.error(f"[PTP4lMonitor] Caught a Write Error for Line: [{type(line)}] {line}")
            tevent.wait(poll_intervall)  # rate limiter
        logger.debug(f"[PTP4lMonitor] ended itself")

    def __setitem__(self, key, item):
        """Offer a convenient interface to store any relevant key-value data"""
        return self._h5file.attrs.__setitem__(key, item)


class LogReader(object):
    """ Sequentially Reads data from HDF5 file.

    Args:
        store_path (Path): Path of hdf5 file containing IV data
        samples_per_buffer (int): Number of IV samples per buffer
    """

    def __init__(self, store_path: Path, samples_per_buffer: int = 10_000):
        self.store_path = store_path
        self.samples_per_buffer = samples_per_buffer

    def __enter__(self):
        self._h5file = h5py.File(self.store_path, "r")
        self.ds_voltage = self._h5file["data"]["voltage"]
        self.ds_current = self._h5file["data"]["current"]
        runtime = round(self.ds_voltage.shape[0] * SAMPLE_INTERVAL_US / 1e6, 1)
        logger.info(f"Reading data from '{str(self.store_path)}', contains {runtime} s")
        return self

    def __exit__(self, *exc):
        self._h5file.close()

    def read_buffers(self, start: int = 0, end: int = None):
        """Reads the specified range of buffers from the hdf5 file.

        Args:
            start (int): Index of first buffer to be read
            end (int): Index of last buffer to be read
        
        Yields:
            Buffers between start and end
        """
        if end is None:
            end = int(
                self._h5file["data"]["time"].shape[0] / self.samples_per_buffer
            )
        logger.debug(f"Reading blocks from { start } to { end } from log")
        verbose = logger.isEnabledFor(logging.DEBUG)  # performance-critical

        for i in range(start, end):
            if verbose:
                ts_start = time.time()
            idx_start = i * self.samples_per_buffer
            idx_end = idx_start + self.samples_per_buffer
            db = DataBuffer(
                voltage=self.ds_voltage[idx_start:idx_end],
                current=self.ds_current[idx_start:idx_end],
            )
            if verbose:
                logger.debug(
                        f"Reading datablock with {self.samples_per_buffer} samples "
                        f"from file took { round(1e3 * (time.time()-ts_start), 2) } ms"
                )
            yield db

    def get_calibration_data(self) -> CalibrationData:
        """Reads calibration data from hdf5 file.

        Returns:
            Calibration data as CalibrationData object
        """
        cal = CalibrationData.from_default()
        for channel, parameter in product(["current", "voltage"], cal_parameter_list):
            cal_channel = cal_channel_harvest_dict[channel]
            cal.data["harvesting"][cal_channel][parameter] = self._h5file["data"][channel].attrs[parameter]
        return CalibrationData(cal)


def h5_structure_printer(file: h5py.File) -> NoReturn:
    # TODO: more recursive with levels, use hasattr(obj, "attribute")
    for group in file:
        h5grp = file.get(group)
        logger.debug(f"[H5File] Group [{group}] Items: {h5grp.items()}")
        for dataset in h5grp:
            h5ds = h5grp.get(dataset)
            logger.debug(f"[H5File] Group [{group}], Dataset [{dataset}] - Chunks={h5ds.chunks}, compression={h5ds.compression}, ")
