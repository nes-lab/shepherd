#ifndef __PROG_SWD_TRANSPORT_H_
#define __PROG_SWD_TRANSPORT_H_

#include <stdint.h>

typedef enum { SWD_PORT_DP = 0, SWD_PORT_AP = 1 } swd_port_t;

int transport_read(uint32_t *data, swd_port_t port, uint8_t addr, unsigned int retries);
int transport_write(swd_port_t port, uint8_t addr, uint32_t data, unsigned int retries);

int transport_init(unsigned int pin_swdclk, unsigned int pin_swdio, unsigned int f_clk);
int transport_release(void);
int transport_reset(void);

#endif /* __PROG_SWD_TRANSPORT_H_ */
