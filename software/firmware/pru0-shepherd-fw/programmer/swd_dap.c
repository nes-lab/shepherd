#include "programmer/swd_dap.h"
#include "programmer/transport.h"

static int swd_dp_write(swd_dp_reg_t reg, uint32_t val)
{
	return swd_transport_write(SWD_PORT_DP, reg, val, 5);
}
static int swd_dp_read(uint32_t *val, swd_dp_reg_t reg)
{
	return swd_transport_read(val, SWD_PORT_DP, reg, 5);
}

int swd_ap_write(swd_ap_reg_t reg, uint32_t val)
{
	return swd_transport_write(SWD_PORT_AP, reg, val, 5);
}
int swd_ap_read(uint32_t *val, swd_ap_reg_t reg)
{
	return swd_transport_read(val, SWD_PORT_AP, reg, 5);
}

int swd_ap_init()
{
	int rc;
	uint32_t data;

	if ((rc = swd_dp_write(DP_REG_ABORT, 0x0000001E)))
		return rc;
	if ((rc = swd_dp_write(DP_REG_SELECT, 0x0)))
		return rc;
	if ((rc = swd_dp_write(DP_REG_CTRLSTAT, 0x50000000)))
		return rc;

	unsigned int retries = 10;
	do {
		if ((rc = swd_dp_read(&data, DP_REG_CTRLSTAT)))
			return rc;
		retries--;
	} while ((data != 0xF0000000) && (data != 0xF0000040) && (retries > 0));

	if (retries == 0)
		return -1;

	if ((rc = swd_ap_write(AP_REG_CSW, 0x23000052)))
		return rc;

	return 0;
}

int swd_ap_exit()
{
	return swd_dp_write(DP_REG_CTRLSTAT, 0x0);
}
