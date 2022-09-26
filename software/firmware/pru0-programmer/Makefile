PRU_NUM = 0
mkfile_path := $(abspath $(lastword $(MAKEFILE_LIST)))
current_dir := $(notdir $(patsubst %/,%,$(dir $(mkfile_path))))
folder_path := $(dir $(mkfile_path))
PROJ_NAME = $(current_dir)
FW_NAME = programmer

BASE_PATH ?= ./..

INCLUDE = --include_path=./include
INCLUDE += --include_path=$(BASE_PATH)/pru0-shepherd-fw/include

SOURCES = $(notdir $(wildcard ./*.c))
# add external sources (./lib/src/)
SOURCES += simple_lock.c
SOURCES += iep.c
SOURCES += ringbuffer.c

ASM_SOURCES = $(notdir $(wildcard ./*.asm))
# add external asm-files (./lib/src/)
#ASM_SOURCES += spi_transfer_pru.asm # adc_readwrite, adc_fastread, dac_write


ifdef PRU_CGT
include $(BASE_PATH)/lib/CGT/Makefile
endif
ifdef PRU_GCC
include $(BASE_PATH)/lib/GCC/Makefile
endif
