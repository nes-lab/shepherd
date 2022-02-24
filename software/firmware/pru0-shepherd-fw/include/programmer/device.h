/*
 * The purpose of the following definitions is to provide a common interface for different devices
 * that are programmed over different protocols. The interface provides all methods necessary
 * to write a firmware image onto the device.
 */

#ifndef __PROG_DEVICE_H_
#define __PROG_DEVICE_H_

#include <stdint.h>

typedef enum {
	DRV_ERR_TIMEOUT = -3,
	DRV_ERR_VERIFY = -2,
	DRV_ERR_GENERIC = -1,
	DRV_ERR_OK = 0,
	DRV_ERR_PROTECTED = 1,
} drv_err_t;

typedef int (*fn_open_t)(unsigned int, unsigned int, unsigned int);
typedef int (*fn_erase_t)(void);
typedef int (*fn_read_t)(uint32_t *dst, uint32_t address);
typedef int (*fn_write_t)(uint32_t address, uint32_t data);
typedef int (*fn_close_t)(void);

typedef struct {
	fn_open_t open;
	fn_erase_t erase;
	fn_read_t read;
	fn_write_t write;
	fn_close_t close;
	/* processor word width */
	unsigned int word_width_bytes;
} device_driver_t;

extern device_driver_t nrf52_driver;
extern device_driver_t msp430fr_driver;

#endif /* __PROG_DEVICE_H_ */
