#include <stdint.h>
#include "float_pseudo.h"


/* if one exponent is smaller and there is head-space, it will double this value, or if no head-space, half the other value*/
void equalize_exp(uint32_t* const value1, int8_t* const shift1,
		  uint32_t* const value2, int8_t* const shift2)
{
	while (*shift1 != *shift2) // TODO: runs not optimal, but ok for a prototype
	{
		if (*shift1 < *shift2)
		{
			if (get_left_zero_count(*value2) > 0)
			{
				*value2 <<= 1;
				(*shift2)--;
			}
			else
			{
				*value1 >>= 1;
				(*shift1)++;
			}
		}
		else
		{
			if (get_left_zero_count(*value1) > 0)
			{
				*value1 <<= 1;
				(*shift1)--;
			}
			else
			{
				*value2 >>= 1;
				(*shift2)++;
			}
		}
	}
}

/* */
void add2(uint32_t *res_value, int8_t *res_expo,
	 uint32_t value1, int8_t expo1,
	 uint32_t value2, int8_t expo2)
{
	equalize_exp(&value1, &expo1, &value2, &expo2);
	*res_expo = expo1;
	if ((get_left_zero_count(value1) < 1) | (get_left_zero_count(value2) < 1))
	{
		value1 >>= 1;
		value2 >>= 1;
		(*res_expo)++;
	}
	*res_value = value1 + value2;
}

void sub2(uint32_t *res_value, int8_t *res_expo,
	 uint32_t value1, int8_t expo1,
	 uint32_t value2, int8_t expo2)
{
	equalize_exp(&value1, &expo1, &value2, &expo2);
	*res_expo = expo1;
	if (value1 > value2)	*res_value = value1 - value2;
	else			*res_value = 0;
}


void mul2(uint32_t *res_value, int8_t *res_exp,
	  uint32_t value1, int8_t expo1,
	  uint32_t value2, int8_t expo2)
{
	uint8_t lezec1 = get_left_zero_count(value1);
	uint8_t lezec2 = get_left_zero_count(value2);
	*res_exp = expo1 + expo2;
	while (lezec1 + lezec2 < 32)  // TODO: runs not optimal, but ok for a prototype
	{
		(*res_exp)++;
		if (lezec1 > lezec2)
		{
			value1 >>= 1;
			lezec1++;
		}
		else
		{
			value2 >>= 1;
			lezec2++;
		}
	}
	*res_value = value1 * value2;
}


void mul1(uint32_t *value1, int8_t *expo1,
	   uint32_t value2, int8_t expo2)
{
	uint8_t lezec1 = get_left_zero_count(*value1);
	uint8_t lezec2 = get_left_zero_count(value2);
	*expo1 += expo2;
	while (lezec1 + lezec2 < 32)  // TODO: runs not optimal, but ok for a prototype
	{
		(*expo1)++;
		if (lezec1 > lezec2)
		{
			*value1 >>= 1;
			lezec1++;
		}
		else
		{
			value2 >>= 1;
			lezec2++;
		}
	}
	*value1 *= value2;
}

/* bring dividend to full 32bit, and divisor to max 16 bit, shrink if necessary */
void div2(uint32_t *res_value, int8_t *res_exp,
	 uint32_t value1, int8_t expo1,
	 uint32_t value2, int8_t expo2)
{
	*res_exp = expo1 + expo2;

	uint8_t lezec1 = get_left_zero_count(value1);
	value1 <<= lezec1;
	*res_exp -= lezec1;

	uint8_t lezec2 = get_left_zero_count(value2);
	if (lezec2 < 16)
	{
		lezec2 = 16 - lezec2;
		value2 >>= lezec2;
		*res_exp += lezec2;
	}
	else if (lezec2 == 32)
	{
		*res_value = 0xFFFFFFFFu;
		return;
	}

	*res_value = value1 / value2;
}

// TODO: some fn that brings value to desired exponent
