/*
This FW is for generating an external sync event on both pru1 debug pins
mainly because accessing gpio from kMod is harder
*/
#include <gpio.h>
#include <pru_cfg.h>
#include <stdint.h>

#include "iep.h"
#include "intc.h"

#include "commons.h"
#include "resource_table.h"
#include "shepherd_config.h"
#include "stdint_fast.h"

/* The Arm to Host interrupt for the timestamp event is mapped to Host interrupt 0 -> Bit 30 (see resource_table.h) */
#define HOST_INT_TIMESTAMP_MASK (1U << 30U)

// both pins have a LED
#define DEBUG_PIN0_MASK         BIT_SHIFT(P8_28)
#define DEBUG_PIN1_MASK         BIT_SHIFT(P8_30)

#define DEBUG_STATE_0           write_r30(read_r30() & ~(DEBUG_PIN0_MASK | DEBUG_PIN1_MASK))
#define DEBUG_STATE_1           write_r30(read_r30() | (DEBUG_PIN0_MASK | DEBUG_PIN1_MASK))


enum SyncState
{
    IDLE,
    REPLY_PENDING
};


// alternative message channel specially dedicated for errors
static void send_status(volatile struct SharedMem *const shared_mem, enum MsgType type,
                        const uint32_t value)
{
    // do not care for sent-status -> the newest error wins IF different from previous
    if (!((shared_mem->pru1_msg_error.type == type) &&
          (shared_mem->pru1_msg_error.value[0] == value)))
    {
        shared_mem->pru1_msg_error.unread   = 0u;
        shared_mem->pru1_msg_error.type     = type;
        shared_mem->pru1_msg_error.value[0] = value;
        shared_mem->pru1_msg_error.id       = MSG_TO_KERNEL;
        // NOTE: always make sure that the unread-flag is activated AFTER payload is copied
        shared_mem->pru1_msg_error.unread   = 1u;
    }
    if (type >= 0xE0) __delay_cycles(200u / TIMER_TICK_NS); // 200 ns
}


static inline bool_ft receive_sync_reply(volatile struct SharedMem *const shared_mem,
                                         struct SyncMsg *const            msg)
{
    if (shared_mem->pru1_sync_inbox.unread >= 1)
    {
        if (shared_mem->pru1_sync_inbox.id != MSG_TO_PRU)
        {
            /* Error occurs if something writes over boundaries */
            send_status(shared_mem, MSG_ERR_MEMCORRUPTION, 0);
            return 0;
        }
        if (shared_mem->pru1_sync_inbox.type == MSG_TEST)
        {
            // pipeline-test for msg-system
            shared_mem->pru1_sync_inbox.unread = 0;
            send_status(shared_mem, MSG_TEST, shared_mem->pru1_sync_inbox.buffer_block_period);
            return 0;
        }
        // NOTE: do not overwrite external msg without thinking twice! sync-routine relies on that content
        *msg = shared_mem->pru1_sync_inbox; // TODO: faster to copy only the needed payload
        shared_mem->pru1_sync_inbox.unread = 0;
        return 1;
    }
    return 0;
}


// emits a 1 on success
// pru1_sync_outbox: (future opt.) needs to have special config set: identifier=MSG_TO_KERNEL and unread=1
static inline bool_ft send_sync_request(volatile struct SharedMem *const shared_mem,
                                        const struct ProtoMsg *const     msg)
{
    if (shared_mem->pru1_sync_outbox.unread == 0)
    {
        shared_mem->pru1_sync_outbox        = *msg;
        shared_mem->pru1_sync_outbox.id     = MSG_TO_KERNEL;
        // NOTE: always make sure that the unread-flag is activated AFTER payload is copied
        shared_mem->pru1_sync_outbox.unread = 1u;
        return 1;
    }
    /* Error occurs if PRU was not able to handle previous message in time */
    send_status(shared_mem, MSG_ERR_BACKPRESSURE, 0);
    return 0;
}


int32_t event_loop(volatile struct SharedMem *const shared_mem)
{
    /* Prepare message that will be received and sent to Linux kernel module */
    struct ProtoMsg sync_rqst = {.id = MSG_TO_KERNEL, .type = MSG_NONE, .unread = 0u};
    struct SyncMsg  sync_repl = {
             .buffer_block_period  = TIMER_BASE_PERIOD,
             .analog_sample_period = TIMER_BASE_PERIOD / ADC_SAMPLES_PER_BUFFER,
             .compensation_steps   = 0u,
    };

    /* Clear raw interrupt status from ARM host */
    INTC_CLEAR_EVENT(HOST_PRU_EVT_TIMESTAMP);
    /* Wait for first timer interrupt from Linux host */
    while (!(read_r31() & HOST_INT_TIMESTAMP_MASK)) {}

    if (INTC_CHECK_EVENT(HOST_PRU_EVT_TIMESTAMP)) INTC_CLEAR_EVENT(HOST_PRU_EVT_TIMESTAMP);

    while (1)
    {
        /* Trigger for interrupt from Linux host to take timestamp */
        while (!(read_r31() & HOST_INT_TIMESTAMP_MASK));

        if (!INTC_CHECK_EVENT(HOST_PRU_EVT_TIMESTAMP)) continue;
        DEBUG_STATE_1;

        /* Take timestamp of IEP */
        sync_rqst.value[0] = iep_get_cnt_val();
        /* Clear interrupt */
        INTC_CLEAR_EVENT(HOST_PRU_EVT_TIMESTAMP);

        send_sync_request(shared_mem, &sync_rqst);

        /* waiting for a reply from Linux kernel module */
        while (receive_sync_reply(shared_mem, &sync_repl) < 1)
        {
            __delay_cycles(2000); // = 10 us
        }
        shared_mem->next_buffer_timestamp_ns = sync_repl.next_timestamp_ns;
        DEBUG_STATE_0;
    }
}


int main(void)
{
    volatile struct SharedMem *const shared_memory =
            (volatile struct SharedMem *) PRU_SHARED_MEM_STRUCT_OFFSET;

    /* Allow OCP primary port access by the PRU so the PRU can read external memories */
    CT_CFG.SYSCFG_bit.STANDBY_INIT = 0;
    DEBUG_STATE_0;

    /* Enable 'timestamp' interrupt from ARM host */
    CT_INTC.EISR_bit.EN_SET_IDX = HOST_PRU_EVT_TIMESTAMP;

    /* wait until pru0 is ready */
    while (shared_memory->cmp0_trigger_for_pru1 == 0u) __delay_cycles(10);
    shared_memory->cmp0_trigger_for_pru1 = 0u;

reset:
    send_status(shared_memory, MSG_STATUS_RESTARTING_ROUTINE, 101);
    /* Make sure the mutex is clear */
    simple_mutex_exit(&shared_memory->gpio_edges_mutex);

    shared_memory->analog_value_current = 0u;
    shared_memory->analog_value_voltage = 0u;
    shared_memory->analog_value_index   = 0u;

    iep_init();
    iep_reset();

    event_loop(shared_memory);
    goto reset;
}
