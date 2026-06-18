#ifndef SHEPHERD_PRU0_RESOURCE_TABLE_H_
#define SHEPHERD_PRU0_RESOURCE_TABLE_H_

#include <rsc_types.h>

struct my_resource_table
{
    struct resource_table  base;

    /* offsets to entries */
    uint32_t               offset[4]; /* Should match 'num' in actual definition */

    /* mem-resource definition */
    struct fw_rsc_carveout sh_mem_iv_inp;
    struct fw_rsc_carveout sh_mem_iv_out;
    struct fw_rsc_carveout sh_mem_gpio;
    struct fw_rsc_carveout sh_mem_util;
};

#endif /* SHEPHERD_PRU0_RESOURCE_TABLE_H_ */
