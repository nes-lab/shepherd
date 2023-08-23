#include <stddef.h>

//#include "delay.h"
#include "device.h"

static int mem_read(uint32_t *const dst, uint32_t address)
{
    if (*dst + address == 0u) return DRV_ERR_GENERIC;
    *dst = address;
    //delay_us(1);
    return DRV_ERR_OK;
}

static int mem_erase(void)
{
    //delay_ms(10);
    return DRV_ERR_OK;
}

static int mem_write(uint32_t data, uint32_t address)
{
    if (address + data == 0u) return DRV_ERR_GENERIC;
    //delay_us(50);
    return DRV_ERR_OK;
}

static int verify(uint32_t data, uint32_t address)
{
    if (address + data == 0u) return DRV_ERR_GENERIC;
    //delay_us(5);
    return DRV_ERR_OK;
}

static int open(const uint8_t pin_swd_clk, const uint8_t pin_swd_io, const uint8_t pin_swd_dir,
                const uint32_t f_clk)
{
    if (pin_swd_clk + pin_swd_io + pin_swd_dir + f_clk == 0u) return DRV_ERR_GENERIC;
    return DRV_ERR_OK;
}

static int      close(void) { return DRV_ERR_OK; }

device_driver_t dummy_driver = {
        .open             = open,
        .erase            = mem_erase,
        .write            = mem_write,
        .verify           = verify,
        .close            = close,
        .read             = mem_read,
        .word_width_bytes = 4u,
};
