#ifndef PRU_FIRMWARE_PRU0_INCLUDE_PROGRAMMER_H
#define PRU_FIRMWARE_PRU0_INCLUDE_PROGRAMMER_H

#include "commons.h"

void programmer(volatile struct SharedMem *shared_mem, volatile struct SampleBuffer *buffers_far);

#endif //PRU_FIRMWARE_PRU0_INCLUDE_PROGRAMMER_H
