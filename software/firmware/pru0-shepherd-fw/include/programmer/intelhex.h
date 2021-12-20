#ifndef __PROG_INTELHEX_H_
#define __PROG_INTELHEX_H_

#include <stdint.h>

typedef struct {
	unsigned int len;
	unsigned int address;
	unsigned int type;
	uint8_t data[256];
} ihex_rec_t;

typedef enum {
	IHEX_REC_TYPE_DATA = 0,
	IHEX_REC_TYPE_EOF = 1,
	IHEX_REC_TYPE_ESAR = 2,
	IHEX_REC_TYPE_START = 3,
	IHEX_REC_TYPE_ELAR = 4,
	IHEX_REC_TYPE_SLAR = 5
} ihex_rec_type_t;

enum ihex_error { IHEX_ERR_OK = 0, IHEX_ERR_START = 1, IHEX_ERR_CHECKSUM = 2, IHEX_ERR_END = 3 };

typedef struct {
	uint32_t address;
	unsigned int len;
	uint8_t *data;
} ihex_mem_block_t;

int ihex_reader_init(char *file_mem);
int ihex_reader_get(ihex_mem_block_t *block);

#endif /* __PROG_INTELHEX_H_ */