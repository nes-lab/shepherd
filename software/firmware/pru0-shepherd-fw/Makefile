PRU_NUM = 0
mkfile_path := $(abspath $(lastword $(MAKEFILE_LIST)))
current_dir := $(notdir $(patsubst %/,%,$(dir $(mkfile_path))))
folder_path := $(dir $(mkfile_path))
PROJ_NAME = $(current_dir)
FW_NAME = shepherd

BASE_PATH ?= ./..

INCLUDE = --include_path=./include

SOURCES = $(notdir $(wildcard ./*.c))
# add external sources (./lib/src/)
SOURCES += simple_lock.c
SOURCES += iep.c
SOURCES += ringbuffer.c

ASM_SOURCES = $(notdir $(wildcard ./*.asm))
# add external asm-files (./lib/src/)
ASM_SOURCES += register_magic.asm # get_num_size_as_bits, msb_position, max_value, min_value

ifdef PRU_CGT
ASM_SOURCES += spi_transfer_pru.asm # adc_readwrite, adc_fastread, dac_write
include $(BASE_PATH)/lib/CGT/Makefile
endif
ifdef PRU_GCC
ASM_SOURCES += spi_transfer_pru_gcc.asm # small hack, constants are defined differently
include $(BASE_PATH)/lib/GCC/Makefile
endif
