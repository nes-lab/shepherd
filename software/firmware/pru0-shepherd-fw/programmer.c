#include <stdint.h>
#include "programmer.h"
#include "intelhex.h"
#include "programmer/device.h"
#include "programmer/swd_transport.h"
#include "sys_gpio.h"

#define SWD_SUPPORT
//#define SBW_SUPPORT

/* Writes block from hex file to target via driver */
int write_to_target(device_driver_t *drv, ihex_mem_block_t *block)
{
	uint32_t read_back;
	uint8_t *src = block->data;
	uint32_t dst = block->address;

	/* Number of words in this block */
	unsigned int n_words = block->len / drv->word_width_bytes;

	for (unsigned int i = 0; i < n_words; i++) {
		uint32_t data = *((uint32_t *)src);
		if (drv->write(dst, data) != DRV_ERR_OK)
			return -1;
		/* read back and verify data */
		if (drv->read(&read_back, dst) != DRV_ERR_OK)
			return -1;
		if (read_back != data)
			return -2;

		src += drv->word_width_bytes;
		dst += drv->word_width_bytes;
	}
	return 0;
}

void programmer(volatile struct SharedMem *const shared_mem, volatile struct SampleBuffer *const buffers_far)
{
	device_driver_t *drv;
	int ret;
	ihex_mem_block_t block;

	/* create more convinient access to structs */
	const uint32_t *const fw = (uint32_t *)buffers_far;
	volatile struct ProgrammerCtrl *const pc = (struct ProgrammerCtrl *)&shared_mem->programmer_ctrl;

	pc->state = PRG_STATE_INITIALIZING;

	/* check for validity */
	if (pc->datasize >= shared_mem->mem_size) {
		pc->state = PRG_STATE_ERR;
		return;
	}

#ifdef SWD_SUPPORT
	if (pc->protocol == PRG_PROTOCOL_SWD)
		drv = &nrf52_driver;
#endif
#ifdef SBW_SUPPORT
	if (pc->protocol == PRG_PROTOCOL_SBW)
		drv = &msp430fr_driver;
#endif
	else {
		pc->state = PRG_STATE_ERR;
		goto exit;
	}

	if (drv->open(pc->pin_tck, pc->pin_tdio, pc->datarate) != DRV_ERR_OK) {
		pc->state = PRG_STATE_ERR;
		goto exit;
	}

	if (drv->erase() != DRV_ERR_OK) {
		pc->state = PRG_STATE_ERR;
		goto exit;
	}

	ihex_reader_init((char *)fw);

	/* State specifies number of bytes written to target */
	pc->state = 0;

	/* Iterate content of hex file entry by entry */
	while ((ret = ihex_reader_get(&block)) == 0) {
		/* Write block data to target device memory */
		if (write_to_target(drv, &block) != 0) {
			pc->state = PRG_STATE_ERR;
			goto exit;
		}
		/* Show progress by incrementing state by number of bytes written */
		pc->state += block.len;
	}
	if (ret != IHEX_RET_DONE) {
		pc->state = PRG_STATE_ERR;
		goto exit;
	}

	/* signal py-interface to exit / power down shepherd */
	pc->state = PRG_STATE_IDLE;

exit:
	drv->close();
}
