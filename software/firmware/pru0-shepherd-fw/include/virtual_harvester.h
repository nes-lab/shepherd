#ifndef PRU_FIRMWARE_PRU0_SHEPHERD_FW_HARVESTER_H
#define PRU_FIRMWARE_PRU0_SHEPHERD_FW_HARVESTER_H

#include "commons.h"

void harvester_struct_init(volatile struct HarvesterConfig *);

void harvester_initialize(const volatile struct HarvesterConfig *, const volatile struct CalibrationConfig *);



#endif //PRU_FIRMWARE_PRU0_SHEPHERD_FW_HARVESTER_H
