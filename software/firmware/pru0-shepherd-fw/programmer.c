#include <stdint.h>
#include "programmer.h"

void programmer(volatile struct SharedMem *const shared_mem,
	        volatile struct SampleBuffer *const buffers_far)
{

	struct ProgrammerFW *const fw = (struct ProgrammerFW *)buffers_far;

	if (fw->signature1 != 0xDEAD) return;
	if (fw->signature2 != 0xD00D) return;
	if (fw->length >= shared_mem->mem_size)	return;

	shared_mem->programmer_ctrl = (struct ProgrammerCtrl){
		.has_work = 0u,
		.type = 0u,
		.target_port = 1001u,
		.voltage_mV = 1002u,
		.frequency_Hz = 1003u,
		.pin_clk = fw->signature1,
		.pin_io = fw->signature2,
		.pin_o = fw->length,
		.pin_m = fw->data[0]};

}
