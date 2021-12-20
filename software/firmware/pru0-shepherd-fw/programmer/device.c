#include <stddef.h>

#include "programmer/swd_dap.h"
#include "programmer/device.h"
#include "programmer/core_cm4.h"
#include "programmer/nrf52840.h"
#include "programmer/nrf52840_bitfields.h"

int mem_write(uint32_t addr, uint32_t data)
{
	int rc;

	if ((rc = swd_ap_write(AP_REG_TAR, addr)))
		return rc;
	if ((rc = swd_ap_write(AP_REG_DRW, data)))
		return rc;

	swd_ap_read(&data, AP_REG_DRW);
	return 0;
}

int mem_read(uint32_t *data, uint32_t addr)
{
	int rc;

	if ((rc = swd_ap_write(AP_REG_TAR, addr)))
		return rc;

	if ((rc = swd_ap_read(data, AP_REG_DRW)))
		return rc;

	return swd_ap_read(data, AP_REG_DRW);
}

int dev_halt()
{
	int rc = mem_write(CoreDebug_BASE + offsetof(CoreDebug_Type, DHCSR),
			   (0xA05F << CoreDebug_DHCSR_DBGKEY_Pos) | CoreDebug_DHCSR_C_HALT_Msk | CoreDebug_DHCSR_C_DEBUGEN_Msk);

	return rc;
}

int dev_continue()
{
	int rc = mem_write(CoreDebug_BASE + offsetof(CoreDebug_Type, DHCSR), (0xA05F << CoreDebug_DHCSR_DBGKEY_Pos) | CoreDebug_DHCSR_C_DEBUGEN_Msk);

	return rc;
}

int dev_reset()
{
	int rc;
	rc = mem_write(SCB_BASE + offsetof(SCB_Type, AIRCR), SCB_AIRCR_VECTKEY_Msk | SCB_AIRCR_SYSRESETREQ_Msk);
	return rc;
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

int nvm_wp_disable(void)
{
	int rc;
	rc = mem_write(NRF_NVMC_BASE + offsetof(NRF_NVMC_Type, CONFIG), NVMC_CONFIG_WEN_Msk);
	if (rc != 0)
		return rc;

	return nvm_wait(64);
}

int nvm_wp_enable(void)
{
	return mem_write(NRF_NVMC_BASE + offsetof(NRF_NVMC_Type, CONFIG), 0x0);
}

int nvm_erase(void)
{
	int rc;
	if ((rc = nvm_wait(256)))
		return rc;

	if ((rc = mem_write(NRF_NVMC_BASE + offsetof(NRF_NVMC_Type, ERASEALL), 0x1)))
		return rc;
	if ((rc = nvm_wait(2048)))
		return rc;
}

int nvm_write(uint32_t addr, uint32_t data)
{
	int rc;
	if ((rc = nvm_wait(256)))
		return rc;

	return mem_write(addr, data);
}
