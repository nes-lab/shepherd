import ctypes as ct
from collections.abc import Sequence

from shepherd_core import CalibrationEmulator
from shepherd_core.data_models.content.virtual_source_config import ConverterPRUConfig
from shepherd_core.data_models.content.virtual_storage_config import StoragePRUConfig
from shepherd_core.logger import log

from ._virtual_pru import virtual_pru
from .data_types import LUT_INP
from .data_types import LUT_OUT
from .data_types import LUT_STORAGE_TYPE
from .data_types import CalibrationConfig
from .data_types import ConverterConfig
from .data_types import StorageConfig


class PruCalibration:
    """part of calibration.h."""

    def __init__(self, cal_emu: CalibrationEmulator | None = None) -> None:
        self.cal = cal_emu or CalibrationEmulator()


def flatten_list(dl: Sequence) -> list:
    """Small helper FN to convert (multi-dimensional) lists to 1D list

    Args:
        dl: (multi-dimensional) lists
    Returns:
        1D list
    """
    if isinstance(dl, Sequence):
        if len(dl) < 1:
            return [*dl]
        if len(dl) == 1:
            if isinstance(dl[0], Sequence):
                return flatten_list(dl[0])
            return [*dl]
        if isinstance(dl[0], Sequence):
            return flatten_list(dl[0]) + flatten_list(dl[1:])
        return [dl[0], *flatten_list(dl[1:])]
    return [dl]


def calc_current(power_W: float, voltage_V: float) -> float:
    p_fW_n4 = int(power_W * 1e15 * 2**4)
    v_uV = int(voltage_V * 1e6)
    return virtual_pru.calc_current_nA_n4(p_fW_n4, v_uV) / 1e9 / 2**4


class PruConverterModel:
    def __init__(
        self, cfg: ConverterPRUConfig, cal: PruCalibration, storage_cfg: StoragePRUConfig
    ) -> None:
        self.pru_cfg = cfg
        cnv_dict = cfg.model_dump()
        cnv_dict["LUT_inp_efficiency_n8"] = LUT_INP(
            *flatten_list(cnv_dict["LUT_inp_efficiency_n8"])
        )
        cnv_dict["LUT_out_inv_efficiency_n4"] = LUT_OUT(
            *flatten_list(cnv_dict["LUT_out_inv_efficiency_n4"])
        )
        self.cnv_cfg = ConverterConfig(**cnv_dict)
        self.cal_cfg = CalibrationConfig(**cal.cal.export_for_sysfs())
        store_dict = storage_cfg.model_dump()
        for item in ["LuT_VOC_uV_n8", "LuT_RSeries_kOhm_n32"]:
            store_dict[item] = LUT_STORAGE_TYPE(*flatten_list(store_dict[item]))
        self.store_cfg = StorageConfig(**store_dict)

        log.info("This is the PRU-C-CNV-Model.")
        log.info(cfg.model_dump())
        log.info(cal.cal.export_for_sysfs())
        self.pru = virtual_pru
        self.pru.set_calibration_config(ct.byref(self.cal_cfg))
        self.pru.set_storage_config(ct.byref(self.store_cfg))
        self.pru.set_converter_config(ct.byref(self.cnv_cfg))
        self.pru.calibration_initialize()
        self.pru.converter_initialize()  # does also .storage_initialize()

    def calc_inp_power(self, input_voltage_uV: float, input_current_nA: float) -> int:
        self.pru.converter_calc_inp_power(int(input_voltage_uV), int(input_current_nA))
        return self.pru.get_P_input_fW()

    def calc_out_power(self, current_adc_raw: int) -> int:
        self.pru.converter_calc_out_power(current_adc_raw)
        return self.pru.get_P_output_fW()

    def update_cap_storage(self) -> int:
        self.pru.converter_update_storage()
        return self.pru.get_V_intermediate_uV()

    def update_states_and_output(self) -> int:
        return self.pru.converter_update_states_and_output()

    def get_input_efficiency(self, voltage_uV: float, current_nA: float) -> float:
        raise NotImplementedError

    def get_output_inv_efficiency(self, current_nA: float) -> float:
        raise NotImplementedError

    def set_P_input_fW(self, value: float) -> None:
        self.pru.set_P_input_fW(int(value))

    def set_P_output_fW(self, value: float) -> None:
        self.pru.set_P_output_fW(int(value))

    def set_V_intermediate_uV(self, value: float) -> None:
        self.pru.set_V_intermediate_uV(int(value))

    def get_P_input_fW(self) -> int:
        return self.pru.get_P_input_fW()

    def get_P_output_fW(self) -> int:
        return self.pru.get_P_output_fW()

    def get_V_intermediate_uV(self) -> int:
        return self.pru.get_V_intermediate_uV()

    def get_V_intermediate_raw(self) -> int:
        return self.pru.get_V_intermediate_raw()

    def get_V_output_uV(self) -> int:
        return self.pru.get_V_output_uV()

    def get_power_good(self) -> int:
        # TODO: vsource_power_good_trigger_for_pru1 is also set
        return self.pru.get_vsource_power_good_pin_values

    def get_I_mid_out_nA(self) -> float:
        return self.pru.get_I_mid_out_nA()

    def get_state_log_intermediate(self) -> bool:
        return bool(self.pru.get_state_log_intermediate())

    def get_state_log_gpio(self) -> bool:
        return bool(self.pru.get_vsource_skip_gpio_logging())

    def vsrc_iterate_sampling(
        self, V_inp_uV: int = 0, I_inp_nA: int = 0, I_out_raw: int = 0
    ) -> int:
        return self.pru.vsrc_iterate_sampling(int(V_inp_uV), int(I_inp_nA), int(I_out_raw))
