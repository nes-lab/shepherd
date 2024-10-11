#include "msg_sys.h"
#include "commons.h"
#include "shared_mem.h"
#include <stdint.h>
#include <stdlib.h>

volatile struct ProtoMsg *msg_inbox;
volatile struct ProtoMsg *msg_outbox;
volatile struct ProtoMsg *msg_error;

void                      msg_init()
{
#if defined(PRU0) // TODO: can be hardcoded!
    msg_inbox  = &SHARED_MEM.pru0_msg_inbox;
    msg_outbox = &SHARED_MEM.pru0_msg_outbox;
    msg_error  = &SHARED_MEM.pru0_msg_error;
#elif defined(PRU1)
    msg_outbox = &SHARED_MEM.pru1_sync_outbox;
    msg_error  = &SHARED_MEM.pru1_msg_error;
    // TODO: add sync inbox
#else
  #error "PRU number must be defined and either 1 or 0"
#endif
}

// alternative message channel specially dedicated for errors
void msg_send_status(enum MsgType type, const uint32_t value1, const uint32_t value2)
{
    // do not care for sent-status -> the newest error wins IF different from previous
    if (!((msg_error->type == type) && (msg_error->value[0] == value1)))
    {
        msg_error->unread   = 0u;
        msg_error->type     = type;
        msg_error->value[0] = value1;
        msg_error->value[1] = value2;
        msg_error->id       = MSG_TO_KERNEL;
        // NOTE: always make sure that the unread-flag is activated AFTER payload is copied
        msg_error->unread   = 1u;
    }
    // apply some rate limiting
    if (type >= 0xE0) __delay_cycles(200U / TICK_INTERVAL_NS); // 200 ns
}

// send returns a 1 on success
bool_ft msg_send(enum MsgType type, const uint32_t value1, const uint32_t value2)
{
    if (msg_outbox->unread == 0)
    {
        msg_outbox->type     = type;
        msg_outbox->value[0] = value1;
        msg_outbox->value[1] = value2;
        msg_outbox->id       = MSG_TO_KERNEL;
        // NOTE: always make sure that the unread-flag is activated AFTER payload is copied
        msg_outbox->unread   = 1u;
        return 1;
    }
    /* Error occurs if kernel was not able to handle previous message in time */
    msg_send_status(MSG_ERR_BACKPRESSURE, 0u, 0u);
    return 0;
}

// only one central hub should receive, because a message is only handed out once
bool_ft msg_receive(struct ProtoMsg *const container)
{
    if (msg_inbox->unread >= 1)
    {
        if (msg_inbox->id == MSG_TO_PRU)
        {
            *container        = *msg_inbox;
            msg_inbox->unread = 0;
            return 1;
        }
        // send mem_corruption warning
        msg_send_status(MSG_ERR_MEM_CORRUPTION, 0u, 0u);
    }
    return 0;
}
