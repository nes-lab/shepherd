#include <stdint.h>
#include "programmer.h"
#include "programmer/hal.h"
#include "programmer/transport.h"
#include "programmer/intelhex.h"
#include "programmer/device.h"
#include "programmer/swd_dap.h"
#include "sys_gpio.h"

// TODO: only for CGT, for GCC see /lib/include/gpio.h
#define REG_MASK_TOGGLE(pin_reg, pin_mask) pin_reg ^= (pin_mask)
#define REG_MASK_ON(pin_reg, pin_mask) pin_reg |= (pin_mask)
#define REG_MASK_OFF(pin_reg, pin_mask) pin_reg &= ~(pin_mask)

int write_to_device(ihex_mem_block_t *block)
{
	int rc;
	uint32_t address = block->address;
	uint32_t *code = (uint32_t *)block->data;

	for (unsigned int i = 0; i < (block->len / 4); i++) {
		if ((rc = nvm_write(address, *(code++))) != 0)
			return rc;
		address += 4;
	}
	return 0;
}

void programmer(volatile struct SharedMem *const shared_mem, volatile struct SampleBuffer *const buffers_far)
{
	/* create more convinient access to structs */
	const uint32_t *const fw = (uint32_t *)buffers_far;
	volatile struct ProgrammerCtrl *const pc = (struct ProgrammerCtrl *)&shared_mem->programmer_ctrl;

	pc->state = 2u; // switch to init-phase

	/* check for validity */
	if (pc->datasize >= shared_mem->mem_size) {
		pc->state = 0xBAAAAAADu;
		return;
	}

	// demo: blink LED of external button: 8_19, 22, gpio0[22]
	const uint32_t gpio_reg_do = CT_GPIO0.GPIO_DATAOUT;
	const uint32_t gpio_reg_oe = CT_GPIO0.GPIO_OE;

	swd_transport_init(pc->pin_tck, pc->pin_tdio, pc->datarate);
	swd_transport_reset();
	uint32_t dummy_data;
	int rctemp = swd_dp_read(&dummy_data, DP_REG_DPIDR);
	swd_ap_init();

	dev_halt();
	nvm_wp_disable();
	nvm_erase();

	ihex_reader_init((char *)fw);
	int rch, rcw;
	ihex_mem_block_t block;

	/* Iterate content of hex file entry by entry */
	while ((rch = ihex_reader_get(&block)) == 0) {
		/* Write block data to target device memory */
		if ((rcw = write_to_device(&block)) != 0) {
			pc->state = 0xBAAAAAADu;
			/* restore initial state */
			CT_GPIO0.GPIO_DATAOUT = gpio_reg_do;
			CT_GPIO0.GPIO_OE = gpio_reg_oe;
			return;
		}
		pc->state++;
	}
	if (rch != IHEX_RET_DONE) {
		pc->state = 0xBAAAAAADu;
		/* restore initial state */
		CT_GPIO0.GPIO_DATAOUT = gpio_reg_do;
		CT_GPIO0.GPIO_OE = gpio_reg_oe;
		return;
	}
	dev_reset();

	unsigned int mcnt;
	if (rch == 1)
		mcnt = 16;
	else
		mcnt = 4;

	for (uint32_t i = 0; i < mcnt; i++) {
		pc->state++; // some kind of progress-bar
		hal_gpio_set(pc->pin_tck, GPIO_STATE_HIGH);
		__delay_cycles(200000);
		hal_gpio_set(pc->pin_tck, GPIO_STATE_LOW);
		__delay_cycles(200000);
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
	pc->state = 0u; // allow py-interface to exit / power down shepherd
}
