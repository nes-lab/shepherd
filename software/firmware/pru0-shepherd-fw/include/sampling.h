#ifndef SHEPHERD_PRU0_SAMPLING_H_
#define SHEPHERD_PRU0_SAMPLING_H_

#include "commons.h"

void sample_init(const volatile struct SharedMem *shared_mem);

#ifdef EMU_SUPPORT
void sample(volatile struct SharedMem *const shared_mem,
            struct SampleBuffer *const current_buffer_far, const enum ShepherdMode mode);
#else
void sample(const volatile struct SharedMem *const shared_mem,
            struct SampleBuffer *const current_buffer_far, const enum ShepherdMode mode);
#endif


uint32_t sample_dbg_adc(uint32_t channel_num);
void     sample_dbg_dac(uint32_t value);

#endif /* SHEPHERD_PRU0_SAMPLING_H_ */
