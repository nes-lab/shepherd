/*
 * Copyright (C) 2016 Texas Instruments Incorporated - http://www.ti.com/
 *
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 *
 *	* Redistributions of source code must retain the above copyright
 *	  notice, this list of conditions and the following disclaimer.
 *
 *	* Redistributions in binary form must reproduce the above copyright
 *	  notice, this list of conditions and the following disclaimer in the
 *	  documentation and/or other materials provided with the
 *	  distribution.
 *
 *	* Neither the name of Texas Instruments Incorporated nor the names of
 *	  its contributors may be used to endorse or promote products derived
 *	  from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#ifndef _RSC_TABLE_PRU_H_
#define _RSC_TABLE_PRU_H_

#include <stddef.h>

#include "resource_table0.h"

#include "commons.h"
#include "ringbuffer.h"

/* Definition for unused interrupts */
#define HOST_UNUSED     255U

#define SIZE_CARVEOUT	(FIFO_BUFFER_SIZE * sizeof(struct SampleBuffer))

// pseudo-assertion to test for correct struct-size, zero cost
extern uint32_t CHECK_CARVEOUT[1/(SIZE_CARVEOUT >= FIFO_BUFFER_SIZE * (8 + 4 + 2*4*10000 + 4 + 8*16384 + 2*16384 + 2*4))];

#pragma DATA_SECTION(resourceTable, ".resource_table")
#pragma RETAIN(resourceTable)
struct my_resource_table resourceTable = {
        {
                1, /* Resource table version: only version 1 is supported by the current driver */
                1, /* number of entries in the table */
                { 0U, 0U } /* reserved, must be zero */
        },
        /* offsets to entries */
        {
		offsetof(struct my_resource_table, shared_mem),
        },

	/* resource entries */
        {
		TYPE_CARVEOUT, 0x0, /* Memory address */
		0x0, /* Physical address */
		SIZE_CARVEOUT, /* ~ 15 MB */
		0, /* Flags */
		0, /* Reserved */
		"PRU_HOST_SHARED_MEM"
        },
};

#endif /* _RSC_TABLE_PRU_H_ */
