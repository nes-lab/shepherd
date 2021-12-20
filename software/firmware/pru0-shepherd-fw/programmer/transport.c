#include "programmer/transport.h"
#include "programmer/hal.h"
#include "var_delay.h"

static swd_header_t hdr;
static unsigned int pin_swdclk_usr;
static unsigned int pin_swdio_usr;
static unsigned int clk_period_cycles;

static inline void swd_iow(gpio_state_t swdio_state)
{
	hal_gpio_set(pin_swdio_usr, swdio_state);
	hal_gpio_set(pin_swdclk_usr, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	hal_gpio_set(pin_swdclk_usr, GPIO_STATE_HIGH);
	__delay_var_cycles(clk_period_cycles);
}

static inline int swd_ior(void)
{
	hal_gpio_set(pin_swdclk_usr, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	int ret = hal_gpio_read(pin_swdio_usr);
	hal_gpio_set(pin_swdclk_usr, GPIO_STATE_HIGH);
	__delay_var_cycles(clk_period_cycles);
	return ret;
}

static inline void swd_iotrn(gpio_dir_t dir)
{
	hal_gpio_cfg_dir(pin_swdio_usr, GPIO_DIR_IN);
	hal_gpio_set(pin_swdclk_usr, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	hal_gpio_set(pin_swdclk_usr, GPIO_STATE_HIGH);
	if (dir == GPIO_DIR_OUT)
		hal_gpio_cfg_dir(pin_swdio_usr, GPIO_DIR_OUT);

	__delay_var_cycles(clk_period_cycles);
}

int swd_header_init(swd_header_t *header, swd_port_t port, swd_rw_t rw, uint8_t addr)
{
	*header = 0x81 | ((addr & 0xC) << 1) | (port << 1) | (rw << 2);

	int bit_count = 0;
	int i;
	for (i = 1; i < 5; i++) {
		if (*header & (0x01 << i))
			bit_count++;
	}
	if (bit_count % 2)
		*header |= (1 << 5);

	return 0;
}

static int swd_data_write(uint32_t *data)
{
	int parity_cnt = 0;
	int i;
	for (i = 0; i < 32; i++) {
		if (*data & (1 << i)) {
			parity_cnt++;
			swd_iow(GPIO_STATE_HIGH);
		} else
			swd_iow(GPIO_STATE_LOW);
	}
	if (parity_cnt % 2)
		swd_iow(GPIO_STATE_HIGH);
	else
		swd_iow(GPIO_STATE_LOW);
	return 0;
}

static int swd_data_read(uint32_t *data)
{
	int parity_cnt = 0;
	*data = 0;
	int i;
	for (i = 0; i < 32; i++) {
		if (swd_ior()) {
			*data |= 1 << i;
			parity_cnt++;
		}
	}
	int parity = swd_ior();
	if ((parity_cnt % 2) != parity)
		return -1;
	return 0;
}

int swd_transceive(swd_header_t *header, uint32_t *data)
{
	int i;
	int rc;

	for (i = 0; i < 8; i++) {
		swd_iow((*header >> i) & 0x1);
	}
	swd_iotrn(GPIO_DIR_IN);
	uint8_t ack = 0;
	for (i = 0; i < 3; i++) {
		ack |= swd_ior() << i;
	}
	if (ack != SWD_ACK_OK) {
		swd_iotrn(GPIO_DIR_OUT);
		return ack;
	}

	if (*header & (1 << 2)) {
		rc = swd_data_read(data);
		swd_iotrn(GPIO_DIR_OUT);

	} else {
		swd_iotrn(GPIO_DIR_OUT);
		rc = swd_data_write(data);
	}
	hal_gpio_set(pin_swdclk_usr, GPIO_STATE_LOW);
	return rc;
}

int swd_transport_read(uint32_t *data, swd_port_t port, uint8_t addr, unsigned int retries)
{
	int rc;
	swd_header_init(&hdr, port, SWD_RW_R, addr);

	do {
		rc = swd_transceive(&hdr, data);
		if (rc <= 0)
			return rc;
		retries--;
	} while (retries > 0);
	return -rc;
}

int swd_transport_write(swd_port_t port, uint8_t addr, uint32_t data, unsigned int retries)
{
	int rc;
	swd_header_init(&hdr, port, SWD_RW_W, addr);
	do {
		rc = swd_transceive(&hdr, &data);
		if (rc <= 0)
			return rc;
		retries--;
	} while (retries > 0);
	return -rc;
}

int swd_transport_reset(void)
{
	int i;
	uint32_t dummy;
	hal_gpio_cfg_dir(pin_swdio_usr, GPIO_DIR_OUT);

	for (i = 0; i < 56; i++) {
		swd_iow(GPIO_STATE_HIGH);
	}

	/* JTAG -> SWD sequence */
	uint16_t tmp = 0x79E7;
	for (i = 15; i >= 0; i--) {
		swd_iow((tmp >> i) & 0x01);
	}

	for (i = 0; i < 56; i++) {
		swd_iow(GPIO_STATE_HIGH);
	}

	for (i = 0; i < 16; i++) {
		swd_iow(GPIO_STATE_LOW);
	}
	swd_transport_read(&dummy, SWD_PORT_DP, 0x0, 5);
	return 0;
}

int swd_transport_init(unsigned int pin_swdclk, unsigned int pin_swdio, unsigned int f_clk)
{
	pin_swdclk_usr = pin_swdclk;
	pin_swdio_usr = pin_swdio;

	clk_period_cycles = 200000000 / f_clk / 2;

	hal_gpio_set(pin_swdclk_usr, GPIO_STATE_LOW);
	hal_gpio_cfg_dir(pin_swdclk_usr, GPIO_DIR_OUT);

	hal_gpio_cfg_dir(pin_swdio_usr, GPIO_DIR_IN);

	return 0;
}
