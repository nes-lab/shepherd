#!python
#cython: language_level=3

cimport hvirtual_converter
from libc.stdint cimport *
from libc.stdint cimport uint32_t
from libc.stdint cimport uint64_t
from libc.stdlib cimport free
from libc.stdlib cimport malloc

import pyximport
import math

"""
The language used here is a special mix of C and Python. However it will look fairly familiar to Python developers
"""

cpdef enum:
	DIV_SHIFT 		= 17
	DIV_LUT_SIZE	= 40
	
cdef uint32_t LUT_div_uV_n27[DIV_LUT_SIZE] 
LUT_div_uV_n27[:] = [16383, 683, 410, 293, 228, 186, 158, 137, 120, 108, 98, 89, 82, 76, 71, 66, 62, 59, 55, 53, 50, 48, 46, 44, 42, 40, 39, 37, 36, 35, 34, 33, 32, 31, 30, 29, 28, 27, 27, 26]

"""	Structure definition	"""
cdef struct ConverterState:
	uint64_t V_mid_uV_n32
	uint64_t P_out_fW_n4
	uint32_t V_out_dac_uV
	uint32_t interval_startup_disabled_drain_n
	bint enable_storage
	uint32_t V_input_uV
	bint enable_boost
	bint enable_log_mid
	uint64_t P_inp_fW_n8
	bint enable_buck
	uint32_t V_out_dac_raw
	uint64_t V_enable_output_threshold_uV_n32
	uint64_t V_disable_output_threshold_uV_n32
	uint64_t dV_enable_output_uV_n32
	bint power_good # The bint type is used for the boolean fields, as it maps to the C bool type.

"""	Declaring variables to access structure members	"""
cdef ConverterState state 
cdef hvirtual_converter.ConverterConfig config_struct
cdef hvirtual_converter.SharedMem sharedMem_struct
		
"""
This section looks like a regular Python function — because it just creates a Python function that has access to the C functions. These are Python-Wrappers...
"""

cdef class VirtualConverter:
	def __init__(self):
		pass
		
	def conv_initialize(self, config): # Tracability Done.
		global config_struct, state
		config_struct = config
		hvirtual_converter.converter_initialize(&config_struct)
		
		# Initialize state
		state.V_input_uV = 0u
		state.P_inp_fW_n8 = 0ull
		state.P_out_fW_n4 = 0ull
		state.interval_startup_disabled_drain_n = config_struct.interval_startup_delay_drain_n

		# container for the stored energy:
		state.V_mid_uV_n32 = (<uint64_t> config_struct.V_intermediate_init_uV) << 32u

		# Buck Boost
		state.enable_storage = (config_struct.converter_mode & 0b0001) > 0
		state.enable_boost = (config_struct.converter_mode & 0b0010) > 0
		state.enable_buck = (config_struct.converter_mode & 0b0100) > 0
		state.enable_log_mid = (config_struct.converter_mode & 0b1000) > 0

		state.V_out_dac_uV = config_struct.V_output_uV
		state.V_out_dac_raw = hvirtual_converter.cal_conv_uV_to_dac_raw(config_struct.V_output_uV)
		state.power_good = True

		# prepare hysteresis-thresholds
		state.dV_enable_output_uV_n32 = (<uint64_t> config_struct.dV_enable_output_uV) << 32u
		state.V_enable_output_threshold_uV_n32 = (<uint64_t> config_struct.V_enable_output_threshold_uV) << 32u
		state.V_disable_output_threshold_uV_n32 = (<uint64_t> config_struct.V_disable_output_threshold_uV) << 32u

		if state.dV_enable_output_uV_n32 > state.V_enable_output_threshold_uV_n32:
			state.V_enable_output_threshold_uV_n32 = state.dV_enable_output_uV_n32
	
	def converter_calc_inp_power(self, input_voltage_uV: int, input_current_nA: int): # Tracability Done.
		return hvirtual_converter.converter_calc_inp_power(input_voltage_uV, input_current_nA)

	def converter_calc_out_power(self, current_adc_raw): # Tracability Done.
		return hvirtual_converter.converter_calc_out_power(current_adc_raw)
		
	def converter_update_cap_storage(self): # Tracability Done.
		return hvirtual_converter.converter_update_cap_storage()
		
	#def converter_update_states_and_output(self, shared_mem):
		#cdef hvirtual_converter.SharedMem* sharedMem_struct = <SharedMem*>shared_mem
	#	return hvirtual_converter.converter_update_states_and_output(sharedMem_struct)
		
	def get_V_intermediate_uV(self):
		return hvirtual_converter.get_V_intermediate_uV()
	
	def get_P_input_fW(self):
		return hvirtual_converter.get_P_input_fW()
		
	def get_P_output_fW(self):
		return hvirtual_converter.get_P_output_fW()
		
	def get_I_mid_out_nA(self):
		return hvirtual_converter.get_I_mid_out_nA()
	
	def div_uV_n4(self, power_fW_n4, voltage_uV): # Tracability Done.
		return hvirtual_converter.div_uV_n4_wrapper(power_fW_n4, voltage_uV)
		
	def get_input_efficiency_n8(self, voltage_uV, current_nA): # Tracability Done.	
		return hvirtual_converter.get_input_efficiency_n8_wrapper(voltage_uV, current_nA)
		
	def get_output_inv_efficiency_n4(self, current_nA):	# Tracability Done.
		return hvirtual_converter.get_output_inv_efficiency_n4_wrapper(current_nA)

	def get_V_intermediate_raw(self):
		return hvirtual_converter.get_V_intermediate_raw()

	def set_V_intermediate_uV(self, C_uV):
		hvirtual_converter.set_V_intermediate_uV(C_uV)
		
	"""	Added from Calibration.c to debug testing.py	"""
	def cal_conv_adc_raw_to_nA(self, current_raw):
		return hvirtual_converter.cal_conv_adc_raw_to_nA(current_raw)
	def cal_conv_uV_to_dac_raw(self, voltage_uV):
		return hvirtual_converter.cal_conv_uV_to_dac_raw(voltage_uV)
		
	"""	Added from math64_safe.c to use in div_uV_n4	"""
	def mul64(self, value1, value2):
		return hvirtual_converter.mul64(value1, value2)
	"""	Added from math64_safe.c to use in converter_calc_out_power	"""
	def add64(self, value1, value2):
		return hvirtual_converter.add64(value1, value2)
		
