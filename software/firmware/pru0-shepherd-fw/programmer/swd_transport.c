#include "programmer/swd_transport.h"
#include "programmer/hal.h"
#include "var_delay.h"

#define TP_TCV_WIDTH 32

typedef enum { SWD_RW_W = 0, SWD_RW_R = 1 } swd_rw_t;

typedef enum { SWD_ACK_OK = 0x1, SWD_ACK_WAIT = 0x2, SWD_ACK_FAULT = 0x4 } swd_ack_t;

typedef uint8_t swd_header_t;
static swd_header_t hdr;

static struct {
	unsigned int swdclk;
	unsigned int swdio;
} pins;

static unsigned int clk_period_cycles;

static inline void iow(gpio_state_t swdio_state)
{
	hal_gpio_set(pins.swdio, swdio_state);
	hal_gpio_set(pins.swdclk, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	hal_gpio_set(pins.swdclk, GPIO_STATE_HIGH);
	__delay_var_cycles(clk_period_cycles);
}

static inline int ior(void)
{
	hal_gpio_set(pins.swdclk, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	int ret = hal_gpio_read(pins.swdio);
	hal_gpio_set(pins.swdclk, GPIO_STATE_HIGH);
	__delay_var_cycles(clk_period_cycles);
	return ret;
}

static inline void iotrn(gpio_dir_t dir)
{
	hal_gpio_cfg_dir(pins.swdio, GPIO_DIR_IN);
	hal_gpio_set(pins.swdclk, GPIO_STATE_LOW);
	__delay_var_cycles(clk_period_cycles);
	hal_gpio_set(pins.swdclk, GPIO_STATE_HIGH);
	if (dir == GPIO_DIR_OUT)
		hal_gpio_cfg_dir(pins.swdio, GPIO_DIR_OUT);

	__delay_var_cycles(clk_period_cycles);
}

int header_init(swd_header_t *header, swd_port_t port, swd_rw_t rw, uint8_t addr)
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

static int data_write(uint32_t *data)
{
	int parity_cnt = 0;
	for (int i = 0; i < TP_TCV_WIDTH; i++) {
		if (*data & (1 << i)) {
			parity_cnt++;
			iow(1);
		} else
			iow(0);
	}
	if (parity_cnt % 2)
		iow(1);
	else
		iow(0);
	return 0;
}

static int data_read(uint32_t *data)
{
	int parity_cnt = 0;
	*data = 0;
	for (int i = 0; i < TP_TCV_WIDTH; i++) {
		if (ior()) {
			*data |= 1 << i;
			parity_cnt++;
		}
	}
	int parity = ior();
	if ((parity_cnt % 2) != parity)
		return -1;
	return 0;
}

static int transceive(swd_header_t *header, uint32_t *data)
{
	int i;
	int rc;

	for (i = 0; i < 8; i++) {
		iow((*header >> i) & 0x1);
	}
	iotrn(GPIO_DIR_IN);
	uint8_t ack = 0;
	for (i = 0; i < 3; i++) {
		ack |= ior() << i;
	}
	if (ack != SWD_ACK_OK) {
		iotrn(GPIO_DIR_OUT);
		return ack;
	}

	if (*header & (1 << 2)) {
		rc = data_read(data);
		iotrn(GPIO_DIR_OUT);

	} else {
		iotrn(GPIO_DIR_OUT);
		rc = data_write(data);
	}
	hal_gpio_set(pins.swdclk, GPIO_STATE_LOW);
	return rc;
}

int transport_read(uint32_t *data, swd_port_t port, uint8_t addr, unsigned int retries)
{
	int rc;
	header_init(&hdr, port, SWD_RW_R, addr);

	do {
		rc = transceive(&hdr, data);
		if (rc <= 0)
			return rc;
		retries--;
	} while (retries > 0);
	return -rc;
}

int transport_write(swd_port_t port, uint8_t addr, uint32_t data, unsigned int retries)
{
	int rc;
	header_init(&hdr, port, SWD_RW_W, addr);
	do {
		rc = transceive(&hdr, &data);
		if (rc <= 0)
			return rc;
		retries--;
	} while (retries > 0);
	return -rc;
}

int transport_reset(void)
{
	hal_gpio_cfg_dir(pins.swdio, GPIO_DIR_OUT);
	hal_gpio_set(pins.swdio, GPIO_STATE_HIGH);

	for (int i = 0; i < 56; i++) {
		iow(1);
	}

	/* JTAG -> SWD sequence */
	uint16_t tmp = 0x79E7;
	for (int i = 15; i >= 0; i--) {
		iow((tmp >> i) & 0x01);
	}

	for (int i = 0; i < 56; i++) {
		iow(1);
	}

	for (int i = 0; i < 16; i++) {
		iow(0);
	}
	return 0;
}

int transport_init(unsigned int pin_swdclk, unsigned int pin_swdio, unsigned int f_clk)
{
	pins.swdclk = pin_swdclk;
	pins.swdio = pin_swdio;

	clk_period_cycles = F_CPU / f_clk / 2;

	hal_gpio_set(pins.swdclk, GPIO_STATE_LOW);
	hal_gpio_cfg_dir(pins.swdclk, GPIO_DIR_OUT);

	hal_gpio_cfg_dir(pins.swdio, GPIO_DIR_IN);

	return 0;
}

int transport_release()
{
	hal_gpio_cfg_dir(pins.swdclk, GPIO_DIR_IN);
	hal_gpio_cfg_dir(pins.swdio, GPIO_DIR_IN);
	hal_gpio_set(pins.swdio, GPIO_STATE_LOW);
	hal_gpio_set(pins.swdclk, GPIO_STATE_LOW);

	return 0;
}
