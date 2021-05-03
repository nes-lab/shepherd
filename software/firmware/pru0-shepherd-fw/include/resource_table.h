#ifndef _RESOURCE_TABLE_H_
#define _RESOURCE_TABLE_H_

#include <rsc_types.h>

struct my_resource_table {
	struct resource_table base;

	uint32_t offset[2]; /* Should match 'num' in actual definition */

	/* intc definition */
	struct fw_rsc_custom pru_ints;
	/* mem-resource definition */
	struct fw_rsc_carveout shared_mem;
};

#endif /* _RESOURCE_TABLE_H_ */
