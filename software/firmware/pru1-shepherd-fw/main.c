#include <gpio.h>
#include <pru_cfg.h>
#include <pru_iep.h>
#include <pru_intc.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "iep.h"
#include "intc.h"
#include "msg_sys.h"

#include "commons.h"
#include "debug_routines.h"
#include "resource_table.h"
#include "shared_mem.h"
#include "shepherd_config.h"
#include "stdint_fast.h"

/* The Arm to Host interrupt for the timestamp event is mapped to Host interrupt 0 -> Bit 30 (see resource_table.h) */
#define HOST_INT_TIMESTAMP_MASK (1U << 30U)
// TODO: is bit r31.31 still important?

// both pins have a LED
#define DEBUG_PIN0_MASK         BIT_SHIFT(P8_28)
#define DEBUG_PIN1_MASK         BIT_SHIFT(P8_30)

#define GPIO_BATOK              BIT_SHIFT(P8_29)
#define GPIO_BATOK_POS          (9u)

#define GPIO_MASK               (0x03FF)

#define SANITY_CHECKS           (0) // warning: costs performance, but is helpful for dev / debugging

/* overview for pin-mirroring - HW-Rev2.4b

pru_reg     name            BB_pin	sys_pin sys_reg
r31_00      TARGET_GPIO0    P8_45	P8_14, g0[26] -> 26
r31_01      TARGET_GPIO1    P8_46	P8_17, g0[27] -> 27
r31_02      TARGET_GPIO2    P8_43	P8_16, g1[14] -> 46
r31_03      TARGET_GPIO3    P8_44	P8_15, g1[15] -> 47
r31_04      TARGET_GPIO4    P8_41	P8_26, g1[29] -> 61
r31_05      TARGET_GPIO5    P8_42	P8_36, g2[16] -> 80
r31_06      TARGET_GPIO6    P8_39	P8_34, g2[17] -> 81
r31_07      TARGET_UART_RX  P8_40	P9_26, g0[14] -> 14
r31_08      TARGET_UART_TX  P8_27	P9_24, g0[15] -> 15
r30_09/out  TARGET_BAT_OK   P8_29	-

Note: this table is copied (for hdf5-reference) in commons.py
*/

enum SyncState
{
    IDLE,
    REPLY_PENDING
};


static inline bool_ft receive_sync_reply(struct SyncMsg *const msg)
{

    if (msgsys_receive(msg))
    {
        if (msg->type == MSG_TEST_ROUTINE)
        {
            // pipeline-test for msg-system
            msgsys_send_status(MSG_TEST_ROUTINE, SHARED_MEM.pru1_sync_inbox.sync_interval_ticks,
                               0u);
            return 0u;
        }

#if (SANITY_CHECKS > 0u)
        // TODO: move this to kernel
        if (msg->sync_interval_ticks > SYNC_INTERVAL_TICKS + (SYNC_INTERVAL_TICKS >> 3))
        {
            //"Recv_CtrlReply -> sync_interval_ticks too high");
            msgsys_send_status(MSG_ERR_VALUE, 11u, 0u);
        }
        if (msg->sync_interval_ticks < SYNC_INTERVAL_TICKS - (SYNC_INTERVAL_TICKS >> 3))
        {
            //"Recv_CtrlReply -> sync_interval_ticks too low");
            msgsys_send_status(MSG_ERR_VALUE, 12u, 0u);
        }
        if (msg->sample_interval_ticks > SAMPLE_INTERVAL_TICKS + 100)
        {
            //"Recv_CtrlReply -> sample_interval_ticks too high");
            msgsys_send_status(MSG_ERR_VALUE, 13u, 0u);
        }
        if (msg->sample_interval_ticks < SAMPLE_INTERVAL_TICKS - 100)
        {
            //"Recv_CtrlReply -> sample_interval_ticks too low");
            msgsys_send_status(MSG_ERR_VALUE, 14u, 0u);
        }
        if (msg->compensation_steps > SAMPLES_PER_SYNC)
        {
            //"Recv_CtrlReply -> compensation_steps too high");
            msgsys_send_status(MSG_ERR_VALUE, 15u, 0u);
        }

        static uint64_t prev_timestamp_ns = 0;
        const uint64_t  time_diff         = msg->next_timestamp_ns - prev_timestamp_ns;
        prev_timestamp_ns                 = msg->next_timestamp_ns;
        if ((time_diff != SYNC_INTERVAL_NS) && (prev_timestamp_ns > 0))
        {
            if (msg->next_timestamp_ns == 0)
                // "Recv_CtrlReply -> next_timestamp_ns is zero");
                msgsys_send_status(MSG_ERR_VALUE, 16u, 0u);
            else if (time_diff > SYNC_INTERVAL_NS + 5000000u)
                // "Recv_CtrlReply -> next_timestamp_ns is > 105 ms");
                msgsys_send_status(MSG_ERR_VALUE, 17u, 0u);
            else if (time_diff < SYNC_INTERVAL_NS - 5000000u)
                // "Recv_CtrlReply -> next_timestamp_ns is < 95 ms");
                msgsys_send_status(MSG_ERR_VALUE, 18u, 0u);
            else
                // "Recv_CtrlReply -> timestamp-jump was not 100 ms");
                msgsys_send_status(MSG_ERR_VALUE, 19u, 0u);
        }
#endif
        return 1u;
    }
    return 0u;
}

