#!python
#cython: language_level=3

cimport hvirtual_harvester
from libc.stdint cimport *

import pyximport
import math


"""
This section looks like a regular Python function — because it just creates a Python function that has access to the C functions. These are Python-Wrappers...
"""

cdef class VirtualConverter:
	def __init__(self):
		pass
	
	def harv_initialize(self, config): # Tracability Done.
		cdef hvirtual_harvester.HarvesterConfig config_struct
		config_struct.voltage_uV = config['voltage_uV']
		config_struct.hrv_mode = config['hrv_mode']
		config_struct.voltage_step_uV = config['voltage_step_uV']

		return hvirtual_harvester.harvester_initialize(&config_struct)
		
	def sample_adc_harvester(self, sample_idx):
		cdef hvirtual_harvester.SampleBuffer *buffer
		return hvirtual_harvester.sample_adc_harvester(buffer, sample_idx)
		
