#ifndef __PROG_SWD_TRANSPORT_H_
#define __PROG_SWD_TRANSPORT_H_

#include <stdint.h>

typedef enum
{
    /* Debug Port */
    SWD_PORT_DP = 0u,
    /* Memory Access Port */
    SWD_PORT_AP = 1u,
} swd_port_t;

/**
 * Reads a word from the specified address of the specified port. Checks for the acknowledgment
 * and retries for given number of times or until the transfer is successful
 *
 * @param dst pointer to which result is written
 * @param port selects target port: Debug Port or Memory Access Port
 * @param addr port address
 * @param retries number of retries before transfer is considered failed
 *
 * @returns 0 on success
 */
int swd_transport_read(uint32_t *dst, swd_port_t port, uint8_t addr, uint32_t retries);

/**
 * Writes a word to the specified address of the specified port. Checks for the acknowledgment
 * and retries for given number of times or until the transfer is successful
 *
 * @param data word to be written
 * @param port selects target port: Debug Port or Memory Access Port
 * @param addr port address
 * @param retries number of retries before transfer is considered failed
 *
 * @returns 0 on success
 */
int swd_transport_write(swd_port_t port, uint8_t addr, uint32_t data, uint32_t retries);

/**
 * Initializes transport layer
 *
 * @param pin_swd_clk pin number for SWDCLK signal. Note: Only supports pins of GPIO port 0.
 * @param pin_swd_io pin number for SWDIO signal. Note: Only supports pins of GPIO port 0.
 * @param pin_swd_dir pin number for direction signal. Note: Only supports pins of GPIO port 0.
 * @param f_clk frequency of SWDCLK signal
 *
 * @returns 0 on success
 */
int swd_transport_init(uint8_t pin_swd_clk, uint8_t pin_swd_io, uint8_t pin_swd_dir,
                       uint32_t f_clk);

/**
 * Puts SWDIO and SWDCLK signals to High-Z
 */
int swd_transport_release(void);

/**
 * Outputs the JTAG reset sequence via SWD pins
 */
int swd_transport_reset(void);

#endif /* __PROG_SWD_TRANSPORT_H_ */
