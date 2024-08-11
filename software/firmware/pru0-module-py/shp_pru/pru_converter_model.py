import ctypes as ct
from pathlib import Path

from shepherd_core.data_models.content.virtual_source import ConverterPRUConfig
from shepherd_core.vsource import PruCalibration
from shepherd_core import logger

class CalibrationConfig(ct.Structure):
    _pack_ = 1
    _fields_ = [("adc_current_factor_nA_n8", ct.c_uint32),
                ("adc_current_offset_nA", ct.c_int32),
                ("adc_voltage_factor_uV_n8", ct.c_uint32),
                ("adc_voltage_offset_uV", ct.c_int32),
                ("dac_voltage_inv_factor_uV_n20", ct.c_uint32),
                ("dac_voltage_offset_uV", ct.c_int32),
            ]


LUT_SIZE: int = 12


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
        ("LUT_inp_efficiency_n8", ct.c_uint8 * LUT_SIZE * LUT_SIZE),
        ("LUT_out_inv_efficiency_n4", ct.c_uint32 * LUT_SIZE),
]


path = Path(__file__).parent / "virtual_xyz.so"
pru = ct.CDLL(path.as_posix())

pru.calibration_initialize.argtypes = [ct.POINTER(CalibrationConfig)]
pru.calibration_initialize.restype = None

pru.converter_initialize.argtypes = [ct.POINTER(ConverterConfig)]
pru.converter_initialize.restype = None

pru.converter_calc_inp_power.argtypes = [ct.c_uint32, ct.c_uint32]
pru.converter_calc_inp_power.restype = None

pru.converter_calc_out_power.argtypes = [ct.c_uint32]
pru.converter_calc_out_power.restype = None

pru.converter_update_cap_storage.argtypes = None
pru.converter_update_cap_storage.restype = None

#pru.converter_update_states_and_output.argtypes = [None] # TODO
pru.converter_update_states_and_output.restype = ct.c_uint32

pru.set_P_input_fW.argtypes = [ct.c_uint32]
pru.set_P_input_fW.restype = None

pru.set_P_output_fW.argtypes = [ct.c_uint32]
pru.set_P_output_fW.restype = None

pru.set_V_intermediate_uV.argtypes = [ct.c_uint32]
pru.set_V_intermediate_uV.restype = None

pru.get_P_input_fW.argtypes = None
pru.get_P_input_fW.restype = ct.c_uint64

pru.get_P_output_fW.argtypes = None
pru.get_P_output_fW.restype = ct.c_uint64

pru.get_V_intermediate_uV.argtypes = None
pru.get_V_intermediate_uV.restype = ct.c_uint32

pru.get_V_intermediate_raw.argtypes = None
pru.get_V_intermediate_raw.restype = ct.c_uint32

pru.get_I_mid_out_nA.argtypes = None
pru.get_I_mid_out_nA.restype = ct.c_uint32

pru.get_state_log_intermediate.argtypes = None
pru.get_state_log_intermediate.restype = ct.c_uint32  # bool_ft

pru.set_batok_pin.argtypes = None
pru.set_batok_pin.restype = None


class PruConverterModel:
    def __init__(self, cfg: ConverterPRUConfig, cal: PruCalibration) -> None:
        self.cnv_cfg = ConverterConfig(**cfg.model_dump())
        self.cal_cfg = CalibrationConfig(**cal.cal.model_dump())
        logger.info("This is the PRU-C-Code-Model.")
        logger.info(cfg.model_dump())
        pru.calibration_initialize(ct.byref(self.cal_cfg))
        pru.converter_initialize(ct.byref(self.cnv_cfg))

    def calc_inp_power(self, input_voltage_uV: float, input_current_nA: float) -> int:
        pru.converter_calc_inp_power(input_voltage_uV, input_current_nA)
        return pru.get_P_input_fW()

    def calc_out_power(self, current_adc_raw: int) -> int:
        pru.converter_calc_out_power(current_adc_raw)
        return pru.get_P_output_fW()

    def update_cap_storage(self) -> int:
        pru.update_cap_storage()
        return pru.get_V_intermediate_uV()

    def update_states_and_output(self) -> int:
        return pru.update_states_and_output()  # TODO

    def get_input_efficiency(self, voltage_uV: float, current_nA: float) -> float:
        pass

    def get_output_inv_efficiency(self, current_nA: float) -> float:
        pass


    def set_P_input_fW(self, value: float) -> None:
        pass

    def set_P_output_fW(self, value: float) -> None:
        pass

    def set_V_intermediate_uV(self, value: float) -> None:
        pass

    def get_P_input_fW(self) -> int:
        pass

    def get_P_output_fW(self) -> int:
        pass

    def get_V_intermediate_uV(self) -> int:
        pass

    def get_V_intermediate_raw(self) -> int:
        pass

    def get_power_good(self) -> bool:
        pass

    def get_I_mod_out_nA(self) -> float:
        pass

    def get_state_log_intermediate(self) -> bool:
        pass

    def get_state_log_gpio(self) -> bool:
        pass