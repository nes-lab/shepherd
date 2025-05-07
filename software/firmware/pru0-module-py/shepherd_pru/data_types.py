import ctypes as ct
from typing import ClassVar

from shepherd_core.data_models.content.virtual_harvester import HarvesterPRUConfig


class HarvesterConfig(ct.Structure):
    _pack_: int = 1  # TODO: test without ClassVar
    _fields_: ClassVar[list] = [(_key, ct.c_uint32) for _key in HarvesterPRUConfig.model_fields] + [
        ("canary", ct.c_uint32)
    ]  # TODO: a sequence (,) seems to be fine


class CalibrationConfig(ct.Structure):
    _pack_: ClassVar[int] = 1
    _fields_: ClassVar[list] = [
        ("adc_current_gain", ct.c_uint32),  # adc_current_factor_nA_n8
        ("adc_current_offset", ct.c_int32),  # adc_current_offset_nA
        ("adc_voltage_gain", ct.c_uint32),  # adc_voltage_factor_uV_n8
        ("adc_voltage_offset", ct.c_int32),  # adc_voltage_offset_uV
        ("dac_voltage_gain", ct.c_uint32),  # dac_voltage_inv_factor_uV_n20
        ("dac_voltage_offset", ct.c_int32),  # dac_voltage_offset_uV
        # NOTE: above are the py-names as the c-struct is handed raw
        ("canary", ct.c_uint32),
    ]


LUT_SIZE: int = 12
LUT_INP = ct.c_uint8 * (LUT_SIZE * LUT_SIZE)
LUT_OUT = ct.c_uint32 * LUT_SIZE


class ConverterConfig(ct.Structure):
    _pack_: ClassVar[int] = 1
    _fields_: ClassVar[list] = [
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
        ("canary", ct.c_uint32),
    ]


VOC_LUT_SIZE: int = 123
VOC_LUT_TYPE = ct.c_uint32 * VOC_LUT_SIZE
RSERIES_LUT_SIZE: int = 100
RSERIES_LUT_TYPE = ct.c_uint32 * RSERIES_LUT_SIZE


class BatteryConfig(ct.Structure):
    _pack_: ClassVar[int] = 1
    _fields_: ClassVar[list] = [
        ("Constant_s_per_mAs_n48", ct.c_uint32),
        ("Constant_1_per_kOhm_n18", ct.c_uint32),
        ("LUT_voc_SoC_min_log2_u_n32", ct.c_uint32),
        ("LUT_voc_uV_n8", VOC_LUT_TYPE),
        ("LUT_rseries_SoC_min_log2_u_n32", ct.c_uint32),
        ("LUT_rseries_KOhm_n32", RSERIES_LUT_TYPE),
        ("canary", ct.c_uint32),
    ]


class SharedMemLight(ct.Structure):
    _pack_: ClassVar[int] = 1
    _fields_: ClassVar[list] = [
        ("pre_A", ct.c_uint32 * 9),
        ("pre_Buff", ct.c_uint32 * (4 + 4 + 5 + 1)),
        ("pre_Cache", ct.c_uint32 * 32),
        ("pre_D", ct.c_uint32 * 2),
        ("calibration_settings", CalibrationConfig),
        ("converter_settings", ConverterConfig),
        ("harvester_settings", HarvesterConfig),
        ("programmer_ctrl", ct.c_uint32 * 11),
        ("proto_msgs", ct.c_uint32 * (6 * 4)),
        ("timestamps", ct.c_uint64 * 2),
        ("canary", ct.c_uint32 * 1),
        ("gpio_pin_state", ct.c_uint32),
        ("trigger_x", ct.c_uint32 * 2),  # bool_ft
        ("vsource_batok_trigger_for_pru1", ct.c_uint32),  # bool_ft
        ("vsource_batok_pin_value", ct.c_uint32),  # bool_ft
        ("vsource_skip_gpio_logging", ct.c_uint32),  # bool_ft
        ("pru0_ns_per_sample", ct.c_uint32),
    ]
