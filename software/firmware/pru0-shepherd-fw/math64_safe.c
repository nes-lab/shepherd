#include "math64_safe.h"

#ifdef __GNUC__
uint8_ft get_num_size_as_bits(const uint32_t value)
{
	/* there is an ASM-COMMAND for that, LMBD r2, r1, 1 */
	uint32_t _value = value;
	uint8_ft count = 32u;
	for (; _value > 0u; _value >>= 1u) count--;
	return count;
}

uint32_t max_value(uint32_t value1, uint32_t value2)
{
	if (value1 > value2) return value1;
	else return value2;
}

uint32_t min_value(uint32_t value1, uint32_t value2)
{
	if (value1 < value2) return value1;
	else return value2;
}
#endif

/* Faster and more time-constant replacement for uint64-multiplication
 * - native code takes 3 - 7 us per mul, depending on size of number (hints at add-loop)
 * - model-calculation gets much safer with container-boundaries
 */
uint64_t mul64(const uint64_t value1, const uint64_t value2)
{
	const uint32_t f1H = value1 >> 32u;
	const uint32_t f1L = (uint32_t)value1;
	const uint32_t f2H = value2 >> 32u;
	const uint32_t f2L = (uint32_t)value2;
	uint64_t product = (uint64_t)f1L * (uint64_t)f2L;
	product += ((uint64_t)f1L * (uint64_t)f2H) << 32u;
	product += ((uint64_t)f1H * (uint64_t)f2L) << 32u;
	//const uint64_t product4 = ((uint64_t)f2H * (uint64_t)f2H); // << 64u
	// check for possible overflow - return max
	uint8_ft f1bits = get_num_size_as_bits(f1H);
	if (f1bits == 0u) f1bits = get_num_size_as_bits(f1L);
	uint8_ft f2bits = get_num_size_as_bits(f2H);
	if (f2bits == 0u) f2bits = get_num_size_as_bits(f2L);
	if ((f1bits + f2bits) <= 64u) 	return product; // simple approximation, not 100% correct, but cheap
	else 				return (uint64_t)(0xFFFFFFFFFFFFFFFFull);
}

uint64_t add64(const uint64_t value1, const uint64_t value2)
{
	const uint64_t sum = value1 + value2;
	if ((sum < value1) || (sum < value2)) 	return (uint64_t)(0xFFFFFFFFFFFFFFFFull);
	else 					return sum;
}

uint64_t sub64(const uint64_t value1, const uint64_t value2)
{
	if (value1 > value2) return (value1 - value2);
	else return 0ull;
}

uint32_t mul32(const uint32_t value1, const uint32_t value2)
{
	uint64_t product = (uint64_t)value1 * (uint64_t)value2;
	// check for possible overflow - return max
	uint8_ft vbits = get_num_size_as_bits(product);
	if (vbits <= 32u)	return (uint32_t)product;
	else 			return (uint32_t)(0xFFFFFFFFu);
}