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

# static function handling
#cdef uint32_t get_input_efficiency_n8(const uint32_t voltage_uV, const uint32_t current_nA)

# structure declaration
cdef const hvirtual_converter.ConverterConfig *cfg
#ctypedef hvirtual_converter.ConverterConfig *const config

"""
This section looks like a regular Python function — because it just creates a Python function that has access to the C functions. These are Python-Wrappers...
"""

cdef class VirtualConverter:
	# TODO: each FN now needs data-conversion from python-objects to c-objects and reverse for return-values
	
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

	def converter_calc_inp_power(self, input_voltage_uV: int, input_current_nA: int):
		return hvirtual_converter.converter_calc_inp_power(input_voltage_uV, input_current_nA)

	def converter_calc_out_power(self, current_adc_raw):
		return hvirtual_converter.converter_calc_out_power(current_adc_raw)

	def get_I_mid_out_nA(self):
		return hvirtual_converter.get_I_mid_out_nA()

	def get_V_intermediate_raw(self):
		return hvirtual_converter.get_V_intermediate_raw()

	def get_V_intermediate_uV(self):
		return hvirtual_converter.get_V_intermediate_uV()

	def get_P_output_fW(self):
		return hvirtual_converter.get_P_output_fW()

	def get_P_input_fW(self):
		return hvirtual_converter.get_P_input_fW()

	# private fn
	#def py_get_output_inv_efficiency_n4(current_nA):
	#	return get_output_inv_efficiency_n4()

	def set_V_intermediate_uV(self, C_uV):
		hvirtual_converter.set_V_intermediate_uV(C_uV)

	"""	Added from Calibration.c to debug testing.py	"""
	def cal_conv_adc_raw_to_nA(self, current_raw):
		return hvirtual_converter.cal_conv_adc_raw_to_nA(current_raw)
	def cal_conv_uV_to_dac_raw(self, voltage_uV):
		return hvirtual_converter.cal_conv_uV_to_dac_raw(voltage_uV)
