#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include <pru_cfg.h>
#include <pru_iep.h>
#include <rsc_types.h>

#include "gpio.h"
#include "iep.h"
#include "intc.h"
#include "resource_table_def.h"
#include "stdint_fast.h"

#include "commons.h"
#include "hw_config.h"
#include "shared_mem.h"
#include "shepherd_config.h"

#include "msg_sys.h"
#include "programmer.h"


int main(void)
{
    /* COPY of pru0/main from here up to 'reset:' - except additional index-init */
    DEBUG_EVENT_STATE_3;

    /* Initialize struct-Members Part A, must come first - this blocks PRU1! */
    SHARED_MEM.cmp0_trigger_for_pru1 = 0u; // Reset Token-System to init-values
    SHARED_MEM.cmp1_trigger_for_pru1 = 0u;

    /* establish safety-boundary around critical sections */
    SHARED_MEM.canary1               = CANARY_VALUE_U32;
    SHARED_MEM.canary2               = CANARY_VALUE_U32;
    SHARED_MEM.canary3               = CANARY_VALUE_U32;

    /* Initialize all struct-Members Part B */
    SHARED_MEM.buffer_iv_inp_ptr     = (struct IVTraceInp *) resourceTable.shared_memory.pa;
    SHARED_MEM.buffer_iv_out_ptr =
            (struct IVTraceOut *) (resourceTable.shared_memory.pa + sizeof(struct IVTraceInp));
    SHARED_MEM.buffer_gpio_ptr =
            (struct GPIOTrace *) (resourceTable.shared_memory.pa + sizeof(struct IVTraceInp) +
                                  sizeof(struct IVTraceOut));
    SHARED_MEM.buffer_util_ptr =
            (struct UtilTrace *) (resourceTable.shared_memory.pa + sizeof(struct IVTraceInp) +
                                  sizeof(struct IVTraceOut) + sizeof(struct GPIOTrace));

    SHARED_MEM.buffer_size                         = resourceTable.shared_memory.len;
    SHARED_MEM.buffer_iv_inp_size                  = sizeof(struct IVTraceInp);
    SHARED_MEM.buffer_iv_out_size                  = sizeof(struct IVTraceOut);
    SHARED_MEM.buffer_gpio_size                    = sizeof(struct GPIOTrace);
    SHARED_MEM.buffer_util_size                    = sizeof(struct UtilTrace);

    SHARED_MEM.buffer_iv_inp_sys_idx               = IDX_OUT_OF_BOUND;
    SHARED_MEM.buffer_iv_inp_ptr->idx_sys          = IDX_OUT_OF_BOUND;
    SHARED_MEM.buffer_iv_inp_ptr->idx_pru          = IDX_OUT_OF_BOUND;
    SHARED_MEM.buffer_iv_out_ptr->idx_pru          = IDX_OUT_OF_BOUND;
    SHARED_MEM.buffer_gpio_ptr->idx_pru            = IDX_OUT_OF_BOUND;
    SHARED_MEM.buffer_util_ptr->idx_pru            = IDX_OUT_OF_BOUND;

    /* accumulated length is documented in resourceTable.shared_memory.len */

    SHARED_MEM.dac_auxiliary_voltage_raw           = 0u;
    SHARED_MEM.shp_pru_state                       = STATE_IDLE;
    SHARED_MEM.shp_pru0_mode                       = MODE_NONE;

    SHARED_MEM.last_sync_timestamp_ns              = 0u;
    SHARED_MEM.next_sync_timestamp_ns              = 0u;

    SHARED_MEM.buffer_iv_inp_idx                   = 0u;
    SHARED_MEM.buffer_iv_out_idx                   = 0u;
    SHARED_MEM.buffer_gpio_idx                     = 0u;
    SHARED_MEM.buffer_util_idx                     = 0u;

    SHARED_MEM.gpio_pin_state                      = 0u;

    SHARED_MEM.vsource_power_good_trigger_for_pru1 = false;
    SHARED_MEM.vsource_power_good_pins_state       = 0b00u;

    /* minimal init for these structs to make them safe */
    /* NOTE: more inits are done in kernel */
    SHARED_MEM.converter_settings.converter_mode   = 0u;
    SHARED_MEM.harvester_settings.algorithm        = 0u;
    SHARED_MEM.programmer_ctrl.state               = PRG_STATE_IDLE;
    SHARED_MEM.programmer_ctrl.target              = PRG_TARGET_NONE;

    DEBUG_EVENT_STATE_0;

    msgsys_init();

    /* Allow OCP primary port access by the PRU so the PRU can read external memories */
    CT_CFG.SYSCFG_bit.STANDBY_INIT   = 0u;

    /* allow PRU1 to enter event-loop */
    SHARED_MEM.cmp0_trigger_for_pru1 = 1u;

reset:
    DEBUG_EVENT_STATE_3;

    msgsys_send(MSG_STATUS_RESTARTING_ROUTINE, 0u, SHARED_MEM.programmer_ctrl.state);
    SHARED_MEM.pru0_ns_per_sample        = IDX_OUT_OF_BOUND;

    SHARED_MEM.vsource_skip_gpio_logging = true;

    SHARED_MEM.shp_pru_state             = STATE_IDLE;

    DEBUG_EVENT_STATE_0;

    while (SHARED_MEM.shp_pru_state == STATE_IDLE)
    {
        if (SHARED_MEM.programmer_ctrl.state == PRG_CMD_START)
        {
            DEBUG_EVENT_STATE_3;
            programmer(&SHARED_MEM.programmer_ctrl, (uint32_t *) resourceTable.shared_memory.pa);
            DEBUG_EVENT_STATE_0;
        }
    }

    goto reset;
}
