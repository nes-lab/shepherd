#ifndef FLOAT_PSEUDO_H
#define FLOAT_PSEUDO_H

#ifdef __GNUC__
static uint8_t get_left_zero_count(uint32_t value);
#else
/* use from asm-file */
extern uint8_t get_left_zero_count(uint32_t value);
extern uint32_t max_value(uint32_t value1, uint32_t value2);
extern uint32_t min_value(uint32_t value1, uint32_t value2);
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


uint32_t extract_value(ufloat num1);


uint32_t compare_gt(ufloat num1, ufloat num2);


void equalize_exp2(ufloat * num1, ufloat * num2);

void equalize_exp0(uint32_t* value1, int8_t* shift1,
		   uint32_t* value2, int8_t* shift2);

ufloat add2(ufloat num1, ufloat num2);

ufloat add1(ufloat num1, uint32_t value2, int8_t shift2);

ufloat add0(uint32_t value1, int8_t shift1,
	    uint32_t value2, int8_t shift2);

ufloat sub2(ufloat num1, ufloat num2);

ufloat sub1(ufloat num1, uint32_t value2, int8_t shift2);

ufloat sub1r(uint32_t value1, int8_t shift1, ufloat num2);

ufloat sub0(uint32_t value1, int8_t shift1,
	    uint32_t value2, int8_t shift2);

ufloat mul2(ufloat num1, ufloat num2);

ufloat mul1(ufloat num1, uint32_t value2, int8_t shift2);

ufloat mul0(uint32_t value1, int8_t shift1,
	    uint32_t value2, int8_t shift2);

ufloat div2(ufloat num1, ufloat num2);

ufloat div1(ufloat num1, uint32_t value2, int8_t shift2);

ufloat div1r(uint32_t value1, int8_t shift1, ufloat num2);

ufloat div0(uint32_t value1, int8_t shift1,
	    uint32_t value2, int8_t shift2);


#endif //FLOAT_PSEUDO_H
