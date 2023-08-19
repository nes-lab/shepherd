import time
from pathlib import Path

import pytest
from shepherd_core import CalibrationCape
from shepherd_core import CalibrationEmulator
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models.content.virtual_harvester import HarvesterPRUConfig
from shepherd_core.data_models.content.virtual_source import ConverterPRUConfig
from shepherd_core.data_models.task import HarvestTask
from shepherd_sheep import flatten_list
from shepherd_sheep import sysfs_interface


@pytest.fixture
def cnv_cfg() -> ConverterPRUConfig:
    here = Path(__file__).resolve()
    name = "_test_config_virtsource.yaml"
    path = here.parent / name
    src_cfg = VirtualSourceConfig.from_file(path)
    cnv_pru = ConverterPRUConfig.from_vsrc(src_cfg, log_intermediate_node=False)
    return cnv_pru


@pytest.fixture
def hrv_cfg() -> HarvesterPRUConfig:
    here = Path(__file__).resolve()
    name = "_test_config_harvest.yaml"
    path = here.parent / name
    hrv_cfg = HarvestTask.from_file(path)
    hrv_pru = HarvesterPRUConfig.from_vhrv(hrv_cfg.virtual_harvester)
    return hrv_pru


@pytest.fixture()
def shepherd_running(shepherd_up) -> None:
    sysfs_interface.set_start()
    sysfs_interface.wait_for_state("running", 5)


@pytest.fixture()
def cal4sysfs() -> dict:
    cal = CalibrationCape()
    return cal.emulator.export_for_sysfs()


@pytest.mark.parametrize("attr", sysfs_interface.attribs)
def test_getters(shepherd_up, attr) -> None:
    method_to_call = getattr(sysfs_interface, f"get_{ attr }")
    assert method_to_call() is not None


@pytest.mark.parametrize("attr", sysfs_interface.attribs)
def test_getters_fail(shepherd_down, attr) -> None:
    method_to_call = getattr(sysfs_interface, f"get_{ attr }")
    with pytest.raises(FileNotFoundError):
        method_to_call()


@pytest.mark.hardware
def test_start(shepherd_up) -> None:
    sysfs_interface.set_start()
    time.sleep(5)
    assert sysfs_interface.get_state() == "running"
    with pytest.raises(sysfs_interface.SysfsInterfaceException):
        sysfs_interface.set_start()


@pytest.mark.hardware
def test_wait_for_state(shepherd_up) -> None:
    sysfs_interface.set_start()
    assert sysfs_interface.wait_for_state("running", 3) < 3
    sysfs_interface.set_stop()
    assert sysfs_interface.wait_for_state("idle", 3) < 3


@pytest.mark.hardware
def test_start_delayed(shepherd_up) -> None:
    start_time = int(time.time() + 5)
    sysfs_interface.set_start(start_time)

    sysfs_interface.wait_for_state("armed", 1)
    with pytest.raises(sysfs_interface.SysfsInterfaceException):
        sysfs_interface.wait_for_state("running", 3)

    sysfs_interface.wait_for_state("running", 3)

    with pytest.raises(sysfs_interface.SysfsInterfaceException):
        sysfs_interface.set_start()


@pytest.mark.parametrize("mode", ["harvester", "emulator"])
def test_set_mode(shepherd_up, mode) -> None:
    sysfs_interface.write_mode(mode)
    assert sysfs_interface.get_mode() == mode


def test_initial_mode(shepherd_up) -> None:
    # NOTE: initial config is set in main() of pru0
    assert sysfs_interface.get_mode() == "harvester"


@pytest.mark.hardware
def test_set_mode_fail_offline(shepherd_running) -> None:
    with pytest.raises(sysfs_interface.SysfsInterfaceException):
        sysfs_interface.write_mode("harvester")


def test_set_mode_fail_invalid(shepherd_up):
    with pytest.raises(sysfs_interface.SysfsInterfaceException):
        sysfs_interface.write_mode("invalidmode")


@pytest.mark.parametrize("value", [0, 0.1, 3.2])
def test_dac_aux_voltage(shepherd_up, value):
    cal_emu = CalibrationEmulator()
    msb_threshold = cal_emu.dac_V_A.raw_to_si(2)
    sysfs_interface.write_dac_aux_voltage(value, cal_emu)
    assert abs(sysfs_interface.read_dac_aux_voltage(cal_emu) - value) <= msb_threshold


@pytest.mark.parametrize("value", [0, 100, 16000])
def test_dac_aux_voltage_raw(shepherd_up, value):
    sysfs_interface.write_dac_aux_voltage_raw(value)
    assert sysfs_interface.read_dac_aux_voltage_raw() == value


def test_initial_aux_voltage(shepherd_up):
    # NOTE: initial config is set in main() of pru0
    assert sysfs_interface.read_dac_aux_voltage_raw() == 0


def test_calibration_settings(shepherd_up, cal4sysfs: dict):
    sysfs_interface.write_calibration_settings(cal4sysfs)
    assert sysfs_interface.read_calibration_settings() == cal4sysfs


@pytest.mark.hardware
def test_initial_calibration_settings(shepherd_up, cal4sysfs):
    # NOTE: initial config is in common_inits.h of kernel-module
    cal4sysfs["adc_current_gain"] = 255
    cal4sysfs["adc_current_offset"] = -1
    cal4sysfs["adc_voltage_gain"] = 254
    cal4sysfs["adc_voltage_offset"] = -2
    cal4sysfs["dac_voltage_gain"] = 253
    cal4sysfs["dac_voltage_offset"] = -3
    assert sysfs_interface.read_calibration_settings() == cal4sysfs


@pytest.mark.hardware
def test_initial_harvester_settings(shepherd_up):
    hrv_list = [0] + list(range(200, 211))
    assert sysfs_interface.read_virtual_harvester_settings() == hrv_list


def test_writing_harvester_settings(shepherd_up, hrv_cfg):
    sysfs_interface.write_virtual_harvester_settings(hrv_cfg)
    assert sysfs_interface.read_virtual_harvester_settings() == list(
        hrv_cfg.model_dump().values(),
    )


@pytest.mark.hardware
def test_initial_virtsource_settings(shepherd_up):
    # NOTE: initial config is set in main() of pru0
    vsource_settings = [
        list(range(100, 124)),
        list(range(12 * 12)),
        list(range(12)),
    ]
    values_1d = flatten_list(vsource_settings)
    assert sysfs_interface.read_virtual_converter_settings() == values_1d


def test_writing_virtsource_settings(shepherd_up, cnv_cfg):
    sysfs_interface.write_virtual_converter_settings(cnv_cfg)
    values_1d = flatten_list(list(cnv_cfg.model_dump().values()))
    assert sysfs_interface.read_virtual_converter_settings() == values_1d
