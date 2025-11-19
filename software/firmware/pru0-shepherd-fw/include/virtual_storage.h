#ifndef VIRTUAL_STORAGE_H
#define VIRTUAL_STORAGE_H

#include "commons.h"
#include <stdint.h>

void     storage_initialize();

uint32_t get_SoC_1_n30(void); // for testing
uint32_t get_V_OC_uV(void);   // for testing

uint32_t storage_update(const uint64_t, const bool_ft);

#endif //VIRTUAL_STORAGE_H
