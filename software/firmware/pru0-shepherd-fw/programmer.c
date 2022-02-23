#include <stdint.h>
#include "programmer.h"
#include "programmer/hal.h"
#include "programmer/intelhex.h"
#include "programmer/device.h"
#include "programmer/swd_transport.h"
#include "sys_gpio.h"

int write_to_device(device_driver_t *drv, ihex_mem_block_t *block)
{
	int rc;
	uint32_t address = block->address;
	uint32_t *code = (uint32_t *)block->data;

	for (unsigned int i = 0; i < (block->len / 4); i++) {
		if ((rc = drv->write(address, *(code++))) != DRV_ERR_OK)
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

	pc->state = PRG_STATE_INITIALIZING;

	/* check for validity */
	if (pc->datasize >= shared_mem->mem_size) {
		pc->state = PRG_STATE_ERR;
		return;
	}

	device_driver_t *drv = &nrf52_driver;
	if (drv->open(pc->pin_tck, pc->pin_tdio, pc->datarate)) {
		pc->state = PRG_STATE_ERR;
		goto exit;
	}

#if 1
	if (drv->erase() != DRV_ERR_OK) {
		pc->state = PRG_STATE_ERR;
		goto exit;
	}

	int rch, rcw;

	ihex_reader_init((char *)fw);
	ihex_mem_block_t block;

	/* State specifies number of bytes written to target */
	pc->state = 0;

	/* Iterate content of hex file entry by entry */
	while ((rch = ihex_reader_get(&block)) == 0) {
		/* Write block data to target device memory */
		if ((rcw = write_to_device(drv, &block)) != 0) {
			pc->state = PRG_STATE_ERR;
			goto exit;
		}
		pc->state += block.len;
	}
	if (rch != IHEX_RET_DONE) {
		pc->state = PRG_STATE_ERR;
		goto exit;
	}
#endif
	/* signal py-interface to exit / power down shepherd */
	pc->state = PRG_STATE_IDLE;

exit:
	drv->close();
}
