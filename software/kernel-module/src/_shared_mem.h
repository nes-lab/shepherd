#ifndef _SHARED_MEM_H
#define _SHARED_MEM_H

#include <linux/types.h>
#include "_commons.h"

struct SharedMem
{
    volatile uint32_t                 shp_pru_state;
    /* Stores the mode, e.g. harvester or emulator */
    volatile uint32_t                 shp_pru0_mode;
    /* Physical address of shared area in DDR RAM, that is used to exchange data between user space and PRUs */
    volatile uint32_t                *far_mem_ptr; // TODO: still needed?
    /* Length of shared area in DDR RAM */
    volatile uint32_t                 far_mem_size;
    /**
    * Parameters of buffer structures in current far & slow RAM.
    * Only PRU0 knows about addresses.
    */
    volatile struct IVTrace          *buffer_iv_ptr;
    volatile struct GPIOTrace        *buffer_gpio_ptr;
    volatile struct UtilTrace        *buffer_util_ptr;
    /* internal fast index to far-buffers */
    volatile uint32_t                 buffer_iv_idx;   // write by pru0 only
    volatile uint32_t                 buffer_gpio_idx; // write by pru1 only
    volatile uint32_t                 buffer_util_idx; // write by pru1 only
    /* size of both buffers */
    volatile uint32_t                 buffer_iv_size;
    volatile uint32_t                 buffer_gpio_size;
    volatile uint32_t                 buffer_util_size; // TODO: hardcoding seems better
    /* Allows setting a fixed voltage for the seconds DAC-Output (Channel A),
     * TODO: this has to be optimized, allow better control (off, link to ch-b, change NOW) */
    volatile uint32_t                 dac_auxiliary_voltage_raw;
    /* ADC calibration settings */
    volatile struct CalibrationConfig calibration_settings;
    /* This structure defines all settings of virtual converter emulation*/
    volatile struct ConverterConfig   converter_settings;
    volatile struct HarvesterConfig   harvester_settings;
    /* settings for programmer-subroutines */
    volatile struct ProgrammerCtrl    programmer_ctrl;
    /* Msg-System-replacement for slow rpmsg (check 640ns, receive 2820 on pru0 and 4820ns on pru1) */
    volatile struct ProtoMsg          pru0_msg_inbox;
    volatile struct ProtoMsg          pru0_msg_outbox;
    volatile struct ProtoMsg          pru0_msg_error;
    volatile struct SyncMsg           pru1_sync_inbox;
    volatile struct ProtoMsg          pru1_sync_outbox;
    volatile struct ProtoMsg          pru1_msg_error;
    /* safety */
    volatile uint32_t                 canary;
    /* NOTE: End of region (also) controlled by kernel module */
} __attribute__((packed));

/* This is external to expose some attributes through sysfs */
extern void __iomem *pru_shared_mem_io;

#endif //_SHARED_MEM_H
