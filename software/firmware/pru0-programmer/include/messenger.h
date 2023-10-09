#ifndef PRU_FIRMWARE_PRU0_PROGRAMMER_INCLUDE_MESSENGER_H
#define PRU_FIRMWARE_PRU0_PROGRAMMER_INCLUDE_MESSENGER_H

#include "commons.h"
#include "stdint_fast.h"
#include <stdint.h>

void    send_status(volatile struct SharedMem *const shared_mem, enum MsgType type,
                    const uint32_t value);

// send returns a 1 on success
bool_ft send_message(volatile struct SharedMem *const shared_mem, enum MsgType type,
                     const uint32_t value1, const uint32_t value2);


// only one central hub should receive, because a message is only handed out once
bool_ft receive_message(volatile struct SharedMem *const shared_mem,
                        struct ProtoMsg *const           msg_container);


#endif //PRU_FIRMWARE_PRU0_PROGRAMMER_INCLUDE_MESSENGER_H
