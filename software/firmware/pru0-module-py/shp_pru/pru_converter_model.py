import ctypes as ct
from pathlib import Path

from shepherd_core import CalibrationEmulator
from shepherd_core import logger
from shepherd_core.data_models.content.virtual_source import ConverterPRUConfig

from .pru_harvester_model import HarvesterConfig


class CalibrationConfig(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("adc_current_factor_nA_n8", ct.c_uint32),
        ("adc_current_offset_nA", ct.c_int32),
        ("adc_voltage_factor_uV_n8", ct.c_uint32),
        ("adc_voltage_offset_uV", ct.c_int32),
        ("dac_voltage_inv_factor_uV_n20", ct.c_uint32),
        ("dac_voltage_offset_uV", ct.c_int32),
    ]


LUT_SIZE: int = 12
LUT_INP = ct.c_uint8 * (LUT_SIZE * LUT_SIZE)
LUT_OUT = ct.c_uint32 * LUT_SIZE


class ConverterConfig(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("converter_mode", ct.c_uint32),
        ("interval_startup_delay_drain_n", ct.c_uint32),
        ("V_input_max_uV", ct.c_uint32),
        ("I_input_max_nA", ct.c_uint32),
        ("V_input_drop_uV", ct.c_uint32),
        ("R_input_kOhm_n22", ct.c_uint32),
        ("Constant_us_per_nF_n28", ct.c_uint32),
        ("V_intermediate_init_uV", ct.c_uint32),
        ("I_intermediate_leak_nA", ct.c_uint32),
        ("V_enable_output_threshold_uV", ct.c_uint32),
        ("V_disable_output_threshold_uV", ct.c_uint32),
        ("dV_enable_output_uV", ct.c_uint32),
        ("interval_check_thresholds_n", ct.c_uint32),
        ("V_pwr_good_enable_threshold_uV", ct.c_uint32),
        ("V_pwr_good_disable_threshold_uV", ct.c_uint32),
        ("immediate_pwr_good_signal", ct.c_uint32),
        ("V_output_log_gpio_threshold_uV", ct.c_uint32),
        ("V_input_boost_threshold_uV", ct.c_uint32),
        ("V_intermediate_max_uV", ct.c_uint32),
        ("V_output_uV", ct.c_uint32),
        ("V_buck_drop_uV", ct.c_uint32),
        ("LUT_input_V_min_log2_uV", ct.c_uint32),
        ("LUT_input_I_min_log2_nA", ct.c_uint32),
        ("LUT_output_I_min_log2_nA", ct.c_uint32),
        ("LUT_inp_efficiency_n8", LUT_INP),
        ("LUT_out_inv_efficiency_n4", LUT_OUT),
    ]


class SharedMemLight(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("pre_stuff", ct.c_uint32 * 9),
        ("calibration_settings", CalibrationConfig),
        ("converter_settings", ConverterConfig),
        ("harvester_settings", HarvesterConfig),
        ("programmer_ctrl", ct.c_uint32 * 10),
        ("proto_msgs", ct.c_uint32 * (3 * 5)),
        ("sync_msgs", ct.c_uint32 * 6),
        ("timestamps", ct.c_uint64 * 2),
        ("mutex_x", ct.c_uint32 * 2),  # bool_ft
        ("gpio_pin_state", ct.c_uint32),
        ("gpio_edges", ct.c_uint32),  # Pointer
        ("sample_buffer", ct.c_uint32),  # Pointer
        ("analog_x", ct.c_uint32 * 4),
        ("trigger_x", ct.c_uint32 * 2),  # bool_ft
        ("vsource_batok_trigger_for_pru1", ct.c_uint32),  # bool_ft
        ("vsource_skip_gpio_logging", ct.c_uint32),  # bool_ft
        ("vsource_batok_pin_value", ct.c_uint32),  # bool_ft
    ]


