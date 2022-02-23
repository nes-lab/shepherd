#include <stddef.h>

#include "programmer/swd_dap.h"
#include "programmer/swd_transport.h"
#include "programmer/device.h"
#include "programmer/core_cm4.h"
#include "programmer/nrf52840.h"
#include "programmer/nrf52840_bitfields.h"

#include "programmer/hal.h"

int mem_write(uint32_t addr, uint32_t data)
{
	int rc;

	if ((rc = ap_write(AP_REG_TAR, addr)))
		return rc;
	if ((rc = ap_write(AP_REG_DRW, data)))
		return rc;

	dp_read(&data, DP_REG_RDBUFF);
	return 0;
}

int mem_read(uint32_t *data, uint32_t addr)
{
	int rc;

	if ((rc = ap_write(AP_REG_TAR, addr)))
		return rc;

	if ((rc = ap_read(data, AP_REG_DRW)))
		return rc;

	return ap_read(data, AP_REG_DRW);
}

int dev_halt()
{
	int rc = mem_write(CoreDebug_BASE + offsetof(CoreDebug_Type, DHCSR),
			   (0xA05Fu << CoreDebug_DHCSR_DBGKEY_Pos) | CoreDebug_DHCSR_C_HALT_Msk | CoreDebug_DHCSR_C_DEBUGEN_Msk);

	return rc;
}

int dev_continue()
{
	int rc;
	if ((rc = mem_write(CoreDebug_BASE + offsetof(CoreDebug_Type, DEMCR), 0x0)))
		return rc;

	return mem_write(CoreDebug_BASE + offsetof(CoreDebug_Type, DHCSR), (0xA05Fu << CoreDebug_DHCSR_DBGKEY_Pos) | CoreDebug_DHCSR_C_DEBUGEN_Msk);
}

int dev_reset_halt()
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
	for (unsigned int i = 0; i < 5; i++) {
		if ((rc = mem_read(&data, CoreDebug_BASE + offsetof(CoreDebug_Type, DHCSR))))
			return rc;

		if ((rc = dp_read(&data, DP_REG_RDBUFF)))
			return rc;

		if (data == 0x0)
			return 0;
	}
	return -1;
}

static int nvm_wait(unsigned int retries)
{
	int rc;
	uint32_t ready;
	do {
		if ((rc = mem_read(&ready, NRF_NVMC_BASE + offsetof(NRF_NVMC_Type, READY))))
			return rc;
		if (--retries == 0)
			return -1;
	} while (ready != 1);
	return 0;
}

static int nvm_wp_disable(void)
{
	int rc;
	rc = mem_write(NRF_NVMC_BASE + offsetof(NRF_NVMC_Type, CONFIG), NVMC_CONFIG_WEN_Msk);
	if (rc != 0)
		return rc;

	return nvm_wait(64);
}

static int nvm_wp_enable(void)
{
	return mem_write(NRF_NVMC_BASE + offsetof(NRF_NVMC_Type, CONFIG), 0x0);
}

static int nvm_erase(void)
{
	int rc;
	if ((rc = nvm_wait(64)))
		return rc;

	if ((rc = mem_write(NRF_NVMC_BASE + offsetof(NRF_NVMC_Type, ERASEALL), 0x1)))
		return rc;

	return nvm_wait(1024);
}

static int nvm_write(uint32_t addr, uint32_t data)
{
	int rc;
	if ((rc = nvm_wait(64)))
		return rc;

	return mem_write(addr, data);
}

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

static int close(void)
{
	nvm_wp_enable();
	dev_continue();
	ap_exit();
	transport_release();
	return DRV_ERR_OK;
}

device_driver_t nrf52_driver = { .open = open, .erase = nvm_erase, .write = nvm_write, .close = close, .read = mem_read, .word_width = 32 };
