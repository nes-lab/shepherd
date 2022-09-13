"""
The cdef extern... tells Cython that the function declarations below are also found in the virtual_converter.h file. This is useful for ensuring that the Python bindings are built against the same declarations as the C code. 
"""
from libc.stdint cimport uint32_t
from libc.stdint cimport uint64_t
from libc.stdint cimport *
from libc.stdlib cimport malloc, free
cdef extern from "virtual_converter.h":

	# Function declarations from virtual_converter.h
	#cdef void converter_initialize(const volatile struct ConverterConfig *config)
	cdef void converter_calc_inp_power(uint32_t input_voltage_uV, uint32_t input_current_nA)
	cdef void converter_calc_out_power(uint32_t current_adc_raw)
	cdef void converter_update_cap_storage()
	cdef void set_P_input_fW(const uint32_t P_fW)
	cdef void set_P_output_fW(const uint32_t P_fW)
	cdef void set_V_intermediate_uV(const uint32_t C_uV)
	#cdef void set_batok_pin(volatile struct SharedMem * shared_mem, bool_ft value)
	
	#cdef uint32_t converter_update_states_and_output(volatile struct SharedMem * shared_mem)
	cdef uint64_t get_P_input_fW()
	cdef uint64_t get_P_output_fW()
	cdef uint32_t get_V_intermediate_uV()
	cdef uint32_t get_V_intermediate_raw()
	cdef uint32_t get_I_mid_out_nA()
	cdef uint32_t get_state_log_intermediate()
	
