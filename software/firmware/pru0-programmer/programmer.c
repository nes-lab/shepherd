#include "programmer.h"

// select a primary programming-mode when none is chosen
#if !(defined(SWD_SUPPORT) || defined(SBW_SUPPORT))
  #define SWD_SUPPORT
#endif

#include "delay.h"
#include "device.h"
#include "intelhex.h"
#include "msg_sys.h"
#include "shared_mem.h"
#include "swd_transport.h"
#include "sys_gpio.h"
#include <stdint.h>
#include <stdlib.h>

/* Writes block from hex file to target via driver */
int write_to_target(device_driver_t *drv, const ihex_mem_block_t *const block)
{
    uint8_t *src     = block->data;
    uint32_t addr    = block->address;

    /* Number of words in this block */
    uint32_t n_words = block->len / drv->word_width_bytes;

    for (uint32_t i = 0; i < n_words; i++)
    {
        uint32_t data = *((uint32_t *) src);
        if (drv->write(data, addr) != DRV_SUCCESS)
        {
            msgsys_send(MSG_PGM_ERROR_WRITE, addr, data);
            return PRG_ERR_WRITE;
        }
        if (drv->verify(data, addr) != DRV_SUCCESS)
        {
            // TODO: maybe add switch to read-back & send-out data
            msgsys_send(MSG_PGM_ERROR_VERIFY, addr, data);
            return PRG_ERR_VERIFY;
        }

        src += drv->word_width_bytes;
        addr += drv->word_width_bytes;
    }
    return 0;
}

void programmer(volatile struct ProgrammerCtrl *const pctrl, volatile const uint32_t *const fw_data)
{
    device_driver_t *drv = NULL;
    int              ret;
    ihex_mem_block_t block;
    // TODO: pctrl -> PGM_CFG - HARDCODE
    pctrl->state = PRG_STATE_INITIALIZING;

    ihex_reader_init((char *) fw_data);
    SHARED_MEM.pru_applied_settings = true;
    // -> apply could be done later (after erase), but there is no point
    //    doing it here avoids error-prints by sheep

#ifdef SWD_SUPPORT
    if (pctrl->target == PRG_TARGET_NRF52) drv = &nrf52_driver;
#endif
#ifdef SBW_SUPPORT
    if (pctrl->target == PRG_TARGET_MSP430) drv = &msp430fr_driver;
#endif
    else if (pctrl->target == PRG_TARGET_DUMMY) drv = &dummy_driver;
    else
    {
        pctrl->state = PRG_ERR_GENERIC;
        goto exit;
    }

    pctrl->state = PRG_STATE_CONNECTING;
    if (drv->open(pctrl->pin_tck, pctrl->pin_tdio, pctrl->pin_dir_tdio, pctrl->datarate) !=
        DRV_SUCCESS)
    {
        pctrl->state = PRG_ERR_OPEN;
#ifdef SBW_SUPPORT
        delay_ms(1200u); // do NOT exit on error, just highlevel print
#else
        goto exit;
#endif
    }

    pctrl->state = PRG_STATE_ERASING;
    if (drv->erase() != DRV_SUCCESS)
    {
        pctrl->state = PRG_ERR_ERASE;
        goto exit;
    }

    /* State specifies number of bytes written to target */
    pctrl->state = 0;

    int rc;
    /* Iterate content of hex file entry by entry */
    while (((ret = ihex_reader_get(&block)) == 0) && (SHARED_MEM.shp_pru_state == STATE_IDLE))
    {
        /* Write block data to target device memory */
        if ((rc = write_to_target(drv, &block)) != 0)
        {
            pctrl->state = rc;
            goto exit;
        }
        /* Show progress by incrementing state by number of bytes written */
        pctrl->state += block.len;
    }
    if (ret != IHEX_RET_DONE)
    {
        msgsys_send(MSG_PGM_ERROR_PARSE, ret, 0u);
        pctrl->state = PRG_ERR_PARSE;
        goto exit;
    }

    /* signal py-interface to exit / power down shepherd */
    pctrl->state = PRG_STATE_IDLE;

exit:
    if (drv != NULL) drv->close();
}
