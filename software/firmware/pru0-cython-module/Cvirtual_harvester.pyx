#!python
#cython: language_level=3

cimport hvirtual_harvester
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

# internal variables
cdef uint32_t voltage_set_uV = 0
cdef bool is_rising = False

cdef uint32_t voltage_hold = 0
cdef uint32_t current_hold = 0
cdef uint32_t voltage_step_x4_uV = 0

cdef uint32_t settle_steps = 0 
cdef uint32_t interval_step = 1 << 30

cdef uint32_t volt_step_uV = 0
cdef uint32_t power_last_raw = 0 

cdef const volatile HarvesterConfig *cfg