/*
 * Here, we sample the GPIO pins from a connected sensor node. We repeatedly
 * poll the state via the R31 register and keep the last state in a static
 * variable. Once we detect a change, the new value (V1=4bit, V2=10bit) is written to the
 * corresponding buffer (which is managed by PRU0). The tricky part is the
 * synchronization between the PRUs to avoid inconsistent state, while
 * minimizing sampling delay
 */
static inline void check_gpio(const uint32_t last_sample_ticks)
{
    static uint32_t prev_gpio_status = 0x00;

    /*
	* Only continue if shepherd is running
	*/
    if (SHARED_MEM.shp_pru_state != STATE_RUNNING)
    {
        prev_gpio_status = 0x00;
        SHARED_MEM.gpio_pin_state =
                (read_r31() | (SHARED_MEM.vsource_batok_pin_value << GPIO_BATOK_POS)) & GPIO_MASK;
        return;
    }
    else if (SHARED_MEM.vsource_skip_gpio_logging) { return; }

    // batOK is on r30 (output), but that does not mean it is in R31
    // -> workaround: splice in SHARED_MEM.vsource_batok_pin_value
    const uint32_t gpio_status =
            (read_r31() | (SHARED_MEM.vsource_batok_pin_value << GPIO_BATOK_POS)) & GPIO_MASK;
    const uint32_t gpio_diff = gpio_status ^ prev_gpio_status;

    prev_gpio_status         = gpio_status;

    if (gpio_diff > 0)
    {
        DEBUG_GPIO_STATE_2;
        // local copy reduces reads to far-ram to current minimum
        volatile struct GPIOTrace *const buf_gpio = SHARED_MEM.buffer_gpio_ptr;
        const uint32_t                   cIDX     = SHARED_MEM.buffer_gpio_idx;

        /* Ticks since we've taken the last sample */
        const uint32_t ticks_since_last_sample    = CT_IEP.TMR_CNT - last_sample_ticks;
        /* Calculate final timestamp of gpio event */
        const uint64_t gpio_timestamp_ns =
                SHARED_MEM.last_sample_timestamp_ns + TICK_INTERVAL_NS * ticks_since_last_sample;
        // TODO: maybe just store TS and counter or even u32 sync-counter + u32 tick_counter

        buf_gpio->timestamp_ns[cIDX] = gpio_timestamp_ns;
        buf_gpio->bitmask[cIDX]      = (uint16_t) gpio_status;

        if (cIDX >= BUFFER_GPIO_SIZE - 1u)
        {
            buf_gpio->idx_pru          = 0u;
            SHARED_MEM.buffer_gpio_idx = 0u;
        }
        else
        {
            buf_gpio->idx_pru          = cIDX + 1u;
            SHARED_MEM.buffer_gpio_idx = cIDX + 1u;
        }
    }
}


/* TODO: update comments, they seem outdated
 * The firmware for synchronization/sample timing is based on a simple
 * event loop. There are three events: 1) Interrupt from Linux kernel module
 * 2) Local IEP timer wrapped 3) Local IEP timer compare for sampling
 *
 * Event 1:
 * The kernel module periodically timestamps its own clock and immediately
 * triggers an interrupt to PRU1. On reception of that interrupt we have
 * to timestamp our local IEP clock. We then send the local timestamp to the
 * kernel module as an RPMSG message. The kernel module runs a PI control loop
 * that minimizes the phase shift (and frequency deviation) by calculating a
 * correction factor that we apply to the base period of the IEP clock. This
 * resembles a Phase-Locked-Loop system. The kernel module sends the resulting
 * correction factor to us as an RPMSG. Ideally, Event 1 happens at the same
 * time as Event 2, i.e. our local clock should wrap at exactly the same time
 * as the Linux host clock. However, due to phase shifts and kernel timer
 * jitter, the two events typically happen with a small delay and in arbitrary
 * order. However, we would
 *
 * Event 2:
 *
 * Event 3:
 * This is the main sample trigger that is used to trigger the actual sampling
 * on PRU0 by raising an interrupt. After every sample, we have to forward
 * the compare value, taking into account the current sampling period
 * (dynamically adapted by PLL). Also, we will only check for the controller
 * reply directly following this event in order to avoid sampling jitter that
 * could result from being busy with RPMSG and delaying response to the next
 * Event 3
 */

