#ifndef __PROG_SWD_DAP_H_
#define __PROG_SWD_DAP_H_

#include <stdint.h>

typedef enum {
	DP_REG_DPIDR = 0x0,
	DP_REG_ABORT = 0x0,
	DP_REG_CTRLSTAT = 0x4,
	DP_REG_DLCR = 0x4,
	DP_REG_SELECT = 0x8,
	DP_REG_RDBUFF = 0xC,
} swd_dp_reg_t;

typedef enum {
	AP_REG_CSW = 0x0,
	AP_REG_TAR = 0x4,
	AP_REG_DRW = 0xC,
	AP_REG_IDR = 0xFC,
} swd_ap_reg_t;

int swd_ap_init();
int swd_ap_exit();

int swd_dp_write(swd_dp_reg_t reg, uint32_t val);
int swd_dp_read(uint32_t *val, swd_dp_reg_t reg);

int swd_ap_write(swd_ap_reg_t reg, uint32_t val);
int swd_ap_read(uint32_t *val, swd_ap_reg_t reg);

#endif /* __PROG_SWD_DAP_H_ */
