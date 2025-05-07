import time
from pathlib import Path

import pytest
from shepherd_core import CalibrationCape
from shepherd_core import CalibrationEmulator
from shepherd_core.data_models import EnergyDType
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
    return ConverterPRUConfig.from_vsrc(
        data=src_cfg, dtype_in=EnergyDType.ivsample, log_intermediate_node=False
    )


@pytest.fixture
def hrv_cfg() -> HarvesterPRUConfig:
    path = Path(__file__).parent / "_test_config_harvest.yaml"
    hrv_cfg = HarvestTask.from_file(path.as_posix())
    return HarvesterPRUConfig.from_vhrv(hrv_cfg.virtual_harvester)


@pytest.fixture
def _shepherd_running(_shepherd_up: None) -> None:
    sysfs_interface.set_start()
    sysfs_interface.wait_for_state("running", 5)


@pytest.fixture
def cal4sysfs() -> dict:
    cal = CalibrationCape()
    return cal.emulator.export_for_sysfs()


@pytest.mark.parametrize("attr", sysfs_interface.attribs)
@pytest.mark.usefixtures("_shepherd_up")
def test_getters(attr: str) -> None:
    sysfs_interface.check_sys_access()
    method_to_call = getattr(sysfs_interface, f"get_{attr}")
    assert method_to_call() is not None


@pytest.mark.parametrize("attr", sysfs_interface.attribs)
@pytest.mark.usefixtures("_shepherd_down")
def test_getters_fail(attr: str) -> None:
    method_to_call = getattr(sysfs_interface, f"get_{attr}")
    with pytest.raises(FileNotFoundError):
        method_to_call()


@pytest.mark.hardware
@pytest.mark.usefixtures("_shepherd_up")
def test_start() -> None:
    sysfs_interface.check_sys_access()
    sysfs_interface.set_start()
    time.sleep(5)
    assert sysfs_interface.get_state() == "running"
    with pytest.raises(sysfs_interface.SysfsInterfaceError):
        sysfs_interface.set_start()


@pytest.mark.hardware
@pytest.mark.usefixtures("_shepherd_up")
def test_wait_for_state() -> None:
    sysfs_interface.set_start()
    assert sysfs_interface.wait_for_state("running", 3) < 3
    sysfs_interface.set_stop()
    assert sysfs_interface.wait_for_state("idle", 3) < 3


@pytest.mark.hardware
@pytest.mark.usefixtures("_shepherd_up")
def test_start_delayed() -> None:
    start_time = int(time.time() + 5)
    sysfs_interface.set_start(start_time)

    sysfs_interface.wait_for_state("armed", 1)
    with pytest.raises(sysfs_interface.SysfsInterfaceError):
        sysfs_interface.wait_for_state("running", 3)

    sysfs_interface.wait_for_state("running", 3)

    with pytest.raises(sysfs_interface.SysfsInterfaceError):
        sysfs_interface.set_start()


@pytest.mark.parametrize("mode", ["harvester", "emulator"])
@pytest.mark.usefixtures("_shepherd_up")
def test_set_mode(mode: str) -> None:
    sysfs_interface.write_mode(mode)
    assert sysfs_interface.get_mode() == mode


@pytest.mark.usefixtures("_shepherd_up")
def test_initial_mode() -> None:
    # NOTE: initial config is set in main() of pru0
    assert sysfs_interface.get_mode() == "none"


@pytest.mark.hardware
@pytest.mark.usefixtures("_shepherd_running")
def test_set_mode_fail_offline() -> None:
    with pytest.raises(sysfs_interface.SysfsInterfaceError):
        sysfs_interface.write_mode("harvester")


@pytest.mark.usefixtures("_shepherd_up")
def test_set_mode_fail_invalid() -> None:
    with pytest.raises(sysfs_interface.SysfsInterfaceError):
        sysfs_interface.write_mode("invalidmode")


@pytest.mark.parametrize("value", [0, 0.1, 3.2])
@pytest.mark.usefixtures("_shepherd_up")
def test_dac_aux_voltage(value: float) -> None:
    cal_emu = CalibrationEmulator()
    msb_threshold = cal_emu.dac_V_A.raw_to_si(2)
    sysfs_interface.write_dac_aux_voltage(value, cal_emu)
    assert abs(sysfs_interface.read_dac_aux_voltage(cal_emu) - value) <= msb_threshold


@pytest.mark.parametrize("value", [0, 100, 16000])
@pytest.mark.usefixtures("_shepherd_up")
def test_dac_aux_voltage_raw(value: int) -> None:
    sysfs_interface.write_dac_aux_voltage_raw(value)
    assert sysfs_interface.read_dac_aux_voltage_raw() == value


@pytest.mark.usefixtures("_shepherd_up")
def test_initial_aux_voltage() -> None:
    # NOTE: initial config is set in main() of pru0
    assert sysfs_interface.read_dac_aux_voltage_raw() == 0


@pytest.mark.usefixtures("_shepherd_up")
def test_calibration_settings(cal4sysfs: dict) -> None:
    sysfs_interface.write_calibration_settings(cal4sysfs)
    assert sysfs_interface.read_calibration_settings() == cal4sysfs


@pytest.mark.hardware
@pytest.mark.usefixtures("_shepherd_up")
def test_initial_calibration_settings(cal4sysfs: dict) -> None:
    # NOTE: initial config is in common_inits.h of kernel-module
    cal4sysfs["adc_current_gain"] = 255
    cal4sysfs["adc_current_offset"] = -1
    cal4sysfs["adc_voltage_gain"] = 254
    cal4sysfs["adc_voltage_offset"] = -2
    cal4sysfs["dac_voltage_gain"] = 253
    cal4sysfs["dac_voltage_offset"] = -3
    assert sysfs_interface.read_calibration_settings() == cal4sysfs


@pytest.mark.hardware
@pytest.mark.usefixtures("_shepherd_up")
def test_initial_harvester_settings() -> None:
    hrv_list = [0, *list(range(200, 211))]
    assert sysfs_interface.read_virtual_harvester_settings() == hrv_list


@pytest.mark.hardware  # TODO: could also run with mock_hardware, but triggers pydantic-error
@pytest.mark.usefixtures("_shepherd_up")
def test_writing_harvester_settings(
    hrv_cfg: HarvesterPRUConfig,
) -> None:
    sysfs_interface.write_virtual_harvester_settings(hrv_cfg)
    assert sysfs_interface.read_virtual_harvester_settings() == list(
        hrv_cfg.model_dump().values(),
    )


@pytest.mark.hardware
@pytest.mark.usefixtures("_shepherd_up")
def test_initial_virtsource_settings() -> None:
    # NOTE: initial config is set in main() of pru0
    vsource_settings = [
        list(range(100, 124)),
        list(range(12 * 12)),
        list(range(12)),
    ]
    values_1d = flatten_list(vsource_settings)
    assert sysfs_interface.read_virtual_converter_settings() == values_1d


@pytest.mark.usefixtures("_shepherd_up")
def test_writing_virtsource_settings(
    cnv_cfg: ConverterPRUConfig,
) -> None:
    sysfs_interface.write_virtual_converter_settings(cnv_cfg)
    values_1d = flatten_list(list(cnv_cfg.model_dump().values()))
    assert sysfs_interface.read_virtual_converter_settings() == values_1d
