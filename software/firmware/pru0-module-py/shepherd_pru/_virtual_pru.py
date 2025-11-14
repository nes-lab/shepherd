import ctypes as ct
from pathlib import Path

from .data_types import CalibrationConfig
from .data_types import ConverterConfig
from .data_types import HarvesterConfig
from .data_types import StorageConfig

bool_ft = ct.c_uint32
uint8_ft = ct.c_uint32


def get_device() -> ct.CDLL:
    path = Path(__file__).parent / "_shared_pru.so"
    fn_signatures = {
        # virtual_harvester.c ##############################
        "harvester_initialize": (None, None),
        "sample_ivcurve_harvester": ([ct.POINTER(ct.c_uint32), ct.POINTER(ct.c_uint32)], None),
        # calibration.c ##############################
        "calibration_initialize": (None, None),
        "cal_conv_adc_raw_to_nA": ([ct.c_uint32], ct.c_uint32),
        "cal_conv_adc_raw_to_uV": ([ct.c_uint32], ct.c_uint32),
        "cal_conv_uV_to_dac_raw": ([ct.c_uint32], ct.c_uint32),
        # virtual_storage.c ##############################
        "storage_initialize": (None, None),
        "get_V_OC_uV": (None, ct.c_uint32),
        "get_SoC_1_n30": (None, ct.c_uint32),
        "storage_update": ([ct.c_uint64, bool_ft], ct.c_uint32),
        # virtual_converter.c ##############################
        "converter_initialize": (None, None),
        "converter_calc_inp_power": ([ct.c_uint32, ct.c_uint32], None),
        "converter_calc_out_power": ([ct.c_uint32], None),
        "converter_update_storage": (None, None),
        "converter_update_states_and_output": (None, ct.c_uint32),
        "set_P_input_fW": ([ct.c_uint32], None),
        "set_P_output_fW": ([ct.c_uint32], None),
        "set_V_intermediate_uV": ([ct.c_uint32], None),
        "get_P_input_fW": (None, ct.c_uint64),
        "get_P_output_fW": (None, ct.c_uint64),
        "get_V_intermediate_uV": (None, ct.c_uint32),
        "get_V_intermediate_raw": (None, ct.c_uint32),
        "get_I_mid_out_nA": (None, ct.c_uint32),
        "get_V_output_uV": (None, ct.c_uint32),
        "get_state_log_intermediate": (None, bool_ft),
        "set_batok_pin": ([bool_ft], None),
        # pru_source.c (local vSource-helper-fn) #####
        "set_harvester_config": ([ct.POINTER(HarvesterConfig)], None),
        "set_storage_config": ([ct.POINTER(StorageConfig)], None),
        "set_calibration_config": ([ct.POINTER(CalibrationConfig)], None),
        "set_converter_config": ([ct.POINTER(ConverterConfig)], None),
        "get_vsource_batok_pin_value": (None, bool_ft),
        "get_vsource_skip_gpio_logging": (None, bool_ft),
        "vsrc_iterate_sampling": ([ct.c_uint32, ct.c_uint32, ct.c_uint32], ct.c_uint32),
        # math64_safe.c ##############################
        "mul32": ([ct.c_uint32, ct.c_uint32], ct.c_uint32),
        "mul64": ([ct.c_uint64, ct.c_uint64], ct.c_uint64),
        "add32": ([ct.c_uint32, ct.c_uint32], ct.c_uint32),
        "add64": ([ct.c_uint64, ct.c_uint64], ct.c_uint64),
        "sub32": ([ct.c_uint32, ct.c_uint32], ct.c_uint32),
        "sub64": ([ct.c_uint64, ct.c_uint64], ct.c_uint64),  # TODO: add new math fn + unittests
        "get_size_in_bits": ([ct.c_uint32], uint8_ft),
        "log2safe": ([ct.c_uint32], uint8_ft),
        "max_value": ([ct.c_uint32, ct.c_uint32], ct.c_uint32),
        "min_value": ([ct.c_uint32, ct.c_uint32], ct.c_uint32),
    }
    pru = ct.CDLL(path.as_posix())
    for _fname, _sig in fn_signatures.items():
        fn_ = getattr(pru, _fname)
        fn_.argtypes = _sig[0]
        fn_.restype = _sig[1]
    return pru


virtual_pru = get_device()
