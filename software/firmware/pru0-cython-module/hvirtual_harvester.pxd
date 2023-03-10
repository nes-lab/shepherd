"""
The cdef extern... tells Cython that the function declarations below are also found in the virtual_harvester.h file. This is useful for ensuring that the Python bindings are built against the same declarations as the C code.
"""
from libc.stdint cimport *
from libc.stdint cimport uint32_t
from libc.stdint cimport uint64_t
from libc.stdlib cimport free
from libc.stdlib cimport malloc

    
cdef extern from "commons.h":
	cpdef enum:
		ADC_SAMPLES_PER_BUFFER = 10000
		MAX_GPIO_EVT_PER_BUFFER = 16384
		
	cdef packed struct GPIOEdges:
		uint32_t canary
		uint32_t idx
		uint64_t timestamp_ns[MAX_GPIO_EVT_PER_BUFFER]
		uint16_t bitmask[MAX_GPIO_EVT_PER_BUFFER]
		
	cdef packed struct HarvesterConfig:
		uint32_t algorithm
		uint32_t hrv_mode
		uint32_t window_size
		uint32_t voltage_uV
		uint32_t voltage_min_uV
		uint32_t voltage_max_uV
		uint32_t voltage_step_uV  # for window-based algo like ivcurve
		uint32_t current_limit_nA  # lower bound to detect zero current
		uint32_t setpoint_n8
		uint32_t interval_n  # between measurements
		uint32_t duration_n  # of measurement
		uint32_t wait_cycles_n  # for DAC to settle
	    
	cdef packed struct SampleBuffer:
		uint32_t canary
		uint32_t len
		uint64_t timestamp_ns
		uint32_t values_voltage[ADC_SAMPLES_PER_BUFFER]
		uint32_t values_current[ADC_SAMPLES_PER_BUFFER]
		GPIOEdges gpio_edges
		uint32_t pru0_max_ticks_per_sample
		uint32_t pru0_sum_ticks_for_buffer
		
cdef extern from "virtual_harvester.h":
	cdef void harvester_initialize(HarvesterConfig *config)
	cdef uint32_t sample_adc_harvester(SampleBuffer *buffer, uint32_t sample_idx)
	cdef void sample_iv_harvester(uint32_t *p_voltage_uV, uint32_t *p_current_nA)
