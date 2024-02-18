#cython: language_level=3

cimport hvirtual_converter

#import hvirtual_converter
from libc.stdint cimport *
from libc.stdint cimport uint32_t
from libc.stdint cimport uint64_t
from libc.stdlib cimport free
from libc.stdlib cimport malloc

import pyximport

#cdef extern from "virtual_converter.c":
#	cdef static uint32_t get_input_efficiency_n8(uint32_t voltage_uV, uint32_t current_nA)
#	cdef static uint32_t get_output_inv_efficiency_n4(uint32_t current_nA)

"""
The language used here is a special mix of C and Python. However it will look fairly familiar to Python developers.
"""
cdef const hvirtual_converter.ConverterConfig *cfg
#ctypedef hvirtual_converter.ConverterConfig *const config

"""
	def converter_initialize(self.config):
		hvirtual_converter.converter_initialize(self.config)

	cdef _setup(self, cfg* t):
		self._config = config
		return self
	def __cinit__(self, ):
		self.config = config
		converter_initialize(&config)
"""
"""
This section looks like a regular Python function — because it just creates a Python function that has access to the C functions. These are Python-Wrappers...
"""

cdef class VirtualConverter:
	# TODO: each FN now needs data-conversion from python-objects to c-objects and reverse for return-values

	def __init__(self, vs_config: list):
		# TODO: convert python-dict to ConverterConfig-Struct, similar to virtual_converter_model.py, line 53 and following
		cdef hvirtual_converter.ConverterConfig* config
		config.converter_mode = vs_config[0]
		# ... either
		hvirtual_converter.converter_initialize(config)

	def converter_calc_inp_power(self, input_voltage_uV, input_current_nA):
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
