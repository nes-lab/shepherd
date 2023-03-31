#include "intelhex.h"

static char    *fptr;
static uint32_t reader_addr;

typedef enum
{
    IHEX_REC_TYPE_DATA  = 0u,
    IHEX_REC_TYPE_EOF   = 1u,
    IHEX_REC_TYPE_ESAR  = 2u,
    IHEX_REC_TYPE_START = 3u,
    IHEX_REC_TYPE_ELAR  = 4u,
    IHEX_REC_TYPE_SLAR  = 5u
} ihex_rec_type_t;

enum ihex_error
{
    IHEX_ERR_OK       = 0u,
    IHEX_ERR_START    = 1u,
    IHEX_ERR_CHECKSUM = 2u,
    IHEX_ERR_END      = 3u
};

static inline void         ihex_init(char *const file_mem) { fptr = file_mem; }

/* converts ascii-encoded hex value to number */
static inline unsigned int x2u(char x)
{
    if ((x >= 48) && (x <= 57)) return (unsigned int) (x - 48);
    else if ((x >= 65) && (x <= 70)) return (unsigned int) (x - 55);
    return 256;
}

/* reads a byte from ascii-encoded hex string */
static inline uint8_t read_byte(char **ptr)
{
    uint8_t res = x2u(*((*ptr)++)) << 4;
    res += x2u(*((*ptr)++));
    return res;
}

/* reads a single record from ihex file in memory */
static int ihex_get_rec(ihex_rec_t *const rec)
{
    uint32_t i;

    if (*(fptr++) != ':') return -IHEX_ERR_START;

    rec->len         = read_byte(&fptr);

    /* next is a 16-bit address */
    uint8_t addr_h   = read_byte(&fptr);
    uint8_t addr_l   = read_byte(&fptr);
    rec->address     = (addr_h << 8u) | addr_l;

    rec->type        = read_byte(&fptr);

    /* sum up the bytes for calculating the checksum later */
    uint32_t counter = rec->len + addr_h + addr_l + rec->type;

    for (i = 0; i < rec->len; i++)
    {
        rec->data[i] = read_byte(&fptr);
        counter += rec->data[i];
    }

    uint8_t checksum = read_byte(&fptr);
    counter += checksum;

    const int rc      = ((counter & 0xFF) == 0) ? 0 : -2;

    /* end of line can be one or two characters */
    char      lineend = *(fptr++);
    if (lineend == 0x0D)
    {
        if (*(fptr++) == 0x0A) return rc;
        return -IHEX_ERR_END;
    }
    else if (lineend == 0x0A) return rc;
    else return -IHEX_ERR_END;
}

int ihex_reader_init(char *const file_mem)
{
    ihex_init(file_mem);
    reader_addr = 0;
    return 0;
}

/* consecutive calls read data from hexfile block by block */
ihex_ret_t ihex_reader_get(ihex_mem_block_t *const block)
{
    int               rc;
    static ihex_rec_t rec;
    while (1)
    {
        if ((rc = ihex_get_rec(&rec)) != 0) return rc;

        if (rec.type == IHEX_REC_TYPE_DATA)
        {
            block->address = reader_addr + rec.address;
            block->data    = rec.data;
            block->len     = rec.len;
            return IHEX_RET_OK;
        }
        else if (rec.type == IHEX_REC_TYPE_ESAR)
        {
            uint32_t segment = ((unsigned int) rec.data[0] << 4u) + rec.data[1];
            reader_addr += segment;
        }
        else if (rec.type == IHEX_REC_TYPE_EOF) { return IHEX_RET_DONE; }
    }
}
