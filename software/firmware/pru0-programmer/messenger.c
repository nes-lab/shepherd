#include "messenger.h"

// alternative message channel specially dedicated for errors
void send_status(volatile struct SharedMem *const shared_mem, enum MsgType type,
                 const uint32_t value)
{
    // do not care for sent-status, the newest error wins IF different from previous
    if (!((shared_mem->pru1_msg_error.type == type) &&
          (shared_mem->pru1_msg_error.value[0] == value)))
    {
        shared_mem->pru0_msg_error.unread   = 0u;
        shared_mem->pru0_msg_error.type     = type;
        shared_mem->pru0_msg_error.value[0] = value;
        shared_mem->pru0_msg_error.id       = MSG_TO_KERNEL;
        // NOTE: always make sure that the unread-flag is activated AFTER payload is copied
        shared_mem->pru0_msg_error.unread   = 1u;
    }
    if (type >= 0xE0) __delay_cycles(200U / TIMER_TICK_NS); // 200 ns
}

// send returns a 1 on success
bool_ft send_message(volatile struct SharedMem *const shared_mem, enum MsgType type,
                     const uint32_t value1, const uint32_t value2)
{
    if (shared_mem->pru0_msg_outbox.unread == 0)
    {
        shared_mem->pru0_msg_outbox.type     = type;
        shared_mem->pru0_msg_outbox.value[0] = value1;
        shared_mem->pru0_msg_outbox.value[1] = value2;
        shared_mem->pru0_msg_outbox.id       = MSG_TO_KERNEL;
        // NOTE: always make sure that the unread-flag is activated AFTER payload is copied
        shared_mem->pru0_msg_outbox.unread   = 1u;
        return 1;
    }
    /* Error occurs if kernel was not able to handle previous message in time */
    send_status(shared_mem, MSG_ERR_BACKPRESSURE, 0);
    return 0;
}

// only one central hub should receive, because a message is only handed out once
bool_ft receive_message(volatile struct SharedMem *const shared_mem,
                        struct ProtoMsg *const           msg_container)
{
    if (shared_mem->pru0_msg_inbox.unread >= 1)
    {
        if (shared_mem->pru0_msg_inbox.id == MSG_TO_PRU)
        {
            *msg_container                    = shared_mem->pru0_msg_inbox;
            shared_mem->pru0_msg_inbox.unread = 0;
            return 1;
        }
        // send mem_corruption warning
        send_status(shared_mem, MSG_ERR_MEMCORRUPTION, 0);
    }
    return 0;
}
