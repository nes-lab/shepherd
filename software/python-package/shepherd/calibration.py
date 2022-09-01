# -*- coding: utf-8 -*-

"""
shepherd.calibration
~~~~~
Provides CalibrationData class, defining the format of the SHEPHERD calibration
data


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import logging
import yaml
import struct
import numpy as np
from pathlib import Path
from scipy import stats

# voodoo to allow loading this file from outside (extras)
# TODO: underlying problem for loading shepherd is a missing mockup of gpio-module, sysfs and sharedmem
try:
    import shepherd.calibration_default as cal_def
except ModuleNotFoundError:
    import calibration_default as cal_def

logger = logging.getLogger(__name__)

# gain and offset will be normalized to SI-Units, most likely V, A
# -> general formula is:    si-value = raw_value * gain + offset
# TODO: emulator has no ADC_voltage, but uses this slot to store cal-data for target-port B
cal_component_list = ["harvester", "emulator"]
cal_channel_list = [
    "dac_voltage_a",
    "dac_voltage_b",
    "adc_current",
    "adc_voltage",
]
# functions from cal-default.py to convert the channels in cal_channel_list
cal_channel_fn_list = [
    "dac_voltage_to_raw",
    "dac_voltage_to_raw",
    "adc_current_to_raw",
    "adc_voltage_to_raw",
]
# translator-dicts for datalog
cal_channel_hrv_dict = {"voltage": "adc_voltage", "current": "adc_current"}
cal_channel_emu_dict = {"voltage": "dac_voltage_b", "current": "adc_current"}
cal_parameter_list = ["gain", "offset"]


# slim alternative to the methods (same name) of CalibrationData
def convert_raw_to_value(
    cal_dict: dict, raw: int
) -> float:  # more precise dict[str, int], trouble with py3.6
    return (float(raw) * cal_dict["gain"]) + cal_dict["offset"]


def convert_value_to_raw(
    cal_dict: dict, value: float
) -> int:  # more precise dict[str, int], trouble with py3.6
    return int((value - cal_dict["offset"]) / cal_dict["gain"])


class CalibrationData(object):
    """Represents SHEPHERD calibration data.

    Defines the format of calibration data and provides convenient functions
    to read and write calibration data.

    Args:
        cal_dict (dict): Dictionary containing calibration data.
    """

    def __init__(self, cal_dict: dict):
        self.data = cal_dict

    def __getitem__(self, key: str):
        return self.data[key]

    def __repr__(self):
        return yaml.dump(self.data, default_flow_style=False, sort_keys=False)

    @classmethod
    def from_bytestr(cls, data: bytes):
        """Instantiates calibration data based on byte string.

        This is mainly used to deserialize data read from an EEPROM memory.

        Args:
            data: Byte string containing calibration data.

        Returns:
            CalibrationData object with extracted calibration data.
        """
        val_count = (
            len(cal_component_list)
            * len(cal_channel_list)
            * len(cal_parameter_list)
        )
        values = struct.unpack(
            ">" + val_count * "d", data
        )  # X double float, big endian
        cal_dict = {}
        counter = 0
        for component in cal_component_list:
            cal_dict[component] = {}
            for channel in cal_channel_list:
                cal_dict[component][channel] = {}
                for parameter in cal_parameter_list:
                    val = float(values[counter])
                    if np.isnan(val):
                        raise ValueError(
                            f"{ component } { channel } { parameter } not a valid number"
                        )
                    cal_dict[component][channel][parameter] = val
                    counter += 1
        return cls(cal_dict)

    @classmethod
    def from_default(cls):
        """Instantiates calibration data from default hardware values.

        Returns:
            CalibrationData object with default calibration values.
        """
        cal_dict = {}
        for component in cal_component_list:
            cal_dict[component] = {}
            for ch_index, channel in enumerate(cal_channel_list):
                cal_fn = cal_channel_fn_list[ch_index]
                # generation of gain / offset is reversed at first (raw = (val - off)/gain), but corrected for storing
                offset = getattr(cal_def, cal_fn)(0)
                gain_inv = getattr(cal_def, cal_fn)(1.0) - offset
                cal_dict[component][channel] = {
                    "offset": -float(offset) / float(gain_inv),
                    "gain": 1.0 / float(gain_inv),
                }

        return cls(cal_dict)

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
            meas_data = yaml.safe_load(stream)

        cal_dict = {}

        for component in cal_component_list:
            cal_dict[component] = {}
            for channel in cal_channel_list:
                cal_dict[component][channel] = dict()
                if "dac_voltage" in channel:
                    gain = 1.0 / cal_def.dac_voltage_to_raw(1.0)
                elif "adc_current" in channel:
                    gain = 1.0 / cal_def.adc_current_to_raw(1.0)
                elif "adc_voltage" in channel:
                    gain = 1.0 / cal_def.adc_voltage_to_raw(1.0)
                else:
                    gain = 1.0
                offset = 0
                try:
                    sample_pts = meas_data["measurements"][component][channel]
                    x = np.empty(len(sample_pts))
                    y = np.empty(len(sample_pts))
                    for i, point in enumerate(sample_pts):
                        x[i] = point["shepherd_raw"]
                        y[i] = point["reference_si"]
                    result = stats.linregress(x, y)
                    offset = float(result.intercept)
                    gain = float(result.slope)
                    rval = result.rvalue  # test quality of regression
                except KeyError:
                    logger.error(
                        f"data not found -> '{component}-{channel}' replaced with default values (gain={gain})"
                    )
                except ValueError as e:
                    logger.error(
                        f"data faulty -> '{component}-{channel}' replaced with default values (gain={gain}) [{e}]"
                    )

                if ("rval" in locals()) and (rval < 0.999):
                    logger.warning(
                        f"Calibration may be faulty -> Correlation coefficient (rvalue) = {rval:.6f} is too low for {component}-{channel}"
                    )
                cal_dict[component][channel]["gain"] = gain
                cal_dict[component][channel]["offset"] = offset
        return cls(cal_dict)

    def convert_raw_to_value(
        self, component: str, channel: str, raw: int
    ) -> float:
        offset = self.data[component][channel]["offset"]
        gain = self.data[component][channel]["gain"]
        raw_max = (
            cal_def.RAW_MAX_DAC if "dac" in channel else cal_def.RAW_MAX_ADC
        )
        raw = min(max(raw, 0), raw_max)
        return max(float(raw) * gain + offset, 0.0)

    def convert_value_to_raw(
        self, component: str, channel: str, value: float
    ) -> int:
        offset = self.data[component][channel]["offset"]
        gain = self.data[component][channel]["gain"]
        raw_max = (
            cal_def.RAW_MAX_DAC if "dac" in channel else cal_def.RAW_MAX_ADC
        )
        return min(max(int((value - offset) / gain), 0), raw_max)

    def to_bytestr(self):
        """Serializes calibration data to byte string.

        Used to prepare data for writing it to EEPROM.

        Returns:
            Byte string representation of calibration values.
        """
        flattened = []
        for component in cal_component_list:
            for channel in cal_channel_list:
                for parameter in cal_parameter_list:
                    flattened.append(self.data[component][channel][parameter])
        val_count = (
            len(cal_component_list)
            * len(cal_channel_list)
            * len(cal_parameter_list)
        )
        return struct.pack(">" + val_count * "d", *flattened)

    def export_for_sysfs(self, component: str) -> dict:
        if component not in cal_component_list:
            raise ValueError(
                f"[Cal] change to unknown component (={component}) detected"
            )
        comp_data = self.data[component]
        cal_set = {
            # ADC is handled in nA (nano-ampere), gain is shifted by 8 bit [scaling according to commons.h]
            "adc_current_gain": round(
                1e9 * (2**8) * comp_data["adc_current"]["gain"]
            ),
            "adc_current_offset": round(
                1e9 * (2**0) * comp_data["adc_current"]["offset"]
            ),
            # ADC is handled in uV (micro-volt), gain is shifted by 8 bit [scaling according to commons.h]
            "adc_voltage_gain": round(
                1e6 * (2**8) * comp_data["adc_voltage"]["gain"]
            ),
            "adc_voltage_offset": round(
                1e6 * (2**0) * comp_data["adc_voltage"]["offset"]
            ),
            # DAC is handled in uV (micro-volt), gain is shifted by 20 bit
            "dac_voltage_gain": round(
                (2**20) / (1e6 * comp_data["dac_voltage_b"]["gain"])
            ),
            "dac_voltage_offset": round(
                1e6 * (2**0) * comp_data["dac_voltage_b"]["offset"]
            ),
        }

        for key, value in cal_set.items():
            # TODO: is exception more useful? -> raise ValueError
            if ("gain" in key) and not (0 <= value < 2**32):
                logger.warning(
                    f"Number (={value}) exceeds uint32-container, in CalibrationData.export_for_sysfs()"
                )
                cal_set[key] = min(max(value, 0), 2**32 - 1)
            if ("offset" in key) and not (-(2**31) <= value < 2**31):
                logger.warning(
                    f"Number (={value}) exceeds int32-container, in CalibrationData.export_for_sysfs()"
                )
                cal_set[key] = min(max(value, -(2**31)), 2**31 - 1)
        return cal_set
