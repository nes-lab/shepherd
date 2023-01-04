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
The language used here is a special mix of C and Python. However it will look fairly familiar to Python developers.
"""

cpdef enum:
	DIV_SHIFT 	= 17
	DIV_LUT_SIZE	= 40
	
cdef uint32_t LUT_div_uV_n27[DIV_LUT_SIZE] 
LUT_div_uV_n27[:] = [16383, 683, 410, 293, 228, 186, 158, 137, 120, 108, 98, 89, 82, 76, 71, 66, 62, 59, 55, 53, 50, 48, 46, 44, 42, 40, 39, 37, 36, 35, 34, 33, 32, 31, 30, 29, 28, 27, 27, 26]

"""	A Trial for structure	"""
cdef struct ConverterState:
	uint64_t V_mid_uV_n32
	uint64_t P_out_fW_n4
	uint32_t V_out_dac_uV
	uint32_t interval_startup_disabled_drain_n
	uint32_t enable_buck

"""	Declaring variables pointing to structs	"""
cdef ConverterState 				state
cdef hvirtual_converter.ConverterConfig 	*cfg
cdef:
	void converter_initialize(hvirtual_converter.ConverterConfig *config) except *:
		cfg					 = config
		state.V_mid_uV_n32			 = cfg.V_intermediate_init_uV << 32	# can add 2**32 as an alternate to shifting, to represent signed to unsigned
		state.P_out_fW_n4 			 = 0
		state.V_out_dac_uV			 = cfg.V_output_uV
		state.interval_startup_disabled_drain_n = cfg.interval_startup_delay_drain_n
		state.enable_buck                       = (cfg.converter_mode & 0b0100) > 0
		
# static function handling
#cdef uint32_t get_input_efficiency_n8(const uint32_t voltage_uV, const uint32_t current_nA)

# structure declaration
# cdef const hvirtual_converter.ConverterConfig *cfg
# ctypedef hvirtual_converter.ConverterConfig *const config

"""
This section looks like a regular Python function — because it just creates a Python function that has access to the C functions. These are Python-Wrappers...
"""

cdef class VirtualConverter:
	# TODO: each FN now needs data-conversion from python-objects to c-objects and reverse for return-values
	"""
	def __init__(self):
		cdef hvirtual_converter.ConverterConfig* config
		hvirtual_converter.converter_initialize(config)
	"""
	
	def get_V_intermediate_uV(self):
		return hvirtual_converter.get_V_intermediate_uV()
	
	def get_P_input_fW(self):
		return hvirtual_converter.get_P_input_fW()
		
	def get_P_output_fW(self):
		return hvirtual_converter.get_P_output_fW()
		
	def get_I_mid_out_nA(self):
		return hvirtual_converter.get_I_mid_out_nA()
	
	"""
	def __init__(self, vs_config: list):
		cdef hvirtual_converter.ConverterConfig* config
		self.config.converter_mode 			 						= vs_config[0]
		self.config.interval_startup_delay_drain_n	 						= vs_config[1]
		self.config.V_input_max_uV			 						= vs_config[2]
		self.config.I_input_max_nA			 						= vs_config[3]
		self.config.V_input_drop_uV			 						= vs_config[4]
		self.config.R_input_kOhm_n22		 							= vs_config[5]
		self.config.Constant_us_per_nF_n28		 						= vs_config[6]
		self.config.V_intermediate_init_uV		 						= vs_config[7]
		self.config.I_intermediate_leak_nA		 						= vs_config[8]
		self.config.V_enable_output_threshold_uV	 						= vs_config[9]
		self.config.V_disable_output_threshold_uV	 						= vs_config[10]
		self.config.dV_enable_output_uV		 						= vs_config[11]
		self.config.interval_check_thresholds_n	 						= vs_config[12]
		self.config.V_pwr_good_enable_threshold_uV 	 						= vs_config[13]
		self.config.V_pwr_good_disable_threshold_uV	 						= vs_config[14]
		self.config.immediate_pwr_good_signal	 							= vs_config[15]
		self.config.V_output_log_gpio_threshold_uV	 						= vs_config[16]
		self.config.V_input_boost_threshold_uV	 							= vs_config[16]
		self.config.V_intermediate_max_uV		 						= vs_config[17]
		self.config.V_output_uV			 						= vs_config[18]
		self.config.V_buck_drop_uV			 						= vs_config[19]
		self.config.LUT_input_V_min_log2_uV		 						= vs_config[20]
		self.config.LUT_input_I_min_log2_nA		 						= vs_config[21]
		self.config.LUT_output_I_min_log2_nA	 							= vs_config[22]
		self.config.LUT_inp_efficiency_n8[hvirtual_converter.LUT_SIZE][hvirtual_converter.LUT_SIZE]   = vs_config[23]
		self.config.LUT_out_inv_efficiency_n4[hvirtual_converter.LUT_SIZE] 				= vs_config[24]		
		hvirtual_converter.converter_initialize(config)
	"""
		
	"""
	@staticmethod
	def get_input_efficiency_n8(self, voltage_uV: int, current_nA: int) -> int:
		voltage_n = int(voltage_uV / (2**self.config.LUT_input_V_min_log2_uV))
		current_n = int(current_nA / (2**self.config.LUT_input_I_min_log2_nA))
		pos_v = int(voltage_n) if (voltage_n > 0) else 0  # V-Scale is Linear!
		pos_c = int(math.log2(current_n)) if (current_n > 0) else 0
		if pos_v >= hvirtual_converter.LUT_SIZE:
			pos_v = hvirtual_converter.LUT_SIZE - 1
		if pos_c >= hvirtual_converter.LUT_SIZE:
			pos_c = hvirtual_converter.LUT_SIZE - 1
		return self.config.LUT_inp_efficiency_n8[pos_v * hvirtual_converter.LUT_SIZE + pos_c] / (2**8)
		
	@staticmethod
	def get_output_inv_efficiency_n4(self, current_nA) -> int:
		current_n = int(current_nA / (2**self.config.LUT_output_I_min_log2_nA))
		pos_c = int(math.log2(current_n)) if (current_n > 0) else 0
		if pos_c >= hvirtual_converter.LUT_SIZE:
			pos_c = hvirtual_converter.LUT_SIZE- 1
		return self.config.LUT_out_inv_efficiency_n4[pos_c] / (2**4)
	"""				

	""" Added temporarily to check static function callability, without using exact py-objects(due to some errors) by replacing it with random numbers """
	@staticmethod
	def get_input_efficiency_n8(self, voltage_uV: int, current_nA: int) -> int:
		voltage_n = int(voltage_uV / (2**1))
		current_n = int(current_nA / (2**1))
		pos_v = int(voltage_n) if (voltage_n > 0) else 0  # V-Scale is Linear!
		pos_c = int(math.log2(current_n)) if (current_n > 0) else 0
		if pos_v >= hvirtual_converter.LUT_SIZE:
			pos_v = hvirtual_converter.LUT_SIZE - 1
		if pos_c >= hvirtual_converter.LUT_SIZE:
			pos_c = hvirtual_converter.LUT_SIZE - 1
		return (1*hvirtual_converter.LUT_SIZE + pos_c) / (2**8)
		
	@staticmethod
	def get_output_inv_efficiency_n4(self, current_nA) -> int:
		current_n = int(current_nA / (2**1))
		pos_c = int(math.log2(current_n)) if (current_n > 0) else 0
		if pos_c >= hvirtual_converter.LUT_SIZE:
			pos_c = hvirtual_converter.LUT_SIZE- 1
		return  1/(2**4)
	""" check ends here """
	
	@staticmethod
	def div_uV_n4(self, power_fW_n4, voltage_uV):
		lut_pos = int(voltage_uV / (2**DIV_SHIFT))
		if lut_pos >= DIV_LUT_SIZE:
			lut_pos = DIV_LUT_SIZE - 1
		return hvirtual_converter.mul64((power_fW_n4 >> 10u), (LUT_div_uV_n27[lut_pos]) >> 17)
	
	def converter_calc_inp_power(self, input_voltage_uV: int, input_current_nA: int):
		return hvirtual_converter.converter_calc_inp_power(input_voltage_uV, input_current_nA)

	def converter_calc_out_power(self, current_adc_raw)-> int:

		cdef uint64_t V_mid_uV_n4  = state.V_mid_uV_n32 >> 28
		cdef uint64_t P_leak_fW_n4 = hvirtual_converter.mul64(cfg.I_intermediate_leak_nA, V_mid_uV_n4)
		cdef uint32_t I_out_nA     = hvirtual_converter.cal_conv_adc_raw_to_nA(current_adc_raw)
		
		cdef uint32_t eta_inv_out_n4 = VirtualConverter.get_output_inv_efficiency_n4(I_out_nA) if (state.enable_buck) else (1 << 4)
		state.P_out_fW_n4 = hvirtual_converter.add64(hvirtual_converter.mul64(eta_inv_out_n4 * state.V_out_dac_uV, I_out_nA), P_leak_fW_n4)
		if (state.interval_startup_disabled_drain_n > 0):
			state.interval_startup_disabled_drain_n-=1
			state.P_out_fW_n4 = 0
		return state.P_out_fW_n4
		#return hvirtual_converter.converter_calc_out_power(current_adc_raw)	

	def get_V_intermediate_raw(self):
		return hvirtual_converter.get_V_intermediate_raw()

	def set_V_intermediate_uV(self, C_uV):
		hvirtual_converter.set_V_intermediate_uV(C_uV)

	"""	Added from Calibration.c to debug testing.py	"""
	def cal_conv_adc_raw_to_nA(self, current_raw):
		return hvirtual_converter.cal_conv_adc_raw_to_nA(current_raw)
	def cal_conv_uV_to_dac_raw(self, voltage_uV):
		return hvirtual_converter.cal_conv_uV_to_dac_raw(voltage_uV)
		
	"""	Added from math64_safe.c to use div_uV_n4	"""
	def mul64(self, value1, value2):
		return hvirtual_converter.mul64(value1, value2)
	def add64(self, value1, value2):
		return hvirtual_converter.add64(value1, value2)
		
