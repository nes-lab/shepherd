#ifndef __PROG_SBW_TRANSPORT_H_
#define __PROG_SBW_TRANSPORT_H_

#include "sys_gpio.h"

/* TMS low, TDI low */
void         tmsl_tdil(void);
/* TMS high, TDI low */
void         tmsh_tdil(void);
/* TMS low, TDI high */
void         tmsl_tdih(void);
/* TMS high, TDI high */
void         tmsh_tdih(void);

/* SBW transfer with TMS low, TDI high. Returns TDO. */
gpio_state_t tmsl_tdih_tdo_rd(void);
/* SBW transfer with TMS low, TDI low. Returns TDO. */
gpio_state_t tmsl_tdil_tdo_rd(void);
/* SBW transfer with TMS high, TDI high. Returns TDO. */
gpio_state_t tmsh_tdih_tdo_rd(void);
/* SBW transfer with TMS high, TDI low. Returns TDO. */
gpio_state_t tmsh_tdil_tdo_rd(void);

/* Clears JTAG TCLK signal via SBW */
void         clr_tclk_sbw(void);
/* Sets JTAG TCLK signal via SBW */
void         set_tclk_sbw(void);
/* Returns internal state of JTAG TCLK signal */
gpio_state_t get_tclk(void);

/* Wrapper for setting SBWTDIO pin */
void         set_sbwtdio(gpio_state_t state);
/* Wrapper for setting SBWTCK pin */
void         set_sbwtck(gpio_state_t state);

int          sbw_transport_init(unsigned int pin_sbwtck, unsigned int pin_sbwtdio, unsigned int f_clk);
int          sbw_transport_disconnect(void);
int          sbw_transport_connect(void);

#endif /* __PROG_SBW_TRANSPORT_H_ */
