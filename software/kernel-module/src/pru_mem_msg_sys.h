#ifndef SRC_MEM_MSG_PRU_H
#define SRC_MEM_MSG_PRU_H

#include "commons.h"

#define RING_SIZE   64U

struct RingBuffer
{
    struct ProtoMsg ring[RING_SIZE];
    uint32_t start; // TODO: these can be smaller, at least in documentation
    uint32_t end;
    uint32_t active;
};

void put_msg_to_pru(const struct ProtoMsg *const element);
uint8_t get_msg_from_pru(struct ProtoMsg *const element);

int mem_msg_sys_exit(void);
int mem_msg_sys_reset(void);
int mem_msg_sys_init(void);

#endif //SRC_MEM_MSG_PRU_H
