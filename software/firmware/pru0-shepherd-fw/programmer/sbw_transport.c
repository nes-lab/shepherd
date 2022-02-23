#include "delay.h"
#include "programmer/sbw_transport.h"

static gpio_state_t tclk_state = GPIO_STATE_LOW;
static unsigned int clk_period_cycles;

static struct {
	unsigned int sbwtck;
	unsigned int sbwtdio;
} pins;

static void tmsh(void)
{
	sys_gpio_set(pins.sbwtdio, GPIO_STATE_HIGH);
	__delay_var_cycles(clk_period_cycles);
	sys_gpio_set(pins.sbwtck, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	sys_gpio_set(pins.sbwtck, GPIO_STATE_HIGH);
}

static void tmsl(void)
{
	sys_gpio_set(pins.sbwtdio, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	sys_gpio_set(pins.sbwtck, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	sys_gpio_set(pins.sbwtck, GPIO_STATE_HIGH);
}

static void tmsldh(void)
{
	sys_gpio_set(pins.sbwtdio, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	sys_gpio_set(pins.sbwtck, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	sys_gpio_set(pins.sbwtdio, GPIO_STATE_HIGH);
	sys_gpio_set(pins.sbwtck, GPIO_STATE_HIGH);
}

static void tdih(void)
{
	sys_gpio_set(pins.sbwtdio, GPIO_STATE_HIGH);
	__delay_var_cycles(clk_period_cycles);
	sys_gpio_set(pins.sbwtck, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	sys_gpio_set(pins.sbwtck, GPIO_STATE_HIGH);
}

static void tdil(void)
{
	sys_gpio_set(pins.sbwtdio, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	sys_gpio_set(pins.sbwtck, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	sys_gpio_set(pins.sbwtck, GPIO_STATE_HIGH);
}

static gpio_state_t tdo_rd(void)
{
	gpio_state_t res;
	sys_gpio_cfg_dir(pins.sbwtdio, GPIO_DIR_IN);
	__delay_var_cycles(clk_period_cycles);
	sys_gpio_set(pins.sbwtck, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	res = sys_gpio_get(pins.sbwtdio);
	__delay_var_cycles(clk_period_cycles);
	sys_gpio_set(pins.sbwtck, GPIO_STATE_HIGH);
	sys_gpio_set(pins.sbwtdio, GPIO_STATE_HIGH);
	sys_gpio_cfg_dir(pins.sbwtdio, GPIO_DIR_OUT);

	return res;
}

static void tdo_sbw(void)
{
	sys_gpio_cfg_dir(pins.sbwtdio, GPIO_DIR_IN);
	__delay_var_cycles(clk_period_cycles);
	sys_gpio_set(pins.sbwtck, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
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
	if (tclk_state == GPIO_STATE_HIGH) {
		tmsldh();
	} else {
		tmsl();
	}

	sys_gpio_set(pins.sbwtdio, GPIO_STATE_LOW);

	tdil();
	tdo_sbw();
	tclk_state = GPIO_STATE_LOW;
}

void set_tclk_sbw(void)
{
	if (tclk_state == GPIO_STATE_HIGH) {
		tmsldh();
	} else {
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
	pins.sbwtck = pin_sbwtck;
	pins.sbwtdio = pin_sbwtdio;

	/*
	 * Ignore the f_clk parameter and make sure that clock period equals 5 clock cycles at 18Mhz -> 280ns
	 * This is the value from SLAU320AJ section 2.2.3.1. and works reliably where other values do not work.
	 * Here, we precalculate the delay cycles w.r.t. the PRU's clock.
	 */
	clk_period_cycles = (5 * F_CPU) / 18000000;

	return 0;
}