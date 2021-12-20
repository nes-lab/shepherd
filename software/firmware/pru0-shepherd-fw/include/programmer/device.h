#ifndef __PROG_DEVICE_H_
#define __PROG_DEVICE_H_

#include <stdint.h>

int dev_halt(void);
int dev_continue(void);
int dev_reset(void);

int mem_write(uint32_t addr, uint32_t data);
int mem_read(uint32_t *data, uint32_t addr);

int nvm_wp_disable(void);
int nvm_wp_enable(void);

int nvm_write(uint32_t address, uint32_t data);
int nvm_erase(void);

#endif /* __PROG_DEVICE_H_ */
