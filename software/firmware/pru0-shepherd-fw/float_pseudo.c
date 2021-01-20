#include <stdint.h>
#include "float_pseudo.h"


#ifdef __GNUC__
static uint8_t get_left_zero_count(const uint32_t value)
{
	/* TODO: there is a ASM-COMMAND for that, LMBD r2, r1, 1 */
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

// TODO: some of these could be a lot faster in asm

uint32_t extract_value(ufloat num1)
{
	uint32_t uShift;
	if (num1.shift > 0)
	{
		uShift = (uint32_t)num1.shift;
		if (uShift > get_left_zero_count(num1.value))
		{
			return (0xFFFFFFFFul);
		}
		else
		{
			return (num1.value << uShift);
		}
	}
	else if (num1.shift < 0)
	{
		uShift = (uint32_t)(0-num1.shift);
		return (num1.value >> uShift);
	}
	return num1.value;
}


uint32_t compare_gt(ufloat num1, ufloat num2)
{
	int8_t lezec1 = get_left_zero_count(num1.value) - num1.shift;
	int8_t lezec2 = get_left_zero_count(num2.value) - num2.shift;
	if (lezec1 == lezec2)
	{
		equalize_exp0(&(num1.value), &(num1.shift), &(num2.value), &(num2.shift)); // TODO: there should be a fast / dirty FN without while
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


uint32_t compare_lt(ufloat num1, ufloat num2)
{
	int8_t lezec1 = get_left_zero_count(num1.value) - num1.shift;
	int8_t lezec2 = get_left_zero_count(num2.value) - num2.shift;
	if (lezec1 == lezec2)
	{
		equalize_exp0(&(num1.value), &(num1.shift), &(num2.value), &(num2.shift)); // TODO: there should be a fast / dirty FN without while
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


void equalize_exp2(ufloat * const num1, ufloat * const num2)
{
	equalize_exp0(&(num1->value), &(num1->shift), &(num2->value), &(num2->shift));
}

/* if one shiftnent is smaller and there is head-space, it will double this value, or if no head-space, half the other value*/
void equalize_exp0(uint32_t* const value1, int8_t* const shift1,
		   uint32_t* const value2, int8_t* const shift2)
{
	while (*shift1 != *shift2) // TODO: runs not optimal, but ok for a prototype, instead of while this algo could jump directly, using fast min/max
	{
		if (*shift1 < *shift2)
		{
			if (get_left_zero_count(*value2) > 0u)
			{
				*value2 <<= 1u;
				(*shift2)--;
			}
			else
			{
				*value1 >>= 1u;
				(*shift1)++;
			}
		}
		else
		{
			if (get_left_zero_count(*value1) > 0u)
			{
				*value1 <<= 1u;
				(*shift1)--;
			}
			else
			{
				*value2 >>= 1u;
				(*shift2)++;
			}
		}
	}
}

ufloat add2(ufloat num1, ufloat num2)
{
	return add0(num1.value, num1.shift, num2.value, num2.shift);
}

ufloat add1(ufloat num1, uint32_t value2, int8_t shift2)
{
	return add0(num1.value, num1.shift, value2, shift2);
}

ufloat add0(uint32_t value1, int8_t shift1,
	    uint32_t value2, int8_t shift2)
{
	ufloat result;
	equalize_exp0(&value1, &shift1, &value2, &shift2);
	result.shift = shift1;
	if ((get_left_zero_count(value1) < 1u) | (get_left_zero_count(value2) < 1u))
	{
		value1 >>= 1u;
		value2 >>= 1u;
		result.shift++;
	}
	result.value = value1 + value2;
	return result;
}

ufloat sub2(ufloat num1, ufloat num2)
{
	return sub0(num1.value, num1.shift, num2.value, num2.shift);
}

ufloat sub1(ufloat num1, uint32_t value2, int8_t shift2)
{
	return sub0(num1.value, num1.shift, value2, shift2);
}

ufloat sub1r(uint32_t value1, int8_t shift1, ufloat num2)
{
	return sub0(value1, shift1, num2.value, num2.shift);
}

ufloat sub0(uint32_t value1, int8_t shift1,
	    uint32_t value2, int8_t shift2)
{
	ufloat result;
	equalize_exp0(&value1, &shift1, &value2, &shift2);
	result.shift = shift1;
	if (value1 > value2)	result.value = value1 - value2;
	else			result.value = 0u;
	return result;
}

ufloat mul2(ufloat num1, ufloat num2)
{
	return mul0(num1.value, num1.shift, num2.value, num2.shift);
}

ufloat mul1(ufloat num1, uint32_t value2, int8_t shift2)
{
	return mul0(num1.value, num1.shift, value2, shift2);
}

ufloat mul0(uint32_t value1, int8_t shift1,
	    uint32_t value2, int8_t shift2)
{
	ufloat result;
	uint8_t lezec1 = get_left_zero_count(value1);
	uint8_t lezec2 = get_left_zero_count(value2);
	result.shift = shift1 + shift2;
	while ((lezec1 + lezec2) < 32u)  // TODO: runs not optimal, but ok for a prototype
	{
		result.shift++;
		if (lezec1 > lezec2)
		{
			value1 >>= 1u;
			lezec1++;
		}
		else
		{
			value2 >>= 1u;
			lezec2++;
		}
	}
	result.value = value1 * value2;
	return result;
}

ufloat div2(ufloat num1, ufloat num2)
{
	return div0(num1.value, num1.shift, num2.value, num2.shift);
}

ufloat div1(ufloat num1, uint32_t value2, int8_t shift2)
{
	return div0(num1.value, num1.shift, value2, shift2);
}

ufloat div1r(uint32_t value1, int8_t shift1, ufloat num2)
{
	return div0(value1, shift1, num2.value, num2.shift);
}

/* bring dividend to full 32bit, and divisor to max 16 bit, shrink if necessary */
ufloat div0(uint32_t value1, int8_t shift1,
	    uint32_t value2, int8_t shift2)
{
	ufloat result;
	result.shift = shift1 + shift2;

	uint8_t lezec1 = get_left_zero_count(value1);
	value1 <<= lezec1;
	result.shift -= lezec1;

	uint8_t lezec2 = get_left_zero_count(value2);
	if (lezec2 < 16u)
	{
		lezec2 = 16u - lezec2;
		value2 >>= lezec2;
		result.shift += lezec2;
	}
	else if (lezec2 == 32u)
	{
		result.value = 0xFFFFFFFFul;
		return result;
	}

	result.value = value1 / value2;
	return result;
}

ufloat sqrt_rounded(const ufloat num1)
{
	uint8_t lezec1 = get_left_zero_count(num1.value);
	ufloat result;
	uint32_t op;

	if (lezec1 > 1u)
	{
		op = num1.value << (lezec1 - 1u);
		result.shift = num1.shift - lezec1 + 1;
	}
	else
	{
		op = num1.value;
		result.shift = num1.shift;
	}

	uint32_t res = 0U;
	uint32_t one = 1uL << 30u;

	while (one > op)  // TODO: could be removed
	{
		one >>= 2u;
	}

	while (one != 0u)
	{
		if (op >= res + one)
		{
			op = op - (res + one);
			res = res + 2U * one;
		}
		res >>= 1U;
		one >>= 2U;
	}
	if (op > res) res++;

	result.value = res;
	return result;
}

