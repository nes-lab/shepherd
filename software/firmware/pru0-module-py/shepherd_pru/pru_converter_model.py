import ctypes as ct

from shepherd_core import CalibrationEmulator
from shepherd_core import logger
from shepherd_core.data_models.content.virtual_source import ConverterPRUConfig

from ._virtual_pru import virtual_pru
from .data_types import LUT_INP
from .data_types import LUT_OUT
from .data_types import CalibrationConfig
from .data_types import ConverterConfig
from .data_types import SharedMemLight


class PruCalibration:
    """part of calibration.h."""

    def __init__(self, cal_emu: CalibrationEmulator | None = None) -> None:
        self.cal = cal_emu if cal_emu else CalibrationEmulator()


def flatten_list(dl: list) -> list:
    """Small helper FN to convert (multi-dimensional) lists to 1D list

    Args:
        dl: (multi-dimensional) lists
    Returns:
        1D list
    """
    if isinstance(dl, list):
        if len(dl) < 1:
            return dl
        if len(dl) == 1:
            if isinstance(dl[0], list):
                return flatten_list(dl[0])
            return dl
        if isinstance(dl[0], list):
            return flatten_list(dl[0]) + flatten_list(dl[1:])
        return [dl[0], *flatten_list(dl[1:])]
    return [dl]


class PruConverterModel:
    def __init__(self, cfg: ConverterPRUConfig, cal: PruCalibration) -> None:
        cnv_dict = cfg.model_dump()
        cnv_dict["LUT_inp_efficiency_n8"] = LUT_INP(
            *flatten_list(cnv_dict["LUT_inp_efficiency_n8"])
        )
        cnv_dict["LUT_out_inv_efficiency_n4"] = LUT_OUT(
            *flatten_list(cnv_dict["LUT_out_inv_efficiency_n4"])
        )
        self.cnv_cfg = ConverterConfig(**cnv_dict)
        self.cal_cfg = CalibrationConfig(**cal.cal.export_for_sysfs())
        self.shared_mem = SharedMemLight()
        logger.info("This is the PRU-C-CNV-Model.")
        logger.info(cfg.model_dump())
        logger.info(cal.cal.export_for_sysfs())
        self.pru = virtual_pru
        self.pru.calibration_initialize(ct.byref(self.cal_cfg))
        self.pru.converter_initialize(ct.byref(self.cnv_cfg))

    def calc_inp_power(self, input_voltage_uV: float, input_current_nA: float) -> int:
        self.pru.converter_calc_inp_power(int(input_voltage_uV), int(input_current_nA))
        return self.pru.get_P_input_fW()

    def calc_out_power(self, current_adc_raw: int) -> int:
        self.pru.converter_calc_out_power(current_adc_raw)
        return self.pru.get_P_output_fW()

    def update_cap_storage(self) -> int:
        self.pru.converter_update_cap_storage()
        return self.pru.get_V_intermediate_uV()

    def update_states_and_output(self) -> int:
        return self.pru.converter_update_states_and_output(ct.byref(self.shared_mem))

    def get_input_efficiency(self, voltage_uV: float, current_nA: float) -> float:
        raise NotImplementedError

    def get_output_inv_efficiency(self, current_nA: float) -> float:
        raise NotImplementedError

    def set_P_input_fW(self, value: float) -> None:
        self.pru.set_P_input_fW(int(value))

    def set_P_output_fW(self, value: float) -> None:
        self.pru.set_P_output_fW(int(value))

    def set_V_intermediate_uV(self, value: float) -> None:
        self.set_V_intermediate_uV(int(value))

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
        return self.shared_mem.vsource_batok_pin_value  # TODO: this has now power_high & _low

    def get_I_mid_out_nA(self) -> float:
        return self.pru.get_I_mid_out_nA()

    def get_state_log_intermediate(self) -> bool:
        return bool(self.pru.get_state_log_intermediate())

    def get_state_log_gpio(self) -> bool:
        return bool(self.shared_mem.vsource_skip_gpio_logging)

    def vsrc_iterate_sampling(
        self, V_inp_uV: int = 0, I_inp_nA: int = 0, I_out_raw: int = 0
    ) -> int:
        return self.pru.vsrc_iterate_sampling(int(V_inp_uV), int(I_inp_nA), int(I_out_raw))
