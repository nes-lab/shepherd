from libc.stdint cimport *
from libc.stdint cimport uint32_t
from libc.stdint cimport uint64_t
from libc.stdlib cimport free
from libc.stdlib cimport malloc


cdef extern from "harvester.h":
    void harvester_initialize(const volatile HarvesterConfig *config)
    uint32_t sample_adc_harvester(struct SampleBuffer *buffer, uint32_t sample_idx)
    void sample_iv_harvester(uint32_t *p_voltage_uV, uint32_t *p_current_nA
