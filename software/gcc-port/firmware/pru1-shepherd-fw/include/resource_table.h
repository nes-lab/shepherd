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
#include <rsc_types.h>
#include "commons.h"

/* Definition for unused interrupts */
#define HOST_UNUSED         255U

/* Mapping sysevts to a channel. Each pair contains a sysevt, channel. */
/* List of system events in TRM Table 4.22 */
struct ch_map pru_intc_map[] = {
	{ HOST_PRU_EVT_TIMESTAMP, 0 }, // Ext int for sync from ARM host
};

struct my_resource_table {
	struct resource_table base;

	/* offsets to entries */
	uint32_t offset[1]; /* Should match 'num' in actual definition */

	/* resource definitions */
	struct fw_rsc_custom pru_ints;
};

#pragma DATA_SECTION(resourceTable, ".resource_table")
#pragma RETAIN(resourceTable)
struct my_resource_table resourceTable = {
        {
                1, /* Resource table version: only version 1 is supported by the current driver */
                1, /* number of entries in the table */
                { 0U, 0U}, /* reserved, must be zero */
        },
        /* offsets to entries */
        {
                offsetof(struct my_resource_table, pru_ints),
        },

	/* resource definitions */
        {
                TYPE_CUSTOM,
                TYPE_PRU_INTS,
                sizeof(struct fw_rsc_custom_ints),
                {
                        /* PRU_INTS version */
                        0x0000,
                        /* Channel-to-host mapping, 255 for unused
                           In this example, channel 0 is on position 0, so channel 0
                           maps to host interrupt 0 */
                        0,
                        HOST_UNUSED,
			HOST_UNUSED,
                        HOST_UNUSED,
                        HOST_UNUSED,
                        HOST_UNUSED,
                        HOST_UNUSED,
                        HOST_UNUSED,
                        HOST_UNUSED,
                        HOST_UNUSED,
                        /* Number of evts being mapped to channels */
                        (sizeof(pru_intc_map) / sizeof(struct ch_map)),
                        /* Pointer to the structure containing mapped events */
                        pru_intc_map,
                },
        },
};

#endif /* _RSC_TABLE_PRU_H_ */
