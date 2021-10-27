#ifndef PRU_FIRMWARE_PRU0_SHEPHERD_FW_MATH64_SAFE_H
#define PRU_FIRMWARE_PRU0_SHEPHERD_FW_MATH64_SAFE_H

#include "stdint_fast.h"

uint64_t mul64(uint64_t value1, uint64_t value2);
uint32_t mul32(uint32_t value1, uint32_t value2);
uint64_t add64(uint64_t value1, uint64_t value2);
uint32_t add32(uint32_t value1, uint32_t value2);
uint64_t sub64(uint64_t value1, uint64_t value2);
uint32_t sub32(uint32_t value1, uint32_t value2);

#ifdef __GNUC__
uint8_ft get_num_size_as_bits(const uint32_t value);
uint32_t max_value(uint32_t value1, uint32_t value2);
uint32_t min_value(uint32_t value1, uint32_t value2);
#else
/* use from asm-file */
extern uint32_t get_num_size_as_bits(uint32_t value);
extern uint32_t msb_position(uint32_t value);
extern inline uint32_t max_value(uint32_t value1, uint32_t value2);
extern inline uint32_t min_value(uint32_t value1, uint32_t value2);
#endif


#endif //PRU_FIRMWARE_PRU0_SHEPHERD_FW_MATH64_SAFE_H
