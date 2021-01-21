#ifndef FLOAT_PSEUDO_H
#define FLOAT_PSEUDO_H

#ifdef __GNUC__
static inline uint8_t get_left_zero_count(uint32_t value);
static uint32_t max_value(uint32_t value1, uint32_t value2);
static uint32_t min_value(uint32_t value1, uint32_t value2);
#else
/* use from asm-file */
extern inline uint8_t get_left_zero_count(uint32_t value);
extern inline uint32_t max_value(uint32_t value1, uint32_t value2);
extern inline uint32_t min_value(uint32_t value1, uint32_t value2);
#endif

/* Pseudo unsigned float has the following features:
 * - tries to keep as much resolution as possible during calculation
 * - catches div0 (results in MAX-value)
 * - catches subtraction with first value being smaller than second (results in 0)
 * - bring new numbers into the system -> number following the Operation tells the count of ufloat-input-parameter
 * - should be faster than float-emulation
 */

struct pseudo_float {
	uint32_t value;
	int8_t   shift;
};
typedef struct pseudo_float ufloat;


inline uint32_t extract_value(ufloat num1);


uint32_t compare_gt(ufloat num1, ufloat num2);
uint32_t compare_lt(ufloat num1, ufloat num2);


inline void equalize_exp(ufloat * num1, ufloat * num2);

ufloat add(ufloat num1, ufloat num2);

ufloat sub(ufloat num1, ufloat num2);

ufloat mul(ufloat num1, ufloat num2);

ufloat div(ufloat num1, ufloat num2);

#endif //FLOAT_PSEUDO_H
