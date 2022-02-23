#ifndef __PROG_HAL_H_
#define __PROG_HAL_H_

#include "sys_gpio.h"
#include "var_delay.h"

#define F_CPU 200000000

typedef enum { GPIO_DIR_OUT = 0, GPIO_DIR_IN = 1 } gpio_dir_t;
typedef enum { GPIO_STATE_LOW = 0, GPIO_STATE_HIGH = 1 } gpio_state_t;

static inline void hal_gpio_cfg_dir(unsigned int pin, gpio_dir_t dir)
{
	if (dir == GPIO_DIR_OUT)
		CT_GPIO0.GPIO_OE &= ~(1 << pin);
	else
		CT_GPIO0.GPIO_OE |= (1 << pin);
}
static inline void hal_gpio_set(unsigned int pin, gpio_state_t state)
{
	if (state)
		CT_GPIO0.GPIO_SETDATAOUT = (1 << pin);
	else
		CT_GPIO0.GPIO_CLEARDATAOUT = (1 << pin);
}

static inline gpio_state_t hal_gpio_read(unsigned int pin)
{
	return (gpio_state_t)(CT_GPIO0.GPIO_DATAIN >> pin) & 1u;
}

static inline void hal_delay_ns(unsigned int time_ns)
{
	__delay_var_cycles(time_ns / 5);
}

#endif /* __PROG_HAL_H_ */
