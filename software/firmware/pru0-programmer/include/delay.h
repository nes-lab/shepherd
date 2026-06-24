#ifndef __DELAY_H_
#define __DELAY_H_
#include <stdint.h>

#define F_CPU (200000000ul)
#define TICK_INTERVAL_NS           (5U)

static inline void delay_us(uint32_t time_us)
{
    while (time_us-- > 0u) __delay_cycles(1000ul / TICK_INTERVAL_NS);
}

static inline void delay_ms(uint32_t time_ms)
{
    while (time_ms-- > 0u) __delay_cycles(1000000ul / TICK_INTERVAL_NS);
}

#endif /* __DELAY_H_ */
