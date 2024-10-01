#ifndef MSG_SYS_H
#define MSG_SYS_H

#include "commons.h"
#include "ringbuffer.h"
#include <stdint.h>

void    msg_init(volatile struct SharedMem *const shared_mem);

// alternative message channel specially dedicated for errors
void    msg_send_status(enum MsgType type, const uint32_t value);

// send returns a 1 on success
bool_ft msg_send(enum MsgType type, const uint32_t value1, const uint32_t value2);

// only one central hub should receive, because a message is only handed out once
bool_ft msg_receive(struct ProtoMsg *const container);

#endif //MSG_SYS_H
