#include "programmer/intelhex.h"

static char *ptr;
static unsigned int reader_addr;
static char *reader_file_mem;

static inline int ihex_init(char *file_mem)
{
	ptr = file_mem;
}

/* converts ascii-encoded hex value to number */
static inline unsigned int x2u(char x)
{
	if ((x >= 48) && (x <= 57))
		return (unsigned int)(x - 48);
	else if ((x >= 65) && (x <= 70))
		return (unsigned int)(x - 55);
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
static int ihex_get_rec(ihex_rec_t *rec)
{
	int i;

	if (*(ptr++) != ':')
		return -IHEX_ERR_START;

	rec->len = read_byte(&ptr);

	/* next is a 16-bit address */
	uint8_t addr_h = read_byte(&ptr);
	uint8_t addr_l = read_byte(&ptr);
	rec->address = (addr_h << 8) | addr_l;

	rec->type = read_byte(&ptr);

	/* sum up the bytes for calculating the checksum later */
	unsigned int counter = rec->len + addr_h + addr_l + rec->type;

	for (i = 0; i < rec->len; i++) {
		rec->data[i] = read_byte(&ptr);
		counter += rec->data[i];
	}

	unsigned int checksum = read_byte(&ptr);
	counter += checksum;

	int rc = ((counter & 0xFF) == 0) ? 0 : -2;

	/* end of line can be one or two characters */
	char lineend = *(ptr++);
	if (lineend == 0x0D) {
		if (*(ptr++) == 0x0A)
			return rc;
		return -IHEX_ERR_END;
	} else if (lineend == 0x0A)
		return rc;
	else
		return -IHEX_ERR_END;
}

static int ihex_get_start_addr(uint32_t *addr, char *file_mem)
{
	int rc;
	ihex_rec_t rec;
	ihex_init(file_mem);
	do {
		if ((rc = ihex_get_rec(&rec)) != 0)
			return rc;
	} while (rec.type != IHEX_REC_TYPE_START);
	unsigned int segment = (rec.data[0] << 8) | rec.data[1];
	unsigned int offset = (rec.data[2] << 8) | rec.data[3];

	*addr = segment * 16 + offset;

	return 0;
}

int ihex_reader_init(char *file_mem)
{
	ihex_init(file_mem);
	reader_addr = 0;
}

/* consecutive calls read data from hexfile block by block */
int ihex_reader_get(ihex_mem_block_t *block)
{
	int rc;
	static ihex_rec_t rec;
	while (1) {
		if ((rc = ihex_get_rec(&rec)) != 0)
			return rc;

		if (rec.type == IHEX_REC_TYPE_DATA) {
			block->address = reader_addr + rec.address;
			block->data = rec.data;
			block->len = rec.len;
			return 0;
		} else if (rec.type == IHEX_REC_TYPE_ESAR) {
			unsigned int segment = ((unsigned int)rec.data[0] << 4) + rec.data[1];
			reader_addr += segment;
		} else if (rec.type == IHEX_REC_TYPE_EOF) {
			return 1;
		}
	}
}
