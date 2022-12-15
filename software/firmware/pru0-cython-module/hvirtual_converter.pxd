"""
The cdef extern... tells Cython that the function declarations below are also found in the virtual_converter.h file. This is useful for ensuring that the Python bindings are built against the same declarations as the C code.
"""
from libc.stdint cimport *
from libc.stdint cimport uint32_t
from libc.stdint cimport uint64_t
from libc.stdlib cimport free
from libc.stdlib cimport malloc


cdef extern from "calibration.h":
	cdef uint32_t cal_conv_adc_raw_to_nA(uint32_t current_raw)
	cdef uint32_t cal_conv_adc_raw_to_uV(uint32_t voltage_raw)
	cdef uint32_t cal_conv_uV_to_dac_raw(uint32_t voltage_uV)

cdef extern from "math64_safe.h":
	cdef uint64_t sub64(uint64_t value1, uint64_t value2)
	cdef uint32_t msb_position(uint32_t value)

cdef extern from "commons.h":
	cpdef enum:
		LUT_SIZE = 12
	cdef struct ConverterConfig:
		uint32_t converter_mode
		uint32_t interval_startup_delay_drain_n
		uint32_t V_input_max_uV
		uint32_t I_input_max_nA
		uint32_t V_input_drop_uV
		uint32_t R_input_kOhm_n22
		uint32_t Constant_us_per_nF_n28
		uint32_t V_intermediate_init_uV
		uint32_t I_intermediate_leak_nA
		uint32_t V_enable_output_threshold_uV
		uint32_t V_disable_output_threshold_uV
		uint32_t dV_enable_output_uV
		uint32_t interval_check_thresholds_n
		uint32_t V_pwr_good_enable_threshold_uV
		uint32_t V_pwr_good_disable_threshold_uV
		uint32_t immediate_pwr_good_signal
		uint32_t V_output_log_gpio_threshold_uV
		uint32_t V_input_boost_threshold_uV
		uint32_t V_intermediate_max_uV
		uint32_t V_output_uV
		uint32_t V_buck_drop_uV
		uint32_t LUT_input_V_min_log2_uV
		uint32_t LUT_input_I_min_log2_nA
		uint32_t LUT_output_I_min_log2_nA
		uint8_t  LUT_inp_efficiency_n8[LUT_SIZE][LUT_SIZE]
		uint32_t LUT_out_inv_efficiency_n4[LUT_SIZE]

cdef extern from "virtual_converter.h":

	# Function declarations from virtual_converter.h
	cdef void converter_initialize(ConverterConfig *config)
	cdef void converter_calc_inp_power(uint32_t input_voltage_uV, uint32_t input_current_nA)
	cdef void converter_calc_out_power(uint32_t current_adc_raw)
	cdef void converter_update_cap_storage()
	cdef void set_P_input_fW(uint32_t P_fW)
	cdef void set_P_output_fW(uint32_t P_fW)
	cdef void set_V_intermediate_uV(uint32_t C_uV)
	#cdef void set_batok_pin(volatile struct SharedMem * shared_mem, bool_ft value)

	#cdef uint32_t converter_update_states_and_output(volatile struct SharedMem * shared_mem)
	cdef uint64_t get_P_input_fW()
	cdef uint64_t get_P_output_fW()
	cdef uint32_t get_V_intermediate_uV()
	cdef uint32_t get_V_intermediate_raw()
	cdef uint32_t get_I_mid_out_nA()
	cdef uint32_t get_state_log_intermediate()
