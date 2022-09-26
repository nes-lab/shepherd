/*
 * Copyright (C) 2016 Texas Instruments Incorporated - http://www.ti.com/
 *
 *  Redistribution and use in source and binary forms, with or without
 *  modification, are permitted provided that the following conditions
 *  are met:
 *
 *    Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 *
 *    Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the
 *    distribution.
 *
 *    Neither the name of Texas Instruments Incorporated nor the names of
 *    its contributors may be used to endorse or promote products derived
 *    from this software without specific prior written permission.
 *
 *  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 *  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 *  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 *  A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 *  OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 *  SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 *  LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 *  DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 *  THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 *  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 *  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 *
*/

/*
 * This implementation of the SBW transport layer is based on code provided
 * by TI (slau320 and slaa754). It provides the basic routines to serialize
 * the JTAG TMS, TDO and TDI signals over a two wire interface.
 */

#include "programmer/sbw_transport.h"
#include "delay.h"

static gpio_state_t tclk_state = GPIO_STATE_LOW;
static unsigned int clk_delay_cycles;

static struct
{
    unsigned int sbwtck;
    unsigned int sbwtdio;
} pins;

static void tmsh(void)
{
    sys_gpio_set(pins.sbwtdio, GPIO_STATE_HIGH);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_LOW);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_HIGH);
}

static void tmsl(void)
{
    sys_gpio_set(pins.sbwtdio, GPIO_STATE_LOW);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_LOW);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_HIGH);
}

static void tmsldh(void)
{
    sys_gpio_set(pins.sbwtdio, GPIO_STATE_LOW);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_LOW);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.sbwtdio, GPIO_STATE_HIGH);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_HIGH);
}

static void tdih(void)
{
    sys_gpio_set(pins.sbwtdio, GPIO_STATE_HIGH);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_LOW);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_HIGH);
}

static void tdil(void)
{
    sys_gpio_set(pins.sbwtdio, GPIO_STATE_LOW);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_LOW);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_HIGH);
}

static gpio_state_t tdo_rd(void)
{
    gpio_state_t res;
    sys_gpio_cfg_dir(pins.sbwtdio, GPIO_DIR_IN);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_LOW);
    __delay_var_cycles(clk_delay_cycles);
    res = sys_gpio_get(pins.sbwtdio);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_HIGH);
    sys_gpio_set(pins.sbwtdio, GPIO_STATE_HIGH);
    sys_gpio_cfg_dir(pins.sbwtdio, GPIO_DIR_OUT);

    return res;
}

static void tdo_sbw(void)
{
    sys_gpio_cfg_dir(pins.sbwtdio, GPIO_DIR_IN);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_LOW);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_HIGH);
    sys_gpio_set(pins.sbwtdio, GPIO_STATE_HIGH);
    sys_gpio_cfg_dir(pins.sbwtdio, GPIO_DIR_OUT);
}

void set_sbwtdio(gpio_state_t state)
{
    sys_gpio_set(pins.sbwtdio, state);
}

void set_sbwtck(gpio_state_t state)
{
    sys_gpio_set(pins.sbwtck, state);
}

void tmsl_tdil(void)
{
    tmsl();
    tdil();
    tdo_sbw();
}

void tmsh_tdil(void)
{
    tmsh();
    tdil();
    tdo_sbw();
}

void tmsl_tdih(void)
{
    tmsl();
    tdih();
    tdo_sbw();
}

void tmsh_tdih(void)
{
    tmsh();
    tdih();
    tdo_sbw();
}

gpio_state_t tmsl_tdih_tdo_rd(void)
{
    tmsl();
    tdih();
    return tdo_rd();
}

gpio_state_t tmsl_tdil_tdo_rd(void)
{
    tmsl();
    tdil();
    return tdo_rd();
}

gpio_state_t tmsh_tdih_tdo_rd(void)
{
    tmsh();
    tdih();
    return tdo_rd();
}

gpio_state_t tmsh_tdil_tdo_rd(void)
{
    tmsh();
    tdil();
    return tdo_rd();
}

void clr_tclk_sbw(void)
{
    if (tclk_state == GPIO_STATE_HIGH)
    {
        tmsldh();
    }
    else
    {
        tmsl();
    }

    sys_gpio_set(pins.sbwtdio, GPIO_STATE_LOW);

    tdil();
    tdo_sbw();
    tclk_state = GPIO_STATE_LOW;
}

void set_tclk_sbw(void)
{
    if (tclk_state == GPIO_STATE_HIGH)
    {
        tmsldh();
    }
    else
    {
        tmsl();
    }
    sys_gpio_set(pins.sbwtdio, GPIO_STATE_HIGH);

    tdih();
    tdo_sbw();
    tclk_state = GPIO_STATE_HIGH;
}

gpio_state_t get_tclk(void)
{
    return tclk_state;
}

int sbw_transport_disconnect(void)
{
    sys_gpio_cfg_dir(pins.sbwtdio, GPIO_DIR_IN);
    sys_gpio_cfg_dir(pins.sbwtck, GPIO_DIR_IN);

    tclk_state = GPIO_STATE_LOW;
    return 0;
}

int sbw_transport_connect(void)
{
    sys_gpio_set(pins.sbwtdio, GPIO_STATE_HIGH);
    sys_gpio_cfg_dir(pins.sbwtdio, GPIO_DIR_OUT);
    sys_gpio_set(pins.sbwtck, GPIO_STATE_HIGH);
    sys_gpio_cfg_dir(pins.sbwtck, GPIO_DIR_OUT);

    tclk_state = GPIO_STATE_LOW;
    return 0;
}

int sbw_transport_init(unsigned int pin_sbwtck, unsigned int pin_sbwtdio, unsigned int f_clk)
{
    pins.sbwtck      = pin_sbwtck;
    pins.sbwtdio     = pin_sbwtdio;

    /*
	 * Ignore the f_clk parameter and make sure that clock frequency is around 500k. This number is taken from
	 * TI's slaa754 reference implementation and works reliably where other values do not work.
	 * In SLAU320AJ section 2.2.3.1., the 'delay' is specified as 5 clock cycles at 18MHz, but this seems
	 * to not work reliably and contradicts the reference implementation.
	 */
    clk_delay_cycles = F_CPU / 500000 / 2;

    return 0;
}
