#include "messenger.h"
#include "shared_mem.h"


// alternative message channel specially dedicated for errors
void send_status(enum MsgType type, const uint32_t value1, const uint32_t value2)
{
    // do not care for sent-status, the newest error wins IF different from previous
    if (!((SHARED_MEM.pru0_msg_error.type == type) &&
          (SHARED_MEM.pru0_msg_error.value[0] == value1)))
    {
        SHARED_MEM.pru0_msg_error.unread   = 0u;
        SHARED_MEM.pru0_msg_error.type     = type;
        SHARED_MEM.pru0_msg_error.value[0] = value1;
        SHARED_MEM.pru0_msg_error.value[1] = value2;
        SHARED_MEM.pru0_msg_error.id       = MSG_TO_KERNEL;
        // NOTE: always make sure that the unread-flag is activated AFTER payload is copied
        SHARED_MEM.pru0_msg_error.unread   = 1u;
    }
    if (type >= 0xE0) __delay_cycles(200U / TICK_INTERVAL_NS); // 200 ns
}

// send returns a 1 on success
bool_ft send_message(enum MsgType type, const uint32_t value1, const uint32_t value2)
{
    if (SHARED_MEM.pru0_msg_outbox.unread == 0)
    {
        SHARED_MEM.pru0_msg_outbox.type     = type;
        SHARED_MEM.pru0_msg_outbox.value[0] = value1;
        SHARED_MEM.pru0_msg_outbox.value[1] = value2;
        SHARED_MEM.pru0_msg_outbox.id       = MSG_TO_KERNEL;
        // NOTE: always make sure that the unread-flag is activated AFTER payload is copied
        SHARED_MEM.pru0_msg_outbox.unread   = 1u;
        return 1;
    }
    /* Error occurs if kernel was not able to handle previous message in time */
    send_status(MSG_ERR_BACKPRESSURE, 0u, 0u);
    return 0;
}

// only one central hub should receive, because a message is only handed out once
bool_ft receive_message(struct ProtoMsg *const msg_container)
{
    if (SHARED_MEM.pru0_msg_inbox.unread >= 1u)
    {
        if (SHARED_MEM.pru0_msg_inbox.id == MSG_TO_PRU)
        {
            *msg_container                   = SHARED_MEM.pru0_msg_inbox;
            SHARED_MEM.pru0_msg_inbox.unread = 0u;
            return 1;
        }
        // send mem_corruption warning
        send_status(MSG_ERR_MEM_CORRUPTION, 0u, 0u);
    }
    return 0;
}
