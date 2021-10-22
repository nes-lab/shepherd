#ifndef PRU_FIRMWARE_PRU0_SHEPHERD_FW_INCLUDE_PROGRAMMER_H
#define PRU_FIRMWARE_PRU0_SHEPHERD_FW_INCLUDE_PROGRAMMER_H

#include "commons.h"

void programmer_struct_init(volatile struct ProgrammerCtrl *);

void programmer(volatile struct SharedMem * shared_mem,
	    volatile struct SampleBuffer * buffers_far);

#endif //PRU_FIRMWARE_PRU0_SHEPHERD_FW_INCLUDE_PROGRAMMER_H
