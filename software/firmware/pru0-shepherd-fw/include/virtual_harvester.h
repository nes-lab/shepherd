#ifndef PRU_FIRMWARE_PRU0_SHEPHERD_FW_HARVESTER_H
#define PRU_FIRMWARE_PRU0_SHEPHERD_FW_HARVESTER_H

#include "commons.h"


/* private FNs */
static inline uint32_t conv_adc_raw_to_nA(uint32_t current_raw); // TODO: the first two could also be helpful for sampling
static inline uint32_t conv_uV_to_dac_raw(uint32_t voltage_uV);

void harvester_struct_init(volatile struct HarvesterConfig *);

void harvester_initialize(const volatile struct HarvesterConfig *, const volatile struct CalibrationConfig *);

void harvest_adc_cv(struct SampleBuffer *, const uint32_t);
void harvest_adc_ivcurve(struct SampleBuffer *, const uint32_t);

#endif //PRU_FIRMWARE_PRU0_SHEPHERD_FW_HARVESTER_H
