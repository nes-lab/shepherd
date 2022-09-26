#include <stddef.h>

#include "programmer/core_cm4.h"
#include "programmer/device.h"
#include "programmer/nrf52840.h"
#include "programmer/nrf52840_bitfields.h"
#include "programmer/swd_dap.h"
#include "programmer/swd_transport.h"

/**
 * Writes a word to the specified address in memory. Note that this routine can NOT
 * be used to write to non-volatile flash memory.
 *
 * @param addr target memory address
 * @param data word to be written
 */
static int mem_write(uint32_t addr, uint32_t data)
{
    int rc;

    if ((rc = ap_write(AP_REG_TAR, addr)))
        return rc;
    if ((rc = ap_write(AP_REG_DRW, data)))
        return rc;

    /* dummy read to make sure previous transfer has finished */
    dp_read(&data, DP_REG_RDBUFF);
    return 0;
}

/**
 * Reads a word from the specified address in memory. Can be used for both, volatile memory and
 * non-volatile flash memory.
 *
 * @param dst pointer to destination
 * @param addr target memory address
 */
static int mem_read(uint32_t *dst, uint32_t addr)
{
    int rc;

    if ((rc = ap_write(AP_REG_TAR, addr)))
        return rc;

    if ((rc = ap_read(dst, AP_REG_DRW)))
        return rc;

    /* dummy read to make sure previous transfer has finished */
    return ap_read(dst, AP_REG_DRW);
}

/* Halts the core */
static int dev_halt()
{
    int rc = mem_write(CoreDebug_BASE + offsetof(CoreDebug_Type, DHCSR),
                       (0xA05Fu << CoreDebug_DHCSR_DBGKEY_Pos) | CoreDebug_DHCSR_C_HALT_Msk | CoreDebug_DHCSR_C_DEBUGEN_Msk);

    return rc;
}

/* Continues execution */
static int dev_continue()
{
    int rc;
    if ((rc = mem_write(CoreDebug_BASE + offsetof(CoreDebug_Type, DEMCR), 0x0)))
        return rc;

    return mem_write(CoreDebug_BASE + offsetof(CoreDebug_Type, DHCSR), (0xA05Fu << CoreDebug_DHCSR_DBGKEY_Pos) | CoreDebug_DHCSR_C_DEBUGEN_Msk);
}

/* Halts and resets the core */
static int dev_reset_halt()
{
    int rc;

    rc = mem_write(CoreDebug_BASE + offsetof(CoreDebug_Type, DHCSR),
                   (0xA05Fu << CoreDebug_DHCSR_DBGKEY_Pos) | CoreDebug_DHCSR_C_HALT_Msk | CoreDebug_DHCSR_C_DEBUGEN_Msk);
    if (rc != 0)
        return rc;

    rc = mem_write(CoreDebug_BASE + offsetof(CoreDebug_Type, DEMCR), CoreDebug_DEMCR_VC_CORERESET_Msk);
    if (rc != 0)
        return rc;

    rc = mem_write(SCB_BASE + offsetof(SCB_Type, AIRCR), (0x05FA << SCB_AIRCR_VECTKEY_Pos) | SCB_AIRCR_SYSRESETREQ_Msk);
    if (rc != 0)
        return rc;

    uint32_t data;
    for (unsigned int i = 0; i < 5; i++)
    {
        if ((rc = mem_read(&data, CoreDebug_BASE + offsetof(CoreDebug_Type, DHCSR))))
            return rc;

        if ((rc = dp_read(&data, DP_REG_RDBUFF)))
            return rc;

        if (data == 0x0)
            return 0;
    }
    return -1;
}

/* Waits for non-volatile memory controller to be ready for a new write */
static int nvm_wait(unsigned int retries)
{
    int      rc;
    uint32_t ready;
    do {
        if ((rc = mem_read(&ready, NRF_NVMC_BASE + offsetof(NRF_NVMC_Type, READY))))
            return rc;
        if (--retries == 0)
            return -1;
    }
    while (ready != 1);
    return 0;
}

/* Disables write-protection of non-volatile flash memory */
static int nvm_wp_disable(void)
{
    int rc;
    rc = mem_write(NRF_NVMC_BASE + offsetof(NRF_NVMC_Type, CONFIG), NVMC_CONFIG_WEN_Msk);
    if (rc != 0)
        return rc;

    return nvm_wait(64);
}

/* Enables write-protection of non-volatile flash memory */
static int nvm_wp_enable(void)
{
    return mem_write(NRF_NVMC_BASE + offsetof(NRF_NVMC_Type, CONFIG), 0x0);
}

/* Erases the whole flash */
static int nvm_erase(void)
{
    int rc;
    if ((rc = nvm_wait(64)))
        return rc;

    if ((rc = mem_write(NRF_NVMC_BASE + offsetof(NRF_NVMC_Type, ERASEALL), 0x1)))
        return rc;

    /* Wait until the nvm controller has finished the operation */
    return nvm_wait(1024);
}

/**
 * Writes a word to the non-volatile flash memory
 *
 * @param target memory address
 * @param data word to be written
 *
 */
static int nvm_write(uint32_t dst, uint32_t data)
{
    int rc;
    if ((rc = nvm_wait(64)))
        return rc;

    return mem_write(dst, data);
}

/**
 * Verifies a word at the specified address in memory.
 *
 * @param addr target memory address
 * @param data expected memory content
 */
static int verify(uint32_t address, uint32_t data)
{
    uint32_t read_back;
    if (mem_read(&read_back, address) != DRV_ERR_OK)
        return DRV_ERR_GENERIC;
    if (data == read_back)
        return DRV_ERR_OK;
    else
        return DRV_ERR_VERIFY;
}

/**
 * Prepares the nRF52 for access. After execution, the core should be reset, halted
 * and ready to receive writes to the non-volatile flash memory.
 *
 * @param pin_swdclk pin number for SWDCLK signal. Note: Only supports pins of GPIO port 0.
 * @param pin_swdio pin number for SWDIO signal. Note: Only supports pins of GPIO port 0.
 * @param f_clk frequency of SWDCLK signal
 *
 * @returns DRV_ERR_OK on success
 */
static int open(unsigned int pin_swdclk, unsigned int pin_swdio, unsigned int f_clk)
{
    uint32_t data;

    if (transport_init(pin_swdclk, pin_swdio, f_clk))
        return DRV_ERR_GENERIC;
    if (transport_reset())
        return DRV_ERR_GENERIC;
    /* Dummy read */
    if (dp_read(&data, DP_REG_DPIDR))
        return DRV_ERR_GENERIC;

    if (ap_init())
        return DRV_ERR_GENERIC;
    if (dev_reset_halt())
        return DRV_ERR_GENERIC;
    if (nvm_wp_disable())
        return DRV_ERR_GENERIC;
    return DRV_ERR_OK;
}

/* Disables access to and communication with the nRF52. After this, the core should be reset and running */
static int close(void)
{
    nvm_wp_enable();
    dev_continue();
    ap_exit();
    transport_release();
    return DRV_ERR_OK;
}

device_driver_t nrf52_driver = {
        .open             = open,
        .erase            = nvm_erase,
        .write            = nvm_write,
        .verify           = verify,
        .close            = close,
        .read             = mem_read,
        .word_width_bytes = 4,
};
