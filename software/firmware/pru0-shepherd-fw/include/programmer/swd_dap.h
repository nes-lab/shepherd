#ifndef __PROG_SWD_DAP_H_
#define __PROG_SWD_DAP_H_

#include <stdint.h>

/* Register address map of Debug Port */
typedef enum
{
    DP_REG_DPIDR    = 0x0,
    DP_REG_ABORT    = 0x0,
    DP_REG_CTRLSTAT = 0x4,
    DP_REG_DLCR     = 0x4,
    DP_REG_SELECT   = 0x8,
    DP_REG_RDBUFF   = 0xC,
} dp_reg_t;

/* Register address map of Memory Access Point */
typedef enum
{
    AP_REG_CSW = 0x0,
    AP_REG_TAR = 0x4,
    AP_REG_DRW = 0xC,
    AP_REG_IDR = 0xFC,
} ap_reg_t;

/**
 * Writes a word to the Debug Port.
 *
 * @param reg destination register
 * @param val word to be written
 */
int dp_write(dp_reg_t reg, uint32_t val);

/**
 * Writes a word to the Memory Access Port.
 *
 * @param reg destination register
 * @param val word to be written
 */
int ap_write(ap_reg_t reg, uint32_t val);

/**
 * Reads a word from the Debug Port.
 *
 * @param dst pointer to destination
 * @param reg source register
 */
int dp_read(uint32_t *dst, dp_reg_t reg);

/**
 * Reads a word from the Memory Access Port.
 *
 * @param dst pointer to destination
 * @param reg source register
 */
int ap_read(uint32_t *dst, ap_reg_t reg);

/* Initializes and enables access to the Memory Access Port */
int ap_init();

/* Closes and disables access to the Memory Access Port */
int ap_exit();

#endif /* __PROG_SWD_DAP_H_ */
