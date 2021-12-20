#ifndef __TRANSPORT_H_
#define __TRANSPORT_H_

#include <stdint.h>

typedef enum { SWD_PORT_DP = 0, SWD_PORT_AP = 1 } swd_port_t;

typedef enum { SWD_RW_W = 0, SWD_RW_R = 1 } swd_rw_t;

typedef enum { SWD_ACK_OK = 0x1, SWD_ACK_WAIT = 0x2, SWD_ACK_FAULT = 0x4 } swd_ack_t;

typedef uint8_t swd_header_t;

int swd_transport_read(uint32_t *data, swd_port_t port, uint8_t addr, unsigned int retries);
int swd_transport_write(swd_port_t port, uint8_t addr, uint32_t data, unsigned int retries);

int swd_transport_init(unsigned int pin_swdclk, unsigned int pin_swdio, unsigned int f_clk);
int swd_transport_reset(void);

#endif /* __TRANSPORT_H_ */
