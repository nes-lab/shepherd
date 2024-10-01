#ifndef PRU_FIRMWARE_PRU0_SHEPHERD_FW_MATH64_SAFE_H_
#define PRU_FIRMWARE_PRU0_SHEPHERD_FW_MATH64_SAFE_H_

#include "stdint_fast.h"

uint64_t mul64(uint64_t value1, uint64_t value2);
uint32_t mul32(uint32_t value1, uint32_t value2);
uint64_t add64(uint64_t value1, uint64_t value2);
uint32_t add32(uint32_t value1, uint32_t value2);
uint64_t sub64(uint64_t value1, uint64_t value2);
uint32_t sub32(uint32_t value1, uint32_t value2);


#if defined(__GNUC__) || defined(__PYTHON__)
// TODO: not completely correct - now the gnu-pru also uses c-code instead of 1-op asm
uint8_ft get_size_in_bits(const uint32_t value);
uint8_ft log2safe(uint32_t value);
uint32_t max_value(uint32_t value1, uint32_t value2);
uint32_t min_value(uint32_t value1, uint32_t value2);
#else
/* use from asm-file */
extern uint8_ft get_size_in_bits(uint32_t value);
extern uint8_ft log2safe(uint32_t value);
extern uint32_t max_value(uint32_t value1, uint32_t value2);
extern uint32_t min_value(uint32_t value1, uint32_t value2);
#endif


#endif //PRU_FIRMWARE_PRU0_SHEPHERD_FW_MATH64_SAFE_H_
