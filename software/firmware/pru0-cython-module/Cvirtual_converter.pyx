#!python
#cython: language_level=3

#cimport hvirtual_converter
"""vishal.shepherd.software.firmware.pru0_shepherd_fw."""
#from hvirtual_converter cimport (converter_calc_inp_power, converter_calc_out_power, converter_update_cap_storage, set_P_input_fW, set_P_output_fW, set_V_intermediate_uV, get_P_input_fW, get_P_output_fW, get_V_intermediate_uV, get_V_intermediate_raw, get_I_mid_out_nA)

cimport hvirtual_converter
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
	The language used here is a special mix of C and Python.
	However it will look fairly familiar to Python developers.


	This section looks like a regular Python function — because it just creates a Python function that has access to the C functions.
	These are Python-Wrappers...
"""

"""
def converter_initialize(*config):
	hvirtual_converter.converter_initialize(*config)
"""

def converter_calc_inp_power(input_voltage_uV, input_current_nA):
	return hvirtual_converter.converter_calc_inp_power(input_voltage_uV, input_current_nA)

def converter_calc_out_power(current_adc_raw):
	return hvirtual_converter.converter_calc_out_power(current_adc_raw)

def get_I_mid_out_nA():
	return hvirtual_converter.get_I_mid_out_nA()

def get_V_intermediate_raw():
	return hvirtual_converter.get_V_intermediate_raw()

def get_V_intermediate_uV():
	return hvirtual_converter.get_V_intermediate_uV()

def get_P_output_fW():
	return hvirtual_converter.get_P_output_fW()

def get_P_input_fW():
	return hvirtual_converter.get_P_input_fW()

# private fn
#def py_get_output_inv_efficiency_n4(current_nA):
#	return get_output_inv_efficiency_n4()

def set_V_intermediate_uV(C_uV):
	hvirtual_converter.set_V_intermediate_uV(C_uV)
