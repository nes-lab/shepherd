#ifndef __DELAY_H_
#define __DELAY_H_

#define F_CPU 200000000

extern void __delay_var_cycles(unsigned int cycles);

static inline void delay_ns(unsigned int time_ns)
{
	__delay_var_cycles(time_ns / 5);
}

static inline void delay_us(unsigned int time_us)
{
	__delay_var_cycles(time_us * 200);
}

static inline void delay_ms(unsigned int time_ms)
{
	__delay_var_cycles(time_ms * 200000);
}

#endif /* __DELAY_H_ */
