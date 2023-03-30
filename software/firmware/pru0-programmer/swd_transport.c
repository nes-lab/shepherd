#include "swd_transport.h"
#include "delay.h"
#include "sys_gpio.h"

/* bit width of SWD transfer -> always 32 bit */
#define TP_TCV_WIDTH (32u)

/* Selects direction of SWD transfer */
typedef enum
{
    /* Host to target */
    SWD_RW_W = 0u,
    /* Target to host */
    SWD_RW_R = 1u,
} swd_rw_t;

typedef enum
{
    SWD_ACK_OK    = 0x1u,
    SWD_ACK_WAIT  = 0x2u,
    SWD_ACK_FAULT = 0x4u,
} swd_ack_t;

typedef uint8_t     swd_header_t;
static swd_header_t hdr;

static struct
{
    uint8_t swd_clk;
    uint8_t swd_io;
    uint8_t swd_dir;
} pins;

static uint32_t clk_delay_cycles;

/* SWD write bit routine */
static void     iow(gpio_state_t swdio_state)
{
    sys_gpio_set(pins.swd_io, swdio_state);
    sys_gpio_set(pins.swd_clk, GPIO_STATE_LOW);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.swd_clk, GPIO_STATE_HIGH);
    __delay_var_cycles(clk_delay_cycles);
}

/* SWD read bit routine */
static gpio_state_t ior(void)
{
    sys_gpio_set(pins.swd_clk, GPIO_STATE_LOW);
    __delay_var_cycles(clk_delay_cycles);
    const gpio_state_t ret = sys_gpio_get(pins.swd_io);
    sys_gpio_set(pins.swd_clk, GPIO_STATE_HIGH);
    __delay_var_cycles(clk_delay_cycles);
    return ret;
}

/* SWD turn-around cycle: Control is handed over from host to target or vice versa. */
static void iotrn(gpio_dir_t dir)
{
    sys_gpio_cfg_dir(pins.swd_io, GPIO_DIR_IN);
    sys_gpio_set(pins.swd_dir, GPIO_STATE_LOW); // LOW => SWD_IO is INPUT

    sys_gpio_set(pins.swd_clk, GPIO_STATE_LOW);
    __delay_var_cycles(clk_delay_cycles);
    sys_gpio_set(pins.swd_clk, GPIO_STATE_HIGH);
    if (dir == GPIO_DIR_OUT)
    {
        sys_gpio_set(pins.swd_dir, GPIO_STATE_HIGH); // LOW => SWD_IO is INPUT
        sys_gpio_cfg_dir(pins.swd_io, GPIO_DIR_OUT);
    }

    __delay_var_cycles(clk_delay_cycles);
}

/**
 * Initializes a SWD header according to the given parameters.
 *
 * @param header pointer to header structure
 * @param port selects target port: Debug Port or Memory Access Port
 * @param rw read or write access
 * @param addr port address
 */
static int header_init(swd_header_t *const header, const swd_port_t port, const swd_rw_t rw,
                       const uint8_t addr)
{
    *header           = 0x81u | ((addr & 0xCu) << 1u) | (port << 1u) | (rw << 2u);

    uint8_t bit_count = 0u;
    for (uint8_t i = 1u; i < 5u; i++)
    {
        if (*header & (0x01u << i)) bit_count++;
    }
    if (bit_count % 2u) *header |= (1u << 5u);

    return 0;
}

/* Writes a word during host to target phase of SWD transfer */
static int data_write(const uint32_t *const data)
{
    uint8_t parity_cnt = 0u;
    for (uint8_t i = 0u; i < TP_TCV_WIDTH; i++)
    {
        if (*data & (1u << i))
        {
            parity_cnt++;
            iow(GPIO_STATE_HIGH);
        }
        else iow(GPIO_STATE_LOW);
    }
    if (parity_cnt % 2u) iow(GPIO_STATE_HIGH);
    else iow(GPIO_STATE_LOW);
    return 0;
}

/* Reads a word during target to host phase of SWD transfer */
static int data_read(uint32_t *const data)
{
    uint8_t parity_cnt = 0u;
    *data              = 0u;
    for (uint8_t i = 0u; i < TP_TCV_WIDTH; i++)
    {
        if (ior())
        {
            *data |= 1u << i;
            parity_cnt++;
        }
    }
    const uint8_t parity = ior();
    if ((parity_cnt % 2u) != parity) return -1;
    return 0;
}

