"""
The cdef extern... tells Cython that the function declarations below are also found in the virtual_converter.h file. This is useful for ensuring that the Python bindings are built against the same declarations as the C code.
"""
from libc.stdint cimport *

from libc.stdint cimport uint32_t
from libc.stdint cimport uint64_t
from libc.stdlib cimport free
from libc.stdlib cimport malloc

cdef extern from "simple_lock.h":
	cdef packed struct simple_mutex_t:
		bint lock_pru0
		bint lock_pru1

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
		MAX_GPIO_EVT_PER_BUFFER = 16384
		ADC_SAMPLES_PER_BUFFER = 10000
		
	cdef packed struct GPIOEdges:
		uint32_t canary
		uint32_t idx
		uint64_t timestamp_ns[MAX_GPIO_EVT_PER_BUFFER]
		uint16_t bitmask[MAX_GPIO_EVT_PER_BUFFER]
		
	cdef packed struct SampleBuffer:
		uint32_t canary
		uint32_t len
		uint64_t timestamp_ns
		uint32_t values_voltage[ADC_SAMPLES_PER_BUFFER]
		uint32_t values_current[ADC_SAMPLES_PER_BUFFER]
		GPIOEdges gpio_edges
		uint32_t pru0_max_ticks_per_sample
		uint32_t pru0_sum_ticks_for_buffer
		
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
	
	cdef packed struct HarvesterConfig:
		uint32_t algorithm
		uint32_t hrv_mode
		uint32_t window_size
		uint32_t voltage_uV
		uint32_t voltage_min_uV
		uint32_t voltage_max_uV
		uint32_t voltage_step_uV  	# for window-based algo like ivcurve
		uint32_t current_limit_nA  	# lower bound to detect zero current
		uint32_t setpoint_n8
		uint32_t interval_n  		# between measurements
		uint32_t duration_n  		# of measurement
		uint32_t wait_cycles_n  	# for DAC to settle
	
	cdef packed struct CalibrationConfig:
		uint32_t adc_current_factor_nA_n8
		int32_t adc_current_offset_nA
		uint32_t adc_voltage_factor_uV_n8
		int32_t adc_voltage_offset_uV
		uint32_t dac_voltage_inv_factor_uV_n20
		int32_t dac_voltage_offset_uV
		
	cdef packed struct ProgrammerCtrl:
		int32_t	 state
		uint32_t target
		uint32_t datarate 		# baud
		uint32_t datasize 		# bytes
		uint32_t pin_tck 		# clock-out for JTAG, SBW, SWD
		uint32_t pin_tdio 		# data-io for SWD & SBW, input-only for JTAG (TDI)
		uint32_t pin_dir_tdio 	# direction (HIGH == Output to target)
		uint32_t pin_tdo 		# data-output for JTAG
		uint32_t pin_tms 		# mode for JTAG
		uint32_t pin_dir_tms 	# direction (HIGH == Output to target)
		
	cdef packed struct ProtoMsg:
		uint8_t 	id 				# Identifier => Canary, This is used to identify memory corruption
		uint8_t 	unread 			# Token-System to signal new message & the ack, (sender sets unread/1, receiver resets/0)
		uint8_t 	type 			# content description used to distinguish messages, see enum MsgType	
		uint8_t 	reserved[1] 	# Alignment with memory, (bytes)mod4	
		uint32_t 	value[2] 		# Actual Content of message
		
	cdef struct SyncMsg:
		uint8_t  id
		uint8_t  unread
		uint8_t  type
		uint8_t  reserved0[1]
		uint32_t buffer_block_period
		uint32_t analog_sample_period
		uint32_t compensation_steps
		uint64_t next_timestamp_ns

	cdef struct SharedMem:
		uint32_t                 shepherd_state
		uint32_t                 shepherd_mode
		uint32_t                 dac_auxiliary_voltage_raw
		uint32_t                 mem_base_addr
		uint32_t                 mem_size
		uint32_t                 n_buffers
		uint32_t                 samples_per_buffer
		uint32_t                 buffer_period_ns
		uint32_t                 pru0_ticks_per_sample
		CalibrationConfig 		 calibration_settings
		ConverterConfig   		 converter_settings
		HarvesterConfig   		 harvester_settings
		ProgrammerCtrl    		 programmer_ctrl
		ProtoMsg          		 pru0_msg_inbox
		ProtoMsg          		 pru0_msg_outbox
		ProtoMsg          		 pru0_msg_error
		SyncMsg           		 pru1_sync_inbox
		ProtoMsg          		 pru1_sync_outbox
		ProtoMsg          		 pru1_msg_error
		uint64_t                 last_sample_timestamp_ns
		uint64_t                 next_buffer_timestamp_ns
		simple_mutex_t           gpio_edges_mutex
		uint32_t                 gpio_pin_state
		GPIOEdges        		*gpio_edges
		SampleBuffer     		*sample_buffer
		uint32_t                 analog_sample_counter
		uint32_t                 analog_value_index
		uint32_t                 analog_value_current
		uint32_t                 analog_value_voltage
		bint                     cmp0_trigger_for_pru1
		bint                     cmp1_trigger_for_pru1
		bint                     vsource_batok_trigger_for_pru1
		bint                     vsource_batok_pin_value
		bint                     vsource_skip_gpio_logging


cdef extern from "math64_safe.h":	
	cdef uint64_t mul64(uint64_t value1, uint64_t value2)
	cdef uint64_t add64(uint64_t value1, uint64_t value2)
	
	
cdef extern from "virtual_converter.h":

	# Function declarations from virtual_converter.h
	cdef void converter_initialize(ConverterConfig *config)
	cdef void converter_calc_inp_power(uint32_t input_voltage_uV, uint32_t input_current_nA)
	cdef void converter_calc_out_power(uint32_t current_adc_raw)
	cdef void converter_update_cap_storage()
	cdef void set_P_input_fW(uint32_t P_fW)
	cdef void set_P_output_fW(uint32_t P_fW)
	cdef void set_V_intermediate_uV(uint32_t C_uV)
	cdef void set_batok_pin(SharedMem *shared_mem, bint value)

	cdef uint32_t converter_update_states_and_output(SharedMem *shared_mem)
	cdef uint64_t get_P_input_fW()
	cdef uint64_t get_P_output_fW()
	cdef uint32_t get_V_intermediate_uV()
	cdef uint32_t get_V_intermediate_raw()
	cdef uint32_t get_I_mid_out_nA()
	cdef bint get_state_log_intermediate()
	cdef uint64_t div_uV_n4_wrapper(uint64_t power_fW_n4, uint32_t voltage_uV)
	cdef uint32_t get_input_efficiency_n8_wrapper(uint32_t voltage_uV, uint32_t current_nA)
	cdef uint32_t get_output_inv_efficiency_n4_wrapper(uint32_t current_nA)
	
