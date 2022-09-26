PRU_NUM = 1
mkfile_path := $(abspath $(lastword $(MAKEFILE_LIST)))
current_dir := $(notdir $(patsubst %/,%,$(dir $(mkfile_path))))
folder_path := $(dir $(mkfile_path))
PROJ_NAME = $(current_dir)
FW_NAME = shepherd

BASE_PATH ?= ./..

INCLUDE = --include_path=./include

SOURCES = $(notdir $(wildcard ./*.c))
# also add external files (./lib/src/)
SOURCES += iep.c
SOURCES += simple_lock.c

ASM_SOURCES = $(notdir $(wildcard ./*.asm))
# add external asm-files (./lib/src/)
#ASM_SOURCES += spi_transfer_pru.asm # adc_readwrite, adc_fastread, dac_write


ifdef PRU_CGT
include $(BASE_PATH)/lib/CGT/Makefile
endif
ifdef PRU_GCC
include $(BASE_PATH)/lib/GCC/Makefile
endif
