#include <stdint.h>
#include "programmer.h"
#include "sys_gpio.h"

// TODO: only for CGT, for GCC see /lib/include/gpio.h
#define REG_MASK_TOGGLE(pin_reg, pin_mask)	pin_reg ^= (pin_mask)
#define REG_MASK_ON(pin_reg, pin_mask)		pin_reg |= (pin_mask)
#define REG_MASK_OFF(pin_reg, pin_mask)		pin_reg &= ~(pin_mask)

void programmer(volatile struct SharedMem *const shared_mem,
	        volatile struct SampleBuffer *const buffers_far)
{
	/* create more convinient access to structs */
	const struct ProgrammerFW *const fw = (struct ProgrammerFW *)buffers_far;
	volatile struct ProgrammerCtrl *const pc = (struct ProgrammerCtrl *)&shared_mem->programmer_ctrl;

	if (pc->state != 1u)
	{
		/* no valid start-state -> emit error */
		pc->state = 0xBAAAAAADu;
		return
	}

	pc->state = 2u; // switch to init-phase
	// TODO: just for debug -> mirror fw-struct
	pc->pin_tck = fw->signature1;
	pc->pin_tdio = fw->signature2;
	pc->pin_tdo = fw->length;
	pc->pin_tms = fw->data[0];

	/* check for validity */
	if (fw->signature1 != 0xDEADD00D) return;
	if (fw->signature2 != 0x8BADF00D) return;
	if (fw->length >= shared_mem->mem_size)	return;

	// demo: blink LED of external button: 8_19, 22, gpio0[22]
	const uint32_t pin_led_mask = 1u << 22u;
	const uint32_t gpio_reg_do = CT_GPIO0.GPIO_DATAOUT;
	const uint32_t gpio_reg_oe = CT_GPIO0.GPIO_OE;
	REG_MASK_ON(CT_GPIO0.GPIO_DATAOUT, pin_led_mask);
	for (uint32_t i = 0; i < 40; i++)
	{
		pc->state++; // some kind of progress-bar
		REG_MASK_TOGGLE(CT_GPIO0.GPIO_OE, pin_led_mask);
		__delay_cycles(100000000 / 5); // 100 ms
	}
	/* restore initial state */
	CT_GPIO0.GPIO_DATAOUT = gpio_reg_do;
	CT_GPIO0.GPIO_OE = gpio_reg_oe;

	/* TODO: feasibility
	 * - is reading fast enough?
	 * 	- sys_periphery could take 30 to 40 cycles
	 * 	- transfer DDR to shared RAM 47 cycles / 4 byte, 107 cycles / 128 byte -> prefer large chunks
	 * 		-> could be handled by pru1
	 * - it would suffice to map the 4 possible programming pins to the target
	 * - -> currently only 2 pins (from device-tree):
	 *	P9_17(MUX_MODE7 | RX_ACTIVE)    // gpio0[5], swd_clk
	 *	P9_18(MUX_MODE7 | RX_ACTIVE)    // gpio0[4], swd_io
	 */
	pc->protocol = 0u; // allow py-interface to exit / power down shepherd
}
