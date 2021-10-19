#ifndef PRU_FIRMWARE_PRU0_SHEPHERD_FW_HARVESTER_H
#define PRU_FIRMWARE_PRU0_SHEPHERD_FW_HARVESTER_H

#include "commons.h"

void harvest_struct_init_testable(volatile struct VirtHarvester_Config * config);

void harvest_initialize(const volatile struct VirtHarvester_Config * config, const volatile struct Calibration_Config * cal);



#endif //PRU_FIRMWARE_PRU0_SHEPHERD_FW_HARVESTER_H
