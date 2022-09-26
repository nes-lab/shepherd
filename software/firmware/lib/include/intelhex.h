#ifndef __PROG_INTELHEX_H_
#define __PROG_INTELHEX_H_

#include <stdint.h>

typedef struct
{
    unsigned int len;
    unsigned int address;
    unsigned int type;
    uint8_t      data[256];
} ihex_rec_t;

typedef enum
{
    IHEX_RET_OK   = 0,
    IHEX_RET_DONE = 1
} ihex_ret_t;

typedef struct
{
    uint32_t     address;
    unsigned int len;
    uint8_t     *data;
} ihex_mem_block_t;

int        ihex_reader_init(char *file_mem);
ihex_ret_t ihex_reader_get(ihex_mem_block_t *block);

#endif /* __PROG_INTELHEX_H_ */
