import ctypes as ct
from pathlib import Path

from .data_types import CalibrationConfig
from .data_types import ConverterConfig
from .data_types import HarvesterConfig
from .data_types import SharedMemLight


def get_device() -> ct.CDLL:
    path = Path(__file__).parent / "_shared_pru.so"
    fn_signatures = {
        # virtual_harvester.d ##############################
        "harvester_initialize": ([ct.POINTER(HarvesterConfig)], None),
        "sample_ivcurve_harvester": ([ct.POINTER(ct.c_uint32), ct.POINTER(ct.c_uint32)], None),
        # calibration.c ##############################
        "calibration_initialize": ([ct.POINTER(CalibrationConfig)], None),
        "cal_conv_adc_raw_to_nA": ([ct.c_uint32], ct.c_uint32),
        "cal_conv_adc_raw_to_uV": ([ct.c_uint32], ct.c_uint32),
        "cal_conv_uV_to_dac_raw": ([ct.c_uint32], ct.c_uint32),
        # virtual_converter.d ##############################
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
        "get_V_output_uV": (None, ct.c_uint32),
        "get_state_log_intermediate": (None, ct.c_uint32),  # bool_ft
        "set_batok_pin": (None, None),
        # vSource-helper-fn ##############################
        "vsrc_iterate_sampling": ([ct.c_uint32, ct.c_uint32, ct.c_uint32], ct.c_uint32),
        # math64_safe.c ##############################
        "mul32": ([ct.c_uint32, ct.c_uint32], ct.c_uint32),
        "mul64": ([ct.c_uint64, ct.c_uint64], ct.c_uint64),
        "add32": ([ct.c_uint32, ct.c_uint32], ct.c_uint32),
        "add64": ([ct.c_uint64, ct.c_uint64], ct.c_uint64),
        "sub32": ([ct.c_uint32, ct.c_uint32], ct.c_uint32),
        "sub64": ([ct.c_uint64, ct.c_uint64], ct.c_uint64),
        "get_size_in_bits": ([ct.c_uint32], ct.c_uint8),
        "log2safe": ([ct.c_uint32], ct.c_uint32),
        "max_value": ([ct.c_uint32, ct.c_uint32], ct.c_uint32),
        "min_value": ([ct.c_uint32, ct.c_uint32], ct.c_uint32),
    }
    pru = ct.CDLL(path.as_posix())
    for _fname, _sig in fn_signatures.items():
        _fn = getattr(pru, _fname)
        _fn.argtypes = _sig[0]
        _fn.restype = _sig[1]
    return pru


virtual_pru = get_device()
