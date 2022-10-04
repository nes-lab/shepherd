PRU_NUM = 0
mkfile_path := $(abspath $(lastword $(MAKEFILE_LIST)))
current_dir := $(notdir $(patsubst %/,%,$(dir $(mkfile_path))))
folder_path := $(dir $(mkfile_path))
PROJ_NAME = $(current_dir)
FW_NAME = shepherd

BASE_PATH ?= ./..

# include headers with -I or --include_path= (cgt-only)
INCLUDE = -I./include

# internal sources
SOURCES = $(notdir $(wildcard ./*.c))
# external sources - add manually
SOURCES += $(BASE_PATH)/lib/src/simple_lock.c
SOURCES += $(BASE_PATH)/lib/src/iep.c
SOURCES += $(BASE_PATH)/lib/src/ringbuffer.c

# internal asm-sources
ASM_SOURCES = $(notdir $(wildcard ./*.asm))
# external asm-sources - add manually
ASM_SOURCES += $(BASE_PATH)/lib/src/register_magic.asm # get_num_size_as_bits, msb_position, max_value, min_value

# look for gcc, but use cgt as fallback / default
ifdef PRU_GCC
ASM_SOURCES += $(BASE_PATH)/lib/src/spi_transfer_pru_gcc.asm # small hack: constants are defined differently
include $(BASE_PATH)/lib/GCC/Makefile
else
ASM_SOURCES += $(BASE_PATH)/lib/src/spi_transfer_pru.asm # adc_readwrite, adc_fastread, dac_write
include $(BASE_PATH)/lib/CGT/Makefile
endif
