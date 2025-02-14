#include "intelhex.h"

static char    *fptr;
static uint32_t reader_addr;
static uint32_t start_exe_addr;
static uint32_t line_number;

typedef enum
{
    IHEX_REC_TYPE_DATA  = 0u,
    IHEX_REC_TYPE_EOF   = 1u,
    IHEX_REC_TYPE_ESAR  = 2u,
    IHEX_REC_TYPE_START = 3u,
    IHEX_REC_TYPE_ELAR  = 4u,
    IHEX_REC_TYPE_SLAR  = 5u
} ihex_rec_type_t;

static inline void ihex_init(char *const file_mem)
{
    fptr        = file_mem;
    line_number = 0u;
}

uint32_t                   ihex_get_line_number() { return line_number; }

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

    if (*(fptr++) != ':') return IHEX_RET_ERR_REC_START;

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

    const int rc = ((counter & 0xFF) == 0) ? IHEX_RET_OK : IHEX_RET_ERR_REC_CHECKSUM;
    line_number++;

    /* end of line can be one or two characters */
    char lineend = *(fptr++);
    if (lineend == 0x0D)
    {
        if (*(fptr++) == 0x0A) return rc;
        return IHEX_RET_ERR_REC_END;
    }
    else if (lineend == 0x0A) return rc;
    else return IHEX_RET_ERR_REC_END;
}

int ihex_reader_init(char *const file_mem)
{
    ihex_init(file_mem);
    reader_addr    = 0u;
    start_exe_addr = 0u;
    return 0;
}

/* consecutive calls read data from hexfile block by block */
ihex_ret_t ihex_reader_get(ihex_mem_block_t *const block)
{
    static ihex_rec_t rec;
    static int        ret_err;
    while (1)
    {
        ret_err ihex_get_rec(&rec) if (ret_err != 0) return ret_err;

        if (rec.type == IHEX_REC_TYPE_DATA)
        {
            // len could be 0, so take a shortcut here and advance
            if (rec.len > 0u)
            {
                block->address = reader_addr + rec.address;
                block->data    = rec.data;
                block->len     = rec.len;
                return IHEX_RET_OK;
            }
        }
        else if (rec.type == IHEX_REC_TYPE_EOF)
        {
            if (rec.len > 0u) return IHEX_RET_ERR_LEN_EOF;
            return IHEX_RET_DONE;
        }
        else if (rec.type == IHEX_REC_TYPE_ESAR)
        {
            /* Extended Segment Address
            - multiply by 16 and add to each subsequent data record address
            - extends address range from 64k to 1M
            */
            if (rec.len != 2u) return IHEX_RET_ERR_LEN_ESAR;
            reader_addr = (uint32_t) rec.data[0] << 12u;
            reader_addr |= (uint32_t) rec.data[1] << 4u;
        }
        else if (rec.type == IHEX_REC_TYPE_START)
        {
            start_exe_addr = ((uint32_t) rec.data[0] << 24u); // Code Segment
            start_exe_addr |= ((uint32_t) rec.data[1] << 16u);
            start_exe_addr |= ((uint32_t) rec.data[2] << 8u); // Program counter
            start_exe_addr |= ((uint32_t) rec.data[3] << 0u);
            // not used
        }
        else if (rec.type == IHEX_REC_TYPE_ELAR)
        {
            /* Extended Linear Address
            The two data bytes (big endian) specify the upper 16 bits of
            the 32 bit absolute address for all subsequent type 00 records.
            */
            if (rec.len != 2u) return IHEX_RET_ERR_LEN_ELAR;
            reader_addr = (uint32_t) rec.data[0] << 24u;
            reader_addr |= (uint32_t) rec.data[1] << 16u;
        }
        else if (rec.type == IHEX_REC_TYPE_SLAR)
        {
            start_exe_addr = ((uint32_t) rec.data[0] << 24u);
            start_exe_addr |= ((uint32_t) rec.data[1] << 16u);
            start_exe_addr |= ((uint32_t) rec.data[2] << 8u);
            start_exe_addr |= ((uint32_t) rec.data[3] << 0u);
        }
        else
        {
            // all known types are handled above, so this is undefined territory
            return IHEX_RET_ERR_TYPE_UNKNOWN;
        }
    }
}
