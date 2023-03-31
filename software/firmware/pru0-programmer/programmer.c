#include "programmer.h"

// select a primary programming-mode when none is chosen
#if !(defined(SWD_SUPPORT) || defined(SBW_SUPPORT))
  #define SWD_SUPPORT
#endif

#include "device.h"
#include "intelhex.h"
#include "swd_transport.h"
#include "sys_gpio.h"
#include <stdint.h>

/* Writes block from hex file to target via driver */
int write_to_target(device_driver_t *drv, ihex_mem_block_t *block)
{
    uint8_t *src     = block->data;
    uint32_t addr    = block->address;

    /* Number of words in this block */
    uint32_t n_words = block->len / drv->word_width_bytes;

    for (uint32_t i = 0; i < n_words; i++)
    {
        uint32_t data = *((uint32_t *) src);
        if (drv->write(data, addr) != DRV_ERR_OK) return PRG_STATE_ERR_WRITE;
        if (drv->verify(data, addr) != DRV_ERR_OK) return PRG_STATE_ERR_VERIFY;

        src += drv->word_width_bytes;
        addr += drv->word_width_bytes;
    }
    return 0;
}

void programmer(volatile struct SharedMem *const    shared_mem,
                volatile struct SampleBuffer *const buffers_far)
{
    device_driver_t                      *drv;
    int                                   ret;
    ihex_mem_block_t                      block;

    /* create more convenient access to structs */
    const uint32_t *const                 fw = (uint32_t *) buffers_far;
    volatile struct ProgrammerCtrl *const pc =
            (struct ProgrammerCtrl *) &shared_mem->programmer_ctrl;

    pc->state = PRG_STATE_INITIALIZING;

    /* check for validity */
    if ((pc->datasize >= shared_mem->mem_size) ||
        (pc->pin_tck == pc->pin_tdio) ||
        (pc->pin_tck == pc->pin_dir_tdio) ||
        (pc->pin_tdio == pc->pin_dir_tdio) ||
        (pc->datarate > 1000000))
    {
        pc->state = PRG_STATE_ERR_GENERIC;
        return;
    }

#ifdef SWD_SUPPORT
    if (pc->target == PRG_TARGET_NRF52) drv = &nrf52_driver;
#endif
#ifdef SBW_SUPPORT
    if (pc->target == PRG_TARGET_MSP430) drv = &msp430fr_driver;
#endif
    if (pc->target == PRG_TARGET_DUMMY) drv = &dummy_driver;
    else
    {
        pc->state = PRG_STATE_ERR_GENERIC;
        goto exit;
    }

    if (drv->open(pc->pin_tck, pc->pin_tdio, pc->pin_dir_tdio, pc->datarate) != DRV_ERR_OK)
    {
        pc->state = PRG_STATE_ERR_OPEN;
        goto exit;
    }

    if (drv->erase() != DRV_ERR_OK)
    {
        pc->state = PRG_STATE_ERR_ERASE;
        goto exit;
    }

    ihex_reader_init((char *) fw);

    /* State specifies number of bytes written to target */
    pc->state = 0;

    int rc;
    /* Iterate content of hex file entry by entry */
    while ((ret = ihex_reader_get(&block)) == 0)
    {
        /* Write block data to target device memory */
        if ((rc = write_to_target(drv, &block)) != 0)
        {
            pc->state = rc;
            goto exit;
        }
        /* Show progress by incrementing state by number of bytes written */
        pc->state += block.len;
    }
    if (ret != IHEX_RET_DONE)
    {
        pc->state = PRG_STATE_ERR_PARSE;
        goto exit;
    }

    /* signal py-interface to exit / power down shepherd */
    pc->state = PRG_STATE_IDLE;

exit:
    drv->close();
}