def get_device() -> ct.CDLL:
    path = Path(__file__).parent / "virtual_xyz.so"
    fn_signatures = {
        "calibration_initialize": ([ct.POINTER(CalibrationConfig)], None),
        "converter_initialize": ([ct.POINTER(ConverterConfig)], None),
        "converter_calc_inp_power": ([ct.c_uint32, ct.c_uint32], None),
        "converter_calc_out_power": ([ct.c_uint32], None),
        "converter_update_cap_storage": (None, None),
        "converter_update_states_and_output": ([ct.POINTER(SharedMemLight)], ct.c_uint32),
        "set_P_input_fW": ([ct.c_uint32], None),
        "set_P_output_fW": ([ct.c_uint32], None),
        "set_V_intermediate_uV": ([ct.c_uint32], None),
        "get_P_input_fW": (None, ct.c_uint64),
        "get_P_output_fW": (None, ct.c_uint64),
        "get_V_intermediate_uV": (None, ct.c_uint32),
        "get_V_intermediate_raw": (None, ct.c_uint32),
        "get_I_mid_out_nA": (None, ct.c_uint32),
        "get_state_log_intermediate": (None, ct.c_uint32),  # bool_ft
        "set_batok_pin": (None, None),
        # private fn
        # "get_input_efficiency_n8": ([ct.c_uint32, ct.c_uint32], ct.c_uint32),
        # "get_output_inv_efficiency_n4": ([ct.c_uint32], ct.c_uint32),
    }
    pru = ct.CDLL(path.as_posix())
    for _fn, _sig in fn_signatures.items():
        pru[_fn].argtypes = _sig[0]
        pru[_fn].restype = _sig[1]
    return pru


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
        print(cnv_dict["LUT_inp_efficiency_n8"])
        print(cnv_dict["LUT_out_inv_efficiency_n4"])
        cnv_dict["LUT_inp_efficiency_n8"] = LUT_INP(
            *flatten_list(cnv_dict["LUT_inp_efficiency_n8"])
        )
        cnv_dict["LUT_out_inv_efficiency_n4"] = LUT_OUT(
            *flatten_list(cnv_dict["LUT_out_inv_efficiency_n4"])
        )
        self.cnv_cfg = ConverterConfig(**cnv_dict)
        self.cal_cfg = CalibrationConfig(**cal.cal.model_dump())
        self.shared_mem = SharedMemLight()
        logger.info("This is the PRU-C-Code-Model.")
        logger.info(cfg.model_dump())
        self.pru = get_device()
        self.pru.calibration_initialize(ct.byref(self.cal_cfg))
        self.pru.converter_initialize(ct.byref(self.cnv_cfg))

    def calc_inp_power(self, input_voltage_uV: float, input_current_nA: float) -> int:
        self.pru.converter_calc_inp_power(int(input_voltage_uV), int(input_current_nA))
        return int(self.pru.get_P_input_fW())

    def calc_out_power(self, current_adc_raw: int) -> int:
        self.pru.converter_calc_out_power(int(current_adc_raw))
        return self.pru.get_P_output_fW()

    def update_cap_storage(self) -> int:
        self.pru.converter_update_cap_storage()
        return self.pru.get_V_intermediate_uV()

    def update_states_and_output(self) -> int:
        return self.pru.converter_update_states_and_output(ct.byref(self.shared_mem))

    def get_input_efficiency(self, voltage_uV: float, current_nA: float) -> float:
        raise NotImplementedError
        # return self.pru.get_input_efficiency_n8(voltage_uV, current_nA) / (2**8)

    def get_output_inv_efficiency(self, current_nA: float) -> float:
        raise NotImplementedError
        # return self.pru.get_output_inv_efficiency_n4(current_nA) / (2**4)

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

    def get_power_good(self) -> bool:
        return bool(self.shared_mem.vsource_batok_pin_value)

    def get_I_mid_out_nA(self) -> float:
        return self.pru.get_I_mid_out_nA()

    def get_state_log_intermediate(self) -> bool:
        return self.pru.get_state_log_intermediate()

    def get_state_log_gpio(self) -> bool:
        return bool(self.shared_mem.vsource_skip_gpio_logging)
