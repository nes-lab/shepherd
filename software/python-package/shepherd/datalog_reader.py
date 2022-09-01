"""
shepherd.datalog_reader
~~~~~
Provides classes for retrieving sampled IV data from HDF5 files.
stripped version of https://github.com/orgua/shepherd-datalib/blob/main/src/shepherd_data/reader.py
-> currently the easiest way to get rid of some dependencies (mostly pandas, that gets installed by src and fails on BB)
"""
import logging
import errno
import os
from itertools import product
from pathlib import Path
from typing import NoReturn, Union, Dict

import h5py
import yaml

from shepherd.calibration import convert_raw_to_value


class LogReader:
    """Sequentially Reads shepherd-data from HDF5 file.

    Args:
        file_path: Path of hdf5 file containing shepherd data with iv-samples, iv-curves or isc&voc
        verbose: more info during usage, 'None' skips the setter
    """

    samples_per_buffer: int = 10_000
    samplerate_sps: int = 100_000
    sample_interval_ns: int = int(10**9 // samplerate_sps)
    sample_interval_s: float = 1 / samplerate_sps

    max_elements: int = (
        40 * samplerate_sps
    )  # per iteration (40s full res, < 200 MB RAM use)

    mode_dtype_dict = {
        "harvester": ["ivsample", "ivcurve", "isc_voc"],
        "emulator": ["ivsample"],
    }

    runtime_s: float = None
    file_size: int = None
    data_rate: float = None

    _logger: logging.Logger = logging.getLogger("SHPData.Reader")

    h5file: h5py.File = None
    ds_time: h5py.Dataset = None
    ds_voltage: h5py.Dataset = None
    ds_current: h5py.Dataset = None
    _cal: dict = None  # dict[str, dict]

    def __init__(self, file_path: Union[Path, None], verbose: Union[bool, None] = True):
        self._skip_open = file_path is None  # for access by writer-class
        if not self._skip_open:
            self._file_path = Path(file_path)
        if verbose is not None:
            self._logger.setLevel(logging.INFO if verbose else logging.WARNING)

    def __enter__(self):
        if not self._skip_open:
            if not self._file_path.exists():
                raise FileNotFoundError(
                    errno.ENOENT,
                    os.strerror(errno.ENOENT),
                    self._file_path.name,
                )
            self.h5file = h5py.File(self._file_path, "r")

            if self.is_valid():
                self._logger.info("File is available now")
            else:
                self._logger.error(
                    "File is faulty! Will try to open but there might be dragons"
                )

        self.ds_time = self.h5file["data"]["time"]
        self.ds_voltage = self.h5file["data"]["voltage"]
        self.ds_current = self.h5file["data"]["current"]
        self._cal = {
            "voltage": {
                "gain": self.ds_voltage.attrs["gain"],
                "offset": self.ds_voltage.attrs["offset"],
            },
            "current": {
                "gain": self.ds_current.attrs["gain"],
                "offset": self.ds_current.attrs["offset"],
            },
        }
        self._refresh_file_stats()

        if not self._skip_open:
            self._logger.info(
                "Reading data from '%s'\n"
                "\t- runtime %s s\n"
                "\t- mode = %s\n"
                "\t- window_size = %s\n"
                "\t- size = %s MiB\n"
                "\t- rate = %s KiB/s",
                self._file_path,
                self.runtime_s,
                self.get_mode(),
                self.get_window_samples(),
                round(self.file_size / 2**20),
                round(self.data_rate / 2**10),
            )
        return self

    def __exit__(self, *exc):
        if not self._skip_open:
            self.h5file.close()

    def _refresh_file_stats(self) -> NoReturn:
        """update internal states, helpful after resampling or other changes in data-group"""
        self.h5file.flush()
        if self.ds_time.shape[0] > 1:
            self.sample_interval_ns = int(self.ds_time[1] - self.ds_time[0])
            self.samplerate_sps = max(int(10**9 // self.sample_interval_ns), 1)
            self.sample_interval_s = 1.0 / self.samplerate_sps
        self.runtime_s = round(self.ds_time.shape[0] / self.samplerate_sps, 1)
        self.file_size = self._file_path.stat().st_size
        self.data_rate = self.file_size / self.runtime_s if self.runtime_s > 0 else 0

    def read_buffers(self, start_n: int = 0, end_n: int = None) -> tuple:
        """Generator that reads the specified range of buffers from the hdf5 file.
        can be configured on first call

        Args:
            :param start_n: (int) Index of first buffer to be read
            :param end_n: (int) Index of last buffer to be read
        Yields:
            Buffers between start and end (tuple with time, voltage, current)
        """
        if end_n is None:
            end_n = int(self.ds_time.shape[0] // self.samples_per_buffer)
        self._logger.debug(
            "Reading blocks from %s to %s from source-file", start_n, end_n
        )
        for i in range(start_n, end_n):
            idx_start = i * self.samples_per_buffer
            idx_end = idx_start + self.samples_per_buffer

            yield (
                self.ds_time[idx_start:idx_end],
                self.ds_voltage[idx_start:idx_end],
                self.ds_current[idx_start:idx_end],
            )

    def get_calibration_data(self) -> dict:
        """Reads calibration-data from hdf5 file.

        :return: Calibration data as CalibrationData object
        """
        return self._cal

    def get_window_samples(self) -> int:
        """
        :return:
        """
        if "window_samples" in self.h5file["data"].attrs.keys():
            return self.h5file["data"].attrs["window_samples"]
        return 0

    def get_mode(self) -> str:
        if "mode" in self.h5file.attrs.keys():
            return self.h5file.attrs["mode"]
        return ""

    def get_config(self) -> Dict:
        if "config" in self.h5file["data"].attrs.keys():
            return yaml.safe_load(self.h5file["data"].attrs["config"])
        return {}

    def get_hostname(self) -> str:
        if "hostname" in self.h5file.attrs.keys():
            return self.h5file.attrs["hostname"]
        return "unknown"

    def get_datatype(self) -> str:
        if "datatype" in self.h5file["data"].attrs.keys():
            return self.h5file["data"].attrs["datatype"]
        return ""

    def get_hrv_config(self) -> dict:
        """essential info for harvester
        :return: config-dict directly for vHarvester to be used during emulation
        """
        return {
            "dtype": self.get_datatype(),
            "window_samples": self.get_window_samples(),
        }

    def is_valid(self) -> bool:
        """checks file for plausibility

        :return: state of validity
        """
        # hard criteria
        if "data" not in self.h5file.keys():
            self._logger.error("root data-group not found (@Validator)")
            return False
        for attr in ["mode"]:
            if attr not in self.h5file.attrs.keys():
                self._logger.error(
                    "attribute '%s' not found in file (@Validator)", attr
                )
                return False
            if self.h5file.attrs["mode"] not in self.mode_dtype_dict:
                self._logger.error("unsupported mode '%s' (@Validator)", attr)
                return False
        for attr in ["window_samples", "datatype"]:
            if attr not in self.h5file["data"].attrs.keys():
                self._logger.error(
                    "attribute '%s' not found in data-group (@Validator)", attr
                )
                return False
        for dset in ["time", "current", "voltage"]:
            if dset not in self.h5file["data"].keys():
                self._logger.error("dataset '%s' not found (@Validator)", dset)
                return False
        for dset, attr in product(["current", "voltage"], ["gain", "offset"]):
            if attr not in self.h5file["data"][dset].attrs.keys():
                self._logger.error(
                    "attribute '%s' not found in dataset '%s' (@Validator)",
                    attr,
                    dset,
                )
                return False
        if self.get_datatype() not in self.mode_dtype_dict[self.get_mode()]:
            self._logger.error(
                "unsupported type '%s' for mode '%s' (@Validator)",
                self.get_datatype(),
                self.get_mode(),
            )
            return False

        if self.get_datatype() == "ivcurve" and self.get_window_samples() < 1:
            self._logger.error(
                "window size / samples is < 1 -> invalid for ivcurves-datatype (@Validator)"
            )
            return False

        # soft-criteria:
        if self.get_datatype() != "ivcurve" and self.get_window_samples() > 0:
            self._logger.warning(
                "window size / samples is > 0 despite not using the ivcurves-datatype (@Validator)"
            )
        # same length of datasets:
        ds_time_size = self.h5file["data"]["time"].shape[0]
        for dset in ["current", "voltage"]:
            ds_size = self.h5file["data"][dset].shape[0]
            if ds_time_size != ds_size:
                self._logger.warning(
                    "dataset '%s' has different size (=%s), "
                    "compared to time-ds (=%s) (@Validator)",
                    dset,
                    ds_size,
                    ds_time_size,
                )
        # dataset-length should be multiple of buffersize
        remaining_size = ds_time_size % self.samples_per_buffer
        if remaining_size != 0:
            self._logger.warning(
                "datasets are not aligned with buffer-size (@Validator)"
            )
        # check compression
        for dset in ["time", "current", "voltage"]:
            comp = self.h5file["data"][dset].compression
            opts = self.h5file["data"][dset].compression_opts
            if comp not in [None, "gzip", "lzf"]:
                self._logger.warning(
                    "unsupported compression found (%s != None, lzf, gzip) (@Validator)",
                    comp,
                )
            if (comp == "gzip") and (opts is not None) and (int(opts) > 1):
                self._logger.warning(
                    "gzip compression is too high (%s > 1) for BBone (@Validator)",
                    opts,
                )
        # host-name
        if self.get_hostname() == "unknown":
            self._logger.warning("Hostname was not set (@Validator)")
        return True

    def __getitem__(self, key):
        """returns attribute or (if none found) a handle for a group or dataset (if found)

        :param key: attribute, group, dataset
        :return: value of that key, or handle of object
        """
        if key in self.h5file.attrs.keys():
            return self.h5file.attrs.__getitem__(key)
        if key in self.h5file.keys():
            return self.h5file.__getitem__(key)
        raise KeyError
