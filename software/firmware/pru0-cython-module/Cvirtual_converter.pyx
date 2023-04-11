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
The language used here is a special mix of C and Python .. it might be more resembling with python except for special type handling ..
"""

cpdef enum:
	DIV_SHIFT = 17
	DIV_LUT_SIZE = 40

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
	
"""
This section looks like a regular Python function — because it just creates a Python function that has access to the C functions. These are Python-Wrappers...
"""

cdef class VirtualConverter:
	#cdef hvirtual_converter.SharedMem* shared_mem_ptr
	cdef dict config 
	cdef dict share
	cdef ConverterState state
	
	def __init__(self):
		self.share = {}
		self.config = {
		'interval_startup_delay_drain_n': 0,
		'V_intermediate_init_uV': 0,
		'converter_mode': 0,
		'V_output_uV': 0,
		'dV_enable_output_uV': 0,
		'V_enable_output_threshold_uV': 0,
		'V_disable_output_threshold_uV': 0
		}
		
	def div_uV_n4(self, power_fW_n4, voltage_uV): 
		return hvirtual_converter.div_uV_n4_wrapper(power_fW_n4, voltage_uV)
	
	def conv_initialize(self, config): 
		cdef hvirtual_converter.ConverterConfig config_struct
		
		config_struct.interval_startup_delay_drain_n = self.config['interval_startup_delay_drain_n']
		config_struct.V_intermediate_init_uV = self.config['V_intermediate_init_uV']
		config_struct.converter_mode = self.config['converter_mode']
		config_struct.V_output_uV = self.config['V_output_uV']
		config_struct.dV_enable_output_uV = self.config['dV_enable_output_uV']
		config_struct.V_enable_output_threshold_uV = self.config['V_enable_output_threshold_uV']
		config_struct.V_disable_output_threshold_uV = self.config['V_disable_output_threshold_uV']
		
		hvirtual_converter.converter_initialize(&config_struct)
		return self.state.V_enable_output_threshold_uV_n32
	
	def converter_calc_inp_power(self, input_voltage_uV, input_current_nA):
		hvirtual_converter.converter_calc_inp_power(input_voltage_uV, input_current_nA)
		#return self.state.P_inp_fW_n8

	def converter_calc_out_power(self, current_adc_raw): 
		return hvirtual_converter.converter_calc_out_power(current_adc_raw)
		
	def converter_update_cap_storage(self): 
		return hvirtual_converter.converter_update_cap_storage()
		
	def converter_update_states_and_output(self, share):
		cdef hvirtual_converter.SharedMem shared_mem_ptr
		#share = shared_mem_ptr
		shared_mem_ptr.vsource_skip_gpio_logging = self.share['vsource_skip_gpio_logging']
		return hvirtual_converter.converter_update_states_and_output(&shared_mem_ptr)
		
	def get_input_efficiency_n8(self, voltage_uV, current_nA): 
		return hvirtual_converter.get_input_efficiency_n8_wrapper(voltage_uV, current_nA)
		
	def get_output_inv_efficiency_n4(self, current_nA):	
		return hvirtual_converter.get_output_inv_efficiency_n4_wrapper(current_nA)
	
	def set_P_input_fW(self, P_fW):
		hvirtual_converter.set_P_input_fW(P_fW)
		return self.state.P_inp_fW_n8
		
	def set_P_output_fW(self, P_fW):
		hvirtual_converter.set_P_output_fW(P_fW)
		return self.state.P_out_fW_n4
	
	def set_V_intermediate_uV(self, C_uV):
		hvirtual_converter.set_V_intermediate_uV(C_uV)
		return self.state.V_mid_uV_n32
		
	def get_P_input_fW(self):
		return hvirtual_converter.get_P_input_fW()
	
	def get_P_output_fW(self):
		return hvirtual_converter.get_P_output_fW()
	
	def get_V_intermediate_uV(self):
		return hvirtual_converter.get_V_intermediate_uV()
	
	def mul64(self, value1, value2):
		return hvirtual_converter.mul64(value1, value2)

	def cal_conv_uV_to_dac_raw(self, voltage_uV):
		return hvirtual_converter.cal_conv_uV_to_dac_raw(voltage_uV)		
	
	def get_V_intermediate_raw(self):
		return hvirtual_converter.get_V_intermediate_raw()
		
	#def set_batok_pin(self, SharedMem *shared_mem, bint value):
	#	return hvirtual_converter.set_batok_pin()
		
	def get_I_mid_out_nA(self):
		return hvirtual_converter.get_I_mid_out_nA()
	
	def get_state_log_intermediate(self):
		return hvirtual_converter.get_state_log_intermediate()	
		
	"""	Added from Calibration.c to debug testing.py	"""
	def cal_conv_adc_raw_to_nA(self, current_raw):
		return hvirtual_converter.cal_conv_adc_raw_to_nA(current_raw)

	"""	Added from math64_safe.c to use in converter_calc_out_power	"""
	def add64(self, value1, value2):
		return hvirtual_converter.add64(value1, value2)
		
