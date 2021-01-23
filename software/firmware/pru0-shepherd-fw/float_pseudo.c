#include <stdint.h>
#include "float_pseudo.h"


#ifdef __GNUC__
static uint8_t get_left_zero_count(const uint32_t value)
{
	/* there is an ASM-COMMAND for that, LMBD r2, r1, 1 */
	uint32_t _value = value;
	uint8_t	count = 32;
	for (; _value > 0; _value >>= 1) count--;
	return count;
}

static uint32_t max_value(uint32_t value1, uint32_t value2)
{
	if (value1 > value2) return value1;
	else return value2;
}

static uint32_t min_value(uint32_t value1, uint32_t value2)
{
	if (value1 < value2) return value1;
	else return value2;
}
#endif

/* TODO: some of these could be a lot faster in asm
 *TODO: first step: go back to old format add(value1, shift1, value2, shift2), this seemed to be much faster. test later in real world condition
 * - asm shows a small mess when using structs (and in general the compiler seems to be quite confused)
 * - this small lib would be perfect for translating it to asm (no globals, and some special asm-cmds that have no c-equivalent)
 * spruhv7b - sect. 6.4.1.3 describes layout of struct-arguments
 * spruh73q - sect. 4.4.1.3 describes MAC-Unit
 * helpful comment: https://stackoverflow.com/questions/35841428/beaglebone-and-pru-division-and-multiplication
*/

/* should be optimal (for c) */
uint32_t extract_value(const ufloat num1)
{
	if (num1.shift > 0)
	{
		if ((uint8_t)num1.shift > get_left_zero_count(num1.value))
		{
			return (0xFFFFFFFFul);
		}
		else
		{
			return (num1.value << (uint8_t)num1.shift);
		}
	}
	else if (num1.shift < 0)
	{
		return (num1.value >> (uint32_t)(-num1.shift));
	}
	return num1.value;
}

/* should be optimal (for c) */
uint32_t compare_gt(ufloat num1, ufloat num2)
{
	const int8_t lezec1 = get_left_zero_count(num1.value) - num1.shift;
	const int8_t lezec2 = get_left_zero_count(num2.value) - num2.shift;
	if (lezec1 == lezec2)
	{
		// a fast / dirty equalize_exp-FN without while()
		if (lezec1 >= 0)
		{
			if (num1.shift > num2.shift) 	num1.value <<= (uint8_t)(num1.shift - num2.shift);
			else				num2.value <<= (uint8_t)(num2.shift - num1.shift);
		}
		else
		{
			if (num1.shift > num2.shift)	num2.value >>= (uint8_t)(num1.shift - num2.shift);
			else				num1.value >>= (uint8_t)(num2.shift - num1.shift);
		}

		if (num1.value > num2.value)
			return 1u;
		else	return 0u;
	}
	else
	{
		if (lezec1 < lezec2)
			return 1u;
		else 	return 0u;
	}
}

/* should be optimal (for c) */
uint32_t compare_lt(ufloat num1, ufloat num2)
{
	const int8_t lezec1 = get_left_zero_count(num1.value) - num1.shift;
	const int8_t lezec2 = get_left_zero_count(num2.value) - num2.shift;
	if (lezec1 == lezec2)
	{
		// a fast / dirty equalize_exp-FN without while()
		if (lezec1 >= 0)
		{
			if (num1.shift > num2.shift) 	num1.value <<= (uint8_t)(num1.shift - num2.shift);
			else				num2.value <<= (uint8_t)(num2.shift - num1.shift);
		}
		else
		{
			if (num1.shift > num2.shift)	num2.value >>= (uint8_t)(num1.shift - num2.shift);
			else				num1.value >>= (uint8_t)(num2.shift - num1.shift);
		}

		if (num1.value < num2.value)
			return 1u;
		else	return 0u;
	}
	else
	{
		if (lezec1 > lezec2)
			return 1u;
		else 	return 0u;
	}
}

/* should be optimal (for c) TODO: fastest, but not most precise. read comments in code   */
void equalize_exp(ufloat * const num1, ufloat * const num2)
{
	if (num1->shift == num2->shift) return;
	if (num1->shift > num2->shift)
	{
		const uint8_t diff = num1->shift - num2->shift;
		if (diff <= get_left_zero_count(num1->value))
		{
			num1->value <<= diff; // with some additional overhead this could shift min(diff,lezec1)
			num1->shift = num2->shift;
		}
		else
		{
			num2->value >>= diff; // if needed this could only shift (diff - min(diff,lezec1))
			num2->shift = num1->shift;
		}
	}
	else
	{
		const uint8_t diff = num2->shift - num1->shift;
		if (diff <= get_left_zero_count(num2->value))
		{
			num2->value <<= diff; // see comments above, same addition
			num2->shift = num1->shift;
		}
		else
		{
			num1->value >>= diff;
			num1->shift = num2->shift;
		}
	}
}

/* should be optimal (for c) */
ufloat add(ufloat num1, ufloat num2)
{
	equalize_exp(&num1, &num2);
	if ((get_left_zero_count(num1.value) == 0u) | (get_left_zero_count(num2.value) == 0u))
	{
		num1.value >>= 1u;
		num2.value >>= 1u;
		num1.shift++;
	}
	num1.value += num2.value;
	return num1;
}

/* should be optimal (for c) */
ufloat sub(ufloat num1, ufloat num2)
{
	equalize_exp(&num1, &num2);
	if (num1.value > num2.value)	num1.value -= num2.value;
	else				num1.value = 0;
	return num1;
}


ufloat mul(ufloat num1, ufloat num2)
{
	uint8_t lezec1 = get_left_zero_count(num1.value);
	uint8_t lezec2 = get_left_zero_count(num2.value);
	num1.shift += num2.shift;
	while ((lezec1 + lezec2) < 32u)  // TODO: runs not optimal, but ok for a prototype
	{
		num1.shift += 4;
		if (lezec1 < lezec2)
		{
			num1.value >>= 4u;
			lezec1 += 4;
		}
		else
		{
			num2.value >>= 4u;
			lezec2 += 4;
		}
	}
	num1.value *= num2.value;
	return num1;
}

/* should be optimal (for c) */
ufloat div(ufloat num1, ufloat num2)
{
	const uint8_t lezec1 = get_left_zero_count(num1.value);
	num1.value <<= lezec1;
	num1.shift -= lezec1 + num2.shift;

	uint8_t lezec2 = get_left_zero_count(num2.value);
	if (lezec2 < 16u)
	{
		lezec2 = 16u - lezec2;
		num2.value >>= lezec2;
		num1.shift += lezec2;
	}
	else if (lezec2 == 32u)
	{
		num1.value = 0xFFFFFFFFul;
		return num1;
	}

	num1.value /= num2.value;
	return num1;
}