int32_t event_loop()
{
    uint32_t       last_sample_interval_ticks = 0;

    /* Prepare message that will be received and sent to Linux kernel module */
    struct SyncMsg sync_repl                  = {
                             .sync_interval_ticks   = SYNC_INTERVAL_TICKS,
                             .sample_interval_ticks = SAMPLE_INTERVAL_TICKS,
                             .compensation_steps    = 0u,
                             .canary                = CANARY_VALUE_U32,
    };


    /* This tracks our local state, allowing to execute actions at the right time */
    enum SyncState sync_state             = IDLE;

    /*
	* This holds the number of 'compensation' periods, where the sampling
	* period is increased by 1 in order to compensate for the remainder of the
	* integer udiv used to calculate the sampling period.
	*/
    uint32_t       compensation_steps     = sync_repl.compensation_steps;
    /*
	 * holds distribution of the compensation periods (every x samples the period is increased by 1)
	 */
    uint32_t       compensation_counter   = 0u;
    uint32_t       compensation_increment = 0u;

    /* pru0 util monitor */
    uint32_t       pru0_ticks_max         = 0u;
    uint32_t       pru0_ticks_min         = 0xFFFFFFu;
    uint32_t       pru0_ticks_sum         = 0u;
    uint32_t       pru0_sample_count      = 0u;

    /* Our initial guess of the sampling period based on nominal timer period */
    uint32_t       sample_interval_ticks  = sync_repl.sample_interval_ticks;
    uint32_t       sync_interval_ticks    = sync_repl.sync_interval_ticks;

    /* These are our initial guesses for buffer sample period */
    iep_set_cmp_val(IEP_CMP0, sync_interval_ticks);   // 20 MTicks -> 100 ms
    iep_set_cmp_val(IEP_CMP1, sample_interval_ticks); //  2 kTicks -> 10 us

    iep_enable_evt_cmp(IEP_CMP1);
    iep_clear_evt_cmp(IEP_CMP0);

    /* Clear raw interrupt status from ARM host */
    INTC_CLEAR_EVENT(HOST_PRU_EVT_TIMESTAMP);
    /* Wait for first timer interrupt from Linux host */
    while (!(read_r31() & HOST_INT_TIMESTAMP_MASK)) {}

    if (INTC_CHECK_EVENT(HOST_PRU_EVT_TIMESTAMP)) INTC_CLEAR_EVENT(HOST_PRU_EVT_TIMESTAMP);

    iep_start();

    while (1)
    {
#if DEBUG_LOOP_EN
        debug_loop_delays(SHARED_MEM.shp_pru_state);
#endif

        DEBUG_GPIO_STATE_1;
        check_gpio(last_sample_interval_ticks);
        DEBUG_GPIO_STATE_0;

        /* [Event1] Check for interrupt from Linux host to take timestamp */
        if (read_r31() & HOST_INT_TIMESTAMP_MASK)
        {
            if (!INTC_CHECK_EVENT(HOST_PRU_EVT_TIMESTAMP)) continue;

            /* Take timestamp of IEP */
            const uint32_t iep_timestamp = iep_get_cnt_val(); // TODO: remove
            DEBUG_EVENT_STATE_3;
            /* Clear interrupt */
            INTC_CLEAR_EVENT(HOST_PRU_EVT_TIMESTAMP);

            if (sync_state == IDLE) sync_state = REPLY_PENDING;
            else
            {
                msgsys_send_status(MSG_ERR_SYNC_STATE_NOT_IDLE, sync_state, 0u);
                return 0;
            }
            msgsys_send(MSG_SYNC_ROUTINE, iep_timestamp, 0u);
            DEBUG_EVENT_STATE_0;
            continue; // for more regular gpio-sampling
        }

        /*  [Event 2] Timer compare 0 handle -> sync event */
        if (SHARED_MEM.cmp0_trigger_for_pru1)
        {
            DEBUG_EVENT_STATE_2;
            // reset trigger
            SHARED_MEM.cmp0_trigger_for_pru1 = 0;

            /* update clock compensation of sample-trigger */
            iep_set_cmp_val(IEP_CMP1, 0);
            iep_enable_evt_cmp(IEP_CMP1);
            sample_interval_ticks  = sync_repl.sample_interval_ticks;
            compensation_steps     = sync_repl.compensation_steps;
            compensation_increment = sync_repl.compensation_steps;
            compensation_counter   = 0;

            /* update main-loop */
            sync_interval_ticks    = sync_repl.sync_interval_ticks;
            iep_set_cmp_val(IEP_CMP0, sync_interval_ticks);

            /* transmit pru0-util, current design puts this in fresh/next buffer */
            {
                const uint32_t idx                            = SHARED_MEM.buffer_util_idx;
                SHARED_MEM.buffer_util_ptr->ticks_sum[idx]    = pru0_ticks_sum;
                SHARED_MEM.buffer_util_ptr->ticks_max[idx]    = pru0_ticks_max;
                SHARED_MEM.buffer_util_ptr->ticks_min[idx]    = pru0_ticks_min;
                SHARED_MEM.buffer_util_ptr->sample_count[idx] = pru0_sample_count;
                SHARED_MEM.buffer_util_ptr->idx_pru           = idx;
                pru0_ticks_sum                                = 0u;
                pru0_ticks_max                                = 0u;
                pru0_ticks_min                                = 0xFFFFFFu;
                pru0_sample_count                             = 0u;
                if (idx < BUFFER_UTIL_SIZE - 1u) { SHARED_MEM.buffer_util_idx = idx + 1u; }
                else { SHARED_MEM.buffer_util_idx = 0u; }
            }
            // TODO: add warning for when sync not idle?

            /* more maintenance */
            last_sample_interval_ticks = 0;

            DEBUG_EVENT_STATE_0;
            continue; // for more regular gpio-sampling
        }

        /* [Event 3] Timer compare 1 handle -> analog sampling on pru0 */
        if (SHARED_MEM.cmp1_trigger_for_pru1)
        {
            /* prevent a race condition (cmp0_event has to happen before cmp1_event!) */
            if (SHARED_MEM.cmp0_trigger_for_pru1) continue;

            DEBUG_EVENT_STATE_1;
            // reset trigger
            SHARED_MEM.cmp1_trigger_for_pru1 = 0;

            // Update Timer-Values
            last_sample_interval_ticks       = iep_get_cmp_val(IEP_CMP1);

            /* Forward sample timer based on current sample_interval_ticks*/
            uint32_t next_cmp_val            = last_sample_interval_ticks + sample_interval_ticks;
            compensation_counter += compensation_increment; // fixed point magic
            /* If we are in compensation phase add one */
            if ((compensation_counter >= SAMPLES_PER_SYNC) && (compensation_steps > 0))
            {
                // TODO: is that similar to bresenham?
                next_cmp_val += 1;
                compensation_steps--;
                compensation_counter -= SAMPLES_PER_SYNC;
            }
            iep_set_cmp_val(IEP_CMP1, next_cmp_val);

            /* If we are waiting for a reply from Linux kernel module */
            if (receive_sync_reply(&sync_repl) > 0)
            {
                sync_state                        = IDLE;
                SHARED_MEM.next_sync_timestamp_ns = sync_repl.next_timestamp_ns;
            }
            DEBUG_EVENT_STATE_0;
            continue; // for more regular gpio-sampling
        }

        /* Mem-Reading for PRU -> can vary from 530 to 5400 ns (rare) */
        if ((SHARED_MEM.ivsample_fetch_request != SHARED_MEM.ivsample_fetch_index) &&
            (SHARED_MEM.ivsample_fetch_request < BUFFER_IV_SIZE))
        {
            // split reads to optimize gpio-tracing
            const uint32_t index = SHARED_MEM.ivsample_fetch_request;
            DEBUG_RAMRD_STATE_1;
            SHARED_MEM.ivsample_fetch_value = SHARED_MEM.buffer_iv_inp_ptr->sample[index];
            SHARED_MEM.ivsample_fetch_index = index;
            DEBUG_RAMRD_STATE_0;
            continue;
        }

        /* remote gpio-triggering for pru0 */
        if (SHARED_MEM.vsource_batok_trigger_for_pru1)
        {
            if (SHARED_MEM.vsource_batok_pin_value)
            {
                GPIO_ON(GPIO_BATOK);
                DEBUG_PGOOD_STATE_1;
            }
            else
            {
                GPIO_OFF(GPIO_BATOK);
                DEBUG_PGOOD_STATE_0;
            }
            SHARED_MEM.vsource_batok_trigger_for_pru1 = false;
        }

        /* pru0 util monitoring */
        if (SHARED_MEM.pru0_ticks_per_sample != IDX_OUT_OF_BOUND)
        {
            if (SHARED_MEM.pru0_ticks_per_sample < (1u << 20u))
            {
                if (SHARED_MEM.pru0_ticks_per_sample > pru0_ticks_max)
                {
                    pru0_ticks_max = SHARED_MEM.pru0_ticks_per_sample;
                }
                else if (SHARED_MEM.pru0_ticks_per_sample < pru0_ticks_min)
                {
                    pru0_ticks_min = SHARED_MEM.pru0_ticks_per_sample;
                }
                pru0_ticks_sum += SHARED_MEM.pru0_ticks_per_sample;
                pru0_sample_count += 1;
            }
            SHARED_MEM.pru0_ticks_per_sample = IDX_OUT_OF_BOUND;
        }
    }
}

int main(void)
{
    /* Allow OCP primary port access by the PRU so the PRU can read external memories */
    CT_CFG.SYSCFG_bit.STANDBY_INIT = 0;
    DEBUG_STATE_0;

    /* Enable 'timestamp' interrupt from ARM host */
    CT_INTC.EISR_bit.EN_SET_IDX = HOST_PRU_EVT_TIMESTAMP;

    /* wait until pru0 is ready */
    while (SHARED_MEM.cmp0_trigger_for_pru1 == 0u) __delay_cycles(10);
    SHARED_MEM.cmp0_trigger_for_pru1 = 0u;
    msgsys_init();

reset:
    msgsys_send_status(MSG_STATUS_RESTARTING_ROUTINE, 1u, 0u);

    SHARED_MEM.ivsample_fetch_value.voltage = 0u;
    SHARED_MEM.ivsample_fetch_value.current = 0u;
    SHARED_MEM.ivsample_fetch_index         = IDX_OUT_OF_BOUND;

    DEBUG_STATE_0;
    iep_init();
    iep_reset();

    event_loop();
    goto reset;
}
