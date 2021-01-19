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

void equalize_exp(uint32_t* value1, int8_t* shift1,
		  uint32_t* value2, int8_t* shift2);

void add2(uint32_t* res_value, int8_t* res_expo,
	 uint32_t value1, int8_t expo1,
	 uint32_t value2, int8_t expo2);

void sub2(uint32_t* res_value, int8_t* res_expo,
	 uint32_t value1, int8_t expo1,
	 uint32_t value2, int8_t expo2);

void mul2(uint32_t* res_value, int8_t* res_exp,
	  uint32_t value1, int8_t expo1,
	  uint32_t value2, int8_t expo2);

/* */
void mul1(uint32_t* value1, int8_t* expo1,
	   uint32_t value2, int8_t expo2);

void div2(uint32_t* res_value, int8_t* res_exp,
	 uint32_t value1, int8_t expo1,
	 uint32_t value2, int8_t expo2);





#endif //FLOAT_PSEUDO_H
