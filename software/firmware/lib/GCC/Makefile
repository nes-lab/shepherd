# contains most "magic" for gcc-compiling the pru-code

.DEFAULT_GOAL := all

ifeq ($(MAKECMDGOALS),all)
ifndef PRU_GCC
define GCC_ERROR_BODY

*******************************************************************************
PRU_GCC environment variable is not set. Examples given:
(Linux) export PRU_GCC=/path/to/gnupru/

Link to GNUPRU: https://github.com/dinuxbg/gnupru/
*******************************************************************************

endef
$(error $(GCC_ERROR_BODY))
endif
ifndef PRU_GCC_SUPPORT
define SUP_ERROR_BODY

*******************************************************************************
PRU_GCC_SUPPORT environment variable is not set. Examples given:
(Linux) export PRU_GCC_SUPPORT=/path/to/ti/pru-software-support-package

Link to Git: https://github.com/dinuxbg/pru-software-support-package
		-> clone the linux-4.19-rproc branch
*******************************************************************************

endef
$(error $(SUP_ERROR_BODY))
endif
endif

# Common flags
CROSS_COMPILE ?= $(PRU_GCC)/bin/pru-

# Files to include

INCLUDE += -isystem ${PRU_GCC_SUPPORT}/include
INCLUDE += -isystem ${PRU_GCC_SUPPORT}/include/am335x
INCLUDE += -I$(BASE_PATH)/include
INCLUDE += -I$(BASE_PATH)/lib/include

# NOTE: autoinclude is easy, but cgt can't handle it (>7 kb fw-increase)
#SOURCES += $(notdir $(wildcard $(BASE_PATH)/lib/src/*.c))
#ASM_SOURCES += $(notdir $(wildcard $(BASE_PATH)/lib/src/*.asm))

# Debug symbols and intermediate file keeping
CFLAGS += -g
#CFLAGS += -save-temps

# Language-Features, c99 wanted, but it produces errors from compiler/io.h
CFLAGS += -std=gnu99
CFLAGS += -funsigned-char
CFLAGS += -funsigned-bitfields

# Optimization -> space-saving (mixing whole-program-switch with LTO can break code!)
CFLAGS += -Os
#CFLAGS += -fwhole-program
CFLAGS += -fuse-linker-plugin
CFLAGS += -flto

# Avoid inlining -> to debug compiler-output (ie. pru-nm --size-sort --print-size out/pru-core0.elf  | grep -w '[Tt]')
#CFLAGS += -fno-inline

# PRU-Specific Optimizations:
# Squeeze code size by removing atexit, exit, constructors and destructors from CRT.
# We cannot activate minrt when using stdio
CFLAGS += -minrt
# use pru-specific asm-cmds
CFLAGS += -mloop
# switch ABI, TODO: breaks compilation with undefined references to memset, memcpy
#CFLAGS += -mabi=ti
#CFLAGS += -mno-memcpy

# replace stdlibs, TEST to allow -mabi=ti
#CFLAGS += -nostdlib -nodefaultlibs -nostartfiles
#CFLAGS += -L${PRU_GCC}/../pru-elf/lib
#CFLAGS += -lc #loads libc.a
#CFLAGS += -static

# c++ specific flags,
#CFLAGS += -fno-rtti
CFLAGS += -fno-exceptions

# Warnings and Static Analyzer
CFLAGS += -Wall -Wextra
CFLAGS += -fanalyzer

# Add external Headers: remoteproc?, PSSP
#CFLAGS += -isystem include


# Per-PRU core flags. The -mmcu option will select the correct linker
# script and will predefine mcu-specific macros.
# TODO: temporary size-hack (XL instead of just X), as one firmware does not fit into IMEM
ifeq ($(PROJ_NAME), pru0-shepherd-fw)
CFLAGS += -mmcu=am335xl.pru0 -DPRU0
else
CFLAGS += -mmcu=am335x.pru$(PRU_NUM) -DPRU$(PRU_NUM)
endif

#ifeq ($(PRU_NUM), 0)
#CFLAGS += -mmcu=am335x.pru0 -DPRU0
#endif

#ifeq ($(PRU_NUM), 1)
#CFLAGS += -mmcu=am335x.pru1 -DPRU1
#endif

# generate files that encode make rules for the .h dependencies
#DEPFLAGS=-MP -MD

# Where to output compiled objects
GEN_DIR := gen_gcc

TARGET := $(GEN_DIR)/pru$(PRU_NUM)-$(FW_NAME)-fw.elf
TARGET_PATH := $(folder_path)$(TARGET)

# special folder to find source-files in (auto)
VPATH += $(BASE_PATH)/lib/src

.PHONY: all
all: printStart $(TARGET) printEnd

.PHONY: printStart
printStart:
	@echo ''
	@echo ''
	@echo '************************************************************'
	@echo 'Building project: $(PROJ_NAME) with GNU GCC'

.PHONY: printEnd
printEnd:
	@echo ''
	@echo 'Output files can be found in the "$(GEN_DIR)" directory'
	@echo 'Resulting firmware is $(TARGET_PATH)'
	@echo 'Size in bytes:'
	@stat -L -c %s $(TARGET_PATH)
	@echo ''
	@echo '************************************************************'
	@echo 'Internal statistics of ELF'
	@echo ''
	@$(CROSS_COMPILE)size $(TARGET_PATH)
	@echo ''
	@$(CROSS_COMPILE)nm --size-sort --print-size $(TARGET_PATH)  | grep -w '[Tt]'
	@echo ''
	@echo 'Finished building project: $(PROJ_NAME) (with GNU GCC)'
	@echo '************************************************************'
	@echo ''


%.s : %.elf
	$(CROSS_COMPILE)objdump -S -d $< > $@

# Binary images for IMEM and DMEM memories. Might be useful
# for firmware loaders that cannot handle ELF.
%.imem.bin : %.elf
	$(CROSS_COMPILE)objcopy -O binary  --only-section=.text* $< $@

%.dmem.bin : %.elf
	$(CROSS_COMPILE)objcopy -O binary              \
	  --only-section=.data*                        \
	  --only-section=.bss*                         \
	  --set-section-flags .bss=alloc,load,contents \
	  $< $@

$(GEN_DIR):
	mkdir $(GEN_DIR)

$(TARGET): $(SOURCES) $(ASM_SOURCES) | $(GEN_DIR)
	$(CROSS_COMPILE)gcc $(CFLAGS) $(INCLUDE) -x assembler $(ASM_SOURCES) -x none $(SOURCES) $(LDFLAGS) -o $@

.PHONY: clean
clean:
	@echo ''
	@echo ''
	@echo '************************************************************'
	@echo 'Cleaning project: $(PROJ_NAME) (with GNU GCC)'
	@echo ''
	@echo 'Removing files in the "$(GEN_DIR)" directory'
	$(RM) -fr $(ELF) $(GEN_DIR)
	@echo ''
	@echo 'Finished cleaning project: $(PROJ_NAME) (with GNU GCC)'
	@echo '************************************************************'
	@echo ''
	@echo ''

.PHONY: install
install: $(ELF)
	@echo ''
	@echo ''
	@echo '************************************************************'
	@echo 'Installing project: $(PROJ_NAME) (with GNU GCC)'
	@echo ''
	@echo 'Installing firmware to /lib/firmware'
	install -D $(ELF) /lib/firmware/am335x-pru$(PRU_NUM)-$(FW_NAME)-fw
	@echo ''
	@echo '************************************************************'
	@echo ''
	@echo ''

.PHONY: all install clean
