#ifndef __DELAY_H_
#define __DELAY_H_

#define F_CPU (200000000u)

extern void        __delay_var_cycles(uint32_t cycles);

static inline void delay_ns(uint32_t time_ns) { __delay_var_cycles(time_ns / 5u); }

static inline void delay_us(uint32_t time_us) { __delay_var_cycles(time_us * 200u); }

static inline void delay_ms(uint32_t time_ms) { __delay_var_cycles(time_ms * 200000ul); }

#endif /* __DELAY_H_ */
