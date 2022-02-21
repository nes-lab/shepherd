import pytest
import subprocess
import time
from pathlib import Path
import yaml

from shepherd import sysfs_interface, ShepherdIO, VirtualSourceData, VirtualHarvesterData
from shepherd.calibration import CalibrationData
from shepherd.virtual_source_data import flatten_dict_list


@pytest.fixture
def virtsource_settings():
    here = Path(__file__).absolute()
    name = "example_config_virtsource.yml"
    file_path = here.parent / name
    with open(file_path, "r") as config_data:
        vs_dict = yaml.safe_load(config_data)["virtsource"]

    vs_set = VirtualSourceData(vs_dict)
    vs_list = vs_set.export_for_sysfs()
    return vs_list


@pytest.fixture
def harvester_settings():
    here = Path(__file__).absolute()
    name = "example_config_harvester.yml"
    file_path = here.parent / name
    with open(file_path, "r") as config_data:
        hrv_dict = yaml.safe_load(config_data)["parameters"]["harvester"]

    hrv_set = VirtualHarvesterData(hrv_dict)
    hrv_list = hrv_set.export_for_sysfs()
    return hrv_list


@pytest.fixture()
def shepherd_running(shepherd_up):
    sysfs_interface.set_start()
    sysfs_interface.wait_for_state("running", 5)


@pytest.fixture()
def calibration_settings():
    cal = CalibrationData.from_default()
    return cal.export_for_sysfs("emulator")


@pytest.mark.hardware
@pytest.mark.parametrize("attr", sysfs_interface.attribs)
def test_getters(shepherd_up, attr):
    method_to_call = getattr(sysfs_interface, f"get_{ attr }")
    assert method_to_call() is not None


@pytest.mark.hardware
@pytest.mark.parametrize("attr", sysfs_interface.attribs)
def test_getters_fail(shepherd_down, attr):
    method_to_call = getattr(sysfs_interface, f"get_{ attr }")
    with pytest.raises(FileNotFoundError):
        method_to_call()


@pytest.mark.hardware
def test_start(shepherd_up):
    sysfs_interface.set_start()
    time.sleep(5)
    assert sysfs_interface.get_state() == "running"
    with pytest.raises(sysfs_interface.SysfsInterfaceException):
        sysfs_interface.set_start()


@pytest.mark.hardware
def test_wait_for_state(shepherd_up):
    sysfs_interface.set_start()
    assert sysfs_interface.wait_for_state("running", 3) < 3
    sysfs_interface.set_stop()
    assert sysfs_interface.wait_for_state("idle", 3) < 3


@pytest.mark.hardware
def test_start_delayed(shepherd_up):
    start_time = int(time.time() + 5)
    sysfs_interface.set_start(start_time)

    sysfs_interface.wait_for_state("armed", 1)
    with pytest.raises(sysfs_interface.SysfsInterfaceException):
        sysfs_interface.wait_for_state("running", 3)

    sysfs_interface.wait_for_state("running", 3)

    with pytest.raises(sysfs_interface.SysfsInterfaceException):
        sysfs_interface.set_start()


@pytest.mark.parametrize("mode", ["harvester", "emulator"])
def test_set_mode(shepherd_up, mode):
    sysfs_interface.write_mode(mode)
    assert sysfs_interface.get_mode() == mode


# TODO: is this not tested?
def test_initial_mode(shepherd_up):
    # NOTE: initial config is set in main() of pru0
    assert sysfs_interface.get_mode() == "harvester"


@pytest.mark.hardware
def test_set_mode_fail_offline(shepherd_running):
    with pytest.raises(sysfs_interface.SysfsInterfaceException):
        sysfs_interface.write_mode("harvester")


@pytest.mark.hardware
def test_set_mode_fail_invalid(shepherd_up):
    with pytest.raises(sysfs_interface.SysfsInterfaceException):
        sysfs_interface.write_mode("invalidmode")


@pytest.mark.parametrize("value", [0, 0.1, 3.2])
def test_dac_aux_voltage(shepherd_up, value):
    cal_set = CalibrationData.from_default()
    msb_threshold = cal_set.convert_raw_to_value("emulator", "dac_voltage_b", 2)
    sysfs_interface.write_dac_aux_voltage(cal_set, value)
    assert abs(sysfs_interface.read_dac_aux_voltage(cal_set) - value) <= msb_threshold


@pytest.mark.parametrize("value", [0, 100, 16000])
def test_dac_aux_voltage_raw(shepherd_up, value):
    sysfs_interface.write_dac_aux_voltage_raw(value)
    assert sysfs_interface.read_dac_aux_voltage_raw() == value


# TODO: is this not tested?
def test_initial_aux_voltage(shepherd_up):
    # NOTE: initial config is set in main() of pru0
    assert sysfs_interface.read_dac_aux_voltage_raw() == 0


@pytest.mark.hardware
def test_calibration_settings(shepherd_up, calibration_settings):
    sysfs_interface.write_calibration_settings(calibration_settings)
    assert sysfs_interface.read_calibration_settings() == calibration_settings


@pytest.mark.hardware
def test_initial_calibration_settings(shepherd_up, calibration_settings):
    # NOTE: initial config is in common_inits.h of kernel-module
    calibration_settings["adc_current_gain"] = 255
    calibration_settings["adc_current_offset"] = -1
    calibration_settings["adc_voltage_gain"] = 254
    calibration_settings["adc_voltage_offset"] = -2
    calibration_settings["dac_voltage_gain"] = 253
    calibration_settings["dac_voltage_offset"] = -3
    assert sysfs_interface.read_calibration_settings() == calibration_settings


@pytest.mark.hardware
def test_initial_harvester_settings(shepherd_up, harvester_settings):
    sysfs_interface.write_virtual_harvester_settings(harvester_settings)
    assert sysfs_interface.read_virtual_harvester_settings() == harvester_settings


@pytest.mark.hardware
def test_initial_harvester_settings(shepherd_up):
    hrv_list = [0] + list(range(200, 211))
    assert sysfs_interface.read_virtual_harvester_settings() == hrv_list


@pytest.mark.hardware
def test_virtsource_settings(shepherd_up, virtsource_settings):
    sysfs_interface.write_virtual_converter_settings(virtsource_settings)
    values_1d = flatten_dict_list(virtsource_settings)
    assert sysfs_interface.read_virtual_converter_settings() == values_1d


@pytest.mark.hardware
def test_initial_virtsource_settings(shepherd_up):
    # NOTE: initial config is set in main() of pru0
    vsource_settings = [
        list(range(100, 124)),
        list(range(12 * 12)),
        list(range(12))
    ]
    values_1d = flatten_dict_list(vsource_settings)
    assert sysfs_interface.read_virtual_converter_settings() == values_1d
