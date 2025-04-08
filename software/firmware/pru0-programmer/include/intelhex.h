#ifndef __PROG_INTELHEX_H_
#define __PROG_INTELHEX_H_

#include <stdint.h>

typedef struct
{
    uint32_t len;
    uint32_t address;
    uint32_t type;
    uint8_t  data[256];
} ihex_rec_t;

typedef enum
{
    IHEX_RET_OK               = 0u,
    IHEX_RET_DONE             = 1u,
    IHEX_RET_ERR_REC_START    = 11u,
    IHEX_RET_ERR_REC_CHECKSUM = 12u,
    IHEX_RET_ERR_REC_END      = 13u,
    IHEX_RET_ERR_LEN_EOF      = 21u,
    IHEX_RET_ERR_LEN_ESAR     = 22u,
    IHEX_RET_ERR_LEN_ELAR     = 24u,
    IHEX_RET_ERR_TYPE_UNKNOWN = 31u,
} ihex_ret_t;

typedef struct
{
    uint32_t address;
    uint32_t len;
    uint8_t *data;
} ihex_mem_block_t;

ihex_ret_t ihex_reader_init(char *file_mem);
ihex_ret_t ihex_reader_get(ihex_mem_block_t *block);
uint32_t   ihex_get_line_number();

#endif /* __PROG_INTELHEX_H_ */
