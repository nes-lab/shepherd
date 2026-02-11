import pytest
from shepherd_core.data_models import CalibrationEmulator
from shepherd_core.data_models import EnergyDType
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models.content.virtual_source_config import ConverterPRUConfig
from shepherd_core.data_models.content.virtual_storage_config import StoragePRUConfig
from shepherd_pru.pru_converter_model import PruCalibration
from shepherd_pru.pru_converter_model import PruConverterModel
from shepherd_pru.pru_converter_model import calc_current

val_u32a = [0, 1, 2, 6, 8, 255, 65000]
val_u32b = [2**16 - 1, 2**16, 2**16 + 1]
val_u32c = [2**31 - 1, 2**31, 2**31 + 1]
val_u32d = [2**32 - 1]
val_u32 = [*val_u32a, *val_u32b, *val_u32c, *val_u32d]


@pytest.fixture
def cnv() -> PruConverterModel:
    dtype_in = EnergyDType.ivsample
    cal_emu = CalibrationEmulator()
    cal_pru: PruCalibration = PruCalibration(cal_emu)

    cfg_src = VirtualSourceConfig(name="BQ25504")
    cnv_config = ConverterPRUConfig.from_vsrc(data=cfg_src, dtype_in=dtype_in)
    cfg_store = StoragePRUConfig.from_vstorage(cfg_src.storage)
    return PruConverterModel(cnv_config, cal_pru, cfg_store)


@pytest.mark.parametrize("power_W", [0.001, 0.005, 0.010, 0.020, 0.050, 0.100])
@pytest.mark.parametrize("voltage_V", list(range(1, 16)))
def test_calc_current(power_W: float, voltage_V: float) -> None:
    current_pru = calc_current(power_W, voltage_V)
    current_base = power_W / voltage_V
    assert abs(current_pru / current_base - 1) < 0.02  # 2%


@pytest.mark.parametrize("val1", val_u32)
def test_set_P_input_fW(cnv: PruConverterModel, val1: int) -> None:
    assert cnv.get_P_input_fW() == 0
    cnv.set_P_input_fW(val1)
    assert cnv.get_P_input_fW() == val1


@pytest.mark.parametrize("val1", val_u32)
def test_set_P_output_fW(cnv: PruConverterModel, val1: int) -> None:
    assert cnv.get_P_output_fW() == 0
    cnv.set_P_output_fW(val1)
    assert cnv.get_P_output_fW() == val1


@pytest.mark.parametrize("val1", val_u32)
def test_set_V_intermediate_uV(cnv: PruConverterModel, val1: int) -> None:
    assert cnv.get_V_intermediate_uV() == cnv.pru.get_V_OC_uV()
    cnv.set_V_intermediate_uV(val1)
    assert cnv.get_V_intermediate_uV() == val1


def test_get_state_log_intermediate(cnv: PruConverterModel) -> None:
    assert not cnv.get_state_log_intermediate()
    # TODO: cnv.pru_cfg.logging_intermediate_node_is_enabled()
