#include "programmer/swd_dap.h"
#include "programmer/swd_transport.h"

int dp_write(dp_reg_t reg, uint32_t val) { return transport_write(SWD_PORT_DP, reg, val, 5); }

int ap_write(ap_reg_t reg, uint32_t val) { return transport_write(SWD_PORT_AP, reg, val, 5); }

int dp_read(uint32_t *dst, dp_reg_t reg) { return transport_read(dst, SWD_PORT_DP, reg, 5); }

int ap_read(uint32_t *dst, ap_reg_t reg) { return transport_read(dst, SWD_PORT_AP, reg, 5); }

int ap_init()
{
    int      rc;
    uint32_t data;

    if ((rc = dp_write(DP_REG_ABORT, 0x0000001E))) return rc;
    if ((rc = dp_write(DP_REG_SELECT, 0x0))) return rc;
    if ((rc = dp_write(DP_REG_CTRLSTAT, 0x50000000))) return rc;

    unsigned int retries = 10;
    do {
        if ((rc = dp_read(&data, DP_REG_CTRLSTAT))) return rc;
        retries--;
    }
    while ((data != 0xF0000000) && (data != 0xF0000040) && (retries > 0));
    if (retries == 0) return -1;

    if ((rc = ap_write(AP_REG_CSW, 0x23000052))) return rc;

    return 0;
}

int ap_exit() { return dp_write(DP_REG_CTRLSTAT, 0x0); }
