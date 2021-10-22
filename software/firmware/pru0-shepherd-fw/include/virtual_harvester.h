#ifndef PRU_FIRMWARE_PRU0_SHEPHERD_FW_HARVESTER_H
#define PRU_FIRMWARE_PRU0_SHEPHERD_FW_HARVESTER_H

#include "commons.h"

void harvester_struct_init(volatile struct HarvesterConfig *);
void harvester_initialize(const volatile struct HarvesterConfig *);

void harvester_branches(struct SampleBuffer *, uint32_t);

void harvest_adc_cv(struct SampleBuffer *, uint32_t);
void harvest_adc_ivcurve(struct SampleBuffer *, uint32_t);
void harvest_adc_mppt_voc(struct SampleBuffer *, uint32_t);
void harvest_adc_mppt_po(struct SampleBuffer *, uint32_t);

#endif //PRU_FIRMWARE_PRU0_SHEPHERD_FW_HARVESTER_H