/**
 * SWD transfer routine. Transfers a word from host to target or vice versa depending
 * on the settings provided in the header.
 *
 * @param header SWD header specifies port, address and direction of transfer
 * @param data pointer to source or destination of transfer
 *
 * @returns result of transfer in terms of SWD acknowledgment
 */
static int transceive(const swd_header_t *const header, uint32_t *const data)
{
    uint8_t i;
    int     rc;

    for (i = 0; i < 8u; i++) { iow((*header >> i) & 0x1); }
    iotrn(GPIO_DIR_IN);
    uint8_t ack = 0u;
    for (i = 0; i < 3u; i++) { ack |= ior() << i; }
    if (ack != SWD_ACK_OK)
    {
        iotrn(GPIO_DIR_OUT);
        return ack;
    }

    if (*header & (1 << 2))
    {
        rc = data_read(data);
        iotrn(GPIO_DIR_OUT);
    }
    else
    {
        iotrn(GPIO_DIR_OUT);
        rc = data_write(data);
    }
    sys_gpio_set(pins.swd_clk, GPIO_STATE_LOW);
    return rc;
}

int swd_transport_read(uint32_t *const dst, const swd_port_t port, const uint8_t addr,
                       uint32_t retries)
{
    int rc;
    header_init(&hdr, port, SWD_RW_R, addr);

    do {
        rc = transceive(&hdr, dst);
        if (rc <= 0) return rc;
        retries--;
    }
    while (retries > 0);
    return -rc;
}

int swd_transport_write(const swd_port_t port, const uint8_t addr, uint32_t data, uint32_t retries)
{
    int rc;
    header_init(&hdr, port, SWD_RW_W, addr);
    do {
        rc = transceive(&hdr, &data);
        if (rc <= 0) return rc;
        retries--;
    }
    while (retries > 0u);
    return -rc;
}

int swd_transport_reset(void)
{
    sys_gpio_set(pins.swd_io, GPIO_STATE_HIGH);
    sys_gpio_set(pins.swd_dir, GPIO_STATE_HIGH); // LOW => SWD_IO is INPUT
    sys_gpio_cfg_dir(pins.swd_io, GPIO_DIR_OUT);

    for (uint8_t i = 0u; i < 56u; i++) { iow(GPIO_STATE_HIGH); }

    /* JTAG -> SWD sequence */
    uint16_t tmp = 0x79E7;
    for (int i = 15; i >= 0; i--) { iow((tmp >> i) & 0x01u); }

    for (uint8_t i = 0u; i < 56u; i++) { iow(GPIO_STATE_HIGH); }

    for (uint8_t i = 0u; i < 16u; i++) { iow(GPIO_STATE_LOW); }
    return 0;
}

int swd_transport_init(uint8_t pin_swd_clk, uint8_t pin_swd_io, uint8_t pin_swd_dir, uint32_t f_clk)
{
    pins.swd_clk     = pin_swd_clk;
    pins.swd_io      = pin_swd_io;
    pins.swd_dir     = pin_swd_dir;

    clk_delay_cycles = F_CPU / f_clk / 2u;

    sys_gpio_set(pins.swd_clk, GPIO_STATE_LOW);
    sys_gpio_cfg_dir(pins.swd_clk, GPIO_DIR_OUT);

    sys_gpio_cfg_dir(pins.swd_io, GPIO_DIR_IN);

    sys_gpio_set(pins.swd_dir, GPIO_STATE_LOW); // LOW => SWD_IO is INPUT
    sys_gpio_cfg_dir(pins.swd_dir, GPIO_DIR_OUT);

    return 0;
}

int swd_transport_release()
{
    sys_gpio_cfg_dir(pins.swd_clk, GPIO_DIR_IN);
    sys_gpio_set(pins.swd_clk, GPIO_STATE_LOW);

    sys_gpio_cfg_dir(pins.swd_io, GPIO_DIR_IN);
    sys_gpio_set(pins.swd_io, GPIO_STATE_LOW);

    sys_gpio_set(pins.swd_dir, GPIO_STATE_LOW); // LOW => SWD_IO is INPUT

    return 0;
}
