# -*- coding: utf-8 -*-

"""
shepherd.calibration
~~~~~
Provides CalibrationData class, defining the format of the SHEPHERD calibration
data


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""

import yaml
import struct
from scipy import stats
import numpy as np
from pathlib import Path

from shepherd import calibration_default

# gain and offset will be normalized to SI-Units, most likely V, A
# -> general formula is:    si-value = raw_value * gain + offset
# TODO: emulation has no ADC_voltage
cal_component_list = ["harvesting", "emulation"]
cal_channel_list = ["dac_voltage_a", "dac_voltage_b", "adc_current", "adc_voltage"]
# functions from cal-default.py to convert the channels in cal_channel_list
cal_channel_fn_list = ["dac_ch_a_voltage_to_raw", "dac_ch_b_voltage_to_raw", "adc_current_to_raw", "adc_voltage_to_raw"]
# translator-dicts for datalog
cal_channel_harvest_dict = {"voltage": "adc_voltage", "current": "adc_current"}
cal_channel_emulation_dict = {"voltage": "dac_voltage_b", "current": "adc_current"}
cal_parameter_list = ["gain", "offset"]


# slim alternative to the methods (same name) of CalibrationData
def convert_raw_to_value(cal_dict: dict, raw: int) -> float:  # more precise dict[str, int], trouble with py3.6
    return (float(raw) * cal_dict["gain"]) + cal_dict["offset"]


def convert_value_to_raw(cal_dict: dict, value: float) -> int:  # more precise dict[str, int], trouble with py3.6
    return int((value - cal_dict["offset"]) / cal_dict["gain"])


class CalibrationData(object):
    """Represents SHEPHERD calibration data.

    Defines the format of calibration data and provides convenient functions
    to read and write calibration data.

    Args:
        calib_dict (dict): Dictionary containing calibration data.
    """

    def __init__(self, calib_dict: dict):
        self._data = calib_dict

    def __getitem__(self, key: str):
        return self._data[key]

    def __repr__(self):
        return yaml.dump(self._data, default_flow_style=False)

    @classmethod
    def from_bytestr(cls, bytestr: str):
        """Instantiates calibration data based on byte string.

        This is mainly used to deserialize data read from an EEPROM memory.

        Args:
            bytestr (str): Byte string containing calibration data.
        
        Returns:
            CalibrationData object with extracted calibration data.
        """
        val_count = len(cal_component_list) * len(cal_channel_list) * len(cal_parameter_list)
        values = struct.unpack(">" + val_count * "d", bytestr)  # X double float, big endian
        calib_dict = dict()
        counter = 0
        for component in cal_component_list:
            calib_dict[component] = dict()
            for channel in cal_channel_list:
                calib_dict[component][channel] = dict()
                for parameter in cal_parameter_list:
                    val = float(values[counter])
                    if np.isnan(val):
                        raise ValueError(
                            f"{ component } { channel } { parameter } not a valid number"
                        )
                    calib_dict[component][channel][parameter] = val
                    counter += 1
        return cls(calib_dict)

    @classmethod
    def from_default(cls):
        """Instantiates calibration data from default hardware values.

        Returns:
            CalibrationData object with default calibration values.
        """
        calib_dict = dict()
        for component in cal_component_list:
            calib_dict[component] = dict()
            for ch_index in range(len(cal_channel_list)):
                channel = cal_channel_list[ch_index]
                cal_fn = cal_channel_fn_list[ch_index]
                calib_dict[component][channel] = dict()
                # generation of gain / offset is reversed at first (raw = (val - off)/gain), but corrected for storing
                offset = getattr(calibration_default, cal_fn)(0)
                gain_inv = (getattr(calibration_default, cal_fn)(1.0) - offset)
                calib_dict[component][channel]["offset"] = -float(offset) / float(gain_inv)
                calib_dict[component][channel]["gain"] = 1.0 / float(gain_inv)

        return cls(calib_dict)

    @classmethod
    def from_yaml(cls, filename: Path):
        """Instantiates calibration data from YAML file.

        Args:
            filename (Path): Path to YAML formatted file containing calibration
                values.
        
        Returns:
            CalibrationData object with extracted calibration data.
        """
        with open(filename, "r") as stream:
            in_data = yaml.safe_load(stream)

        return cls(in_data["calibration"])

    @classmethod
    def from_measurements(cls, filename: Path):
        """Instantiates calibration data from calibration measurements.

        Args:
            filename (Path): Path to YAML formatted file containing calibration
                measurement values.
        
        Returns:
            CalibrationData object with extracted calibration data.
        """
        with open(filename, "r") as stream:
            calib_data = yaml.safe_load(stream)

        calib_dict = dict()

        for component in cal_component_list:
            calib_dict[component] = dict()
            for channel in cal_channel_list:
                calib_dict[component][channel] = dict()
                sample_points = calib_data["measurements"][component][channel]
                x = np.empty(len(sample_points))
                y = np.empty(len(sample_points))
                for i, point in enumerate(sample_points):
                    x[i] = point["measured"]
                    y[i] = point["reference"]
                slope, intercept, _, _, _ = stats.linregress(x, y)
                calib_dict[component][channel]["gain"] = float(slope)   # TODO: possibly wrong after all the changes, TEST
                calib_dict[component][channel]["offset"] = float(intercept)

        return cls(calib_dict)

    def convert_raw_to_value(self, component: str, channel: str, raw: int) -> float:
        offset = self._data[component][channel]["offset"]
        gain = self._data[component][channel]["gain"]
        return (float(raw) * gain) + offset

    def convert_value_to_raw(self, component: str, channel: str, value: float) -> int:
        offset = self._data[component][channel]["offset"]
        gain = self._data[component][channel]["gain"]
        return int((value - offset) / gain)

    def to_bytestr(self):
        """Serializes calibration data to byte string.

        Used to prepare data for writing it to EEPROM.

        Returns:
            Byte string representation of calibration values.
        """
        flattened = list()
        for component in cal_component_list:
            for channel in cal_channel_list:
                for parameter in cal_parameter_list:
                    flattened.append(self._data[component][channel][parameter])
        val_count = len(cal_component_list) * len(cal_channel_list) * len(cal_parameter_list)
        return struct.pack(">" + val_count * "d", *flattened)

    def export_for_sysfs(self) -> dict:  # more precise dict[str, int], trouble with py3.6
        cal_set = dict()
        # ADC is calculated in nA (nano-amps), gain is shifted by 8 bit [scaling according to commons.h]
        cal_set["adc_gain"] = int(1e9 * (2 ** 8) * self._data["emulation"]["adc_current"]["gain"])
        cal_set["adc_offset"] = int(1e9 * (2 ** 0) * self._data["emulation"]["adc_current"]["offset"])
        # DAC is calculated in uV (micro-volts), gain is shifted by 20 bit
        cal_set["dac_gain"] = int((2 ** 20) / (1e6 * self._data["emulation"]["dac_voltage_a"]["gain"]))
        cal_set["dac_offset"] = int(1e6 * (2 ** 0) * self._data["emulation"]["dac_voltage_a"]["offset"])

        for value in cal_set.values():
            if value >= 2**31:
                raise ValueError(f"Number (={value}) exceeds 32bit container, in CalibrationData.export_for_sysfs()")
        return cal_set

