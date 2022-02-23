#ifndef __PROG_SBW_TRANSPORT_H_
#define __PROG_SBW_TRANSPORT_H_

#include "hal.h"

void tmsl_tdil(void);
void tmsh_tdil(void);
void tmsl_tdih(void);
void tmsh_tdih(void);
gpio_state_t tmsl_tdih_tdo_rd(void);
gpio_state_t tmsl_tdil_tdo_rd(void);
gpio_state_t tmsh_tdih_tdo_rd(void);

gpio_state_t tmsh_tdil_tdo_rd(void);

void clr_tclk_sbw(void);
void set_tclk_sbw(void);
gpio_state_t get_tclk(void);

void set_sbwtdio(gpio_state_t state);
void set_sbwtck(gpio_state_t state);

int sbw_transport_init(unsigned int pin_sbwtck, unsigned int pin_sbwtdio, unsigned int f_clk);
int sbw_transport_disconnect(void);
int sbw_transport_connect(void);

#endif /* __PROG_SBW_TRANSPORT_H_ */