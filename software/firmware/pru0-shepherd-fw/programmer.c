#include <stdint.h>
#include "programmer.h"

void programmer(volatile struct SharedMem *const shared_mem,
	        volatile struct SampleBuffer *const buffers_far)
{
	struct ProgrammerFW *const fw = (struct ProgrammerFW *)buffers_far;

	shared_mem->programmer_ctrl = (struct ProgrammerCtrl){
		.has_work = 0u,
		.protocol = 333u,
		.datarate_baud = 115200u,
		.pin_clk = fw->signature1,
		.pin_io = fw->signature2,
		.pin_o = fw->length,
		.pin_m = fw->data[0]};

	if (fw->signature1 != 0xDEADD00D) return;
	if (fw->signature2 != 0x8BADF00D) return;
	if (fw->length >= shared_mem->mem_size)	return;
}
