# Copyright (c) 2014, Dimitar Dimitrov
#   All rights reserved.
#
#   Redistribution and use in source and binary forms, with or without
#   modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright
#     notice, this list of conditions and the following disclaimer in
#     the documentation and/or other materials provided with the
#     distribution.
#   * Neither the name of the copyright holders nor the names of
#     contributors may be used to endorse or promote products derived
#     from this software without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
#  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
#  IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
#  ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
#  LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
#  CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
#  SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
#  INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
#  CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
#  ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
#  POSSIBILITY OF SUCH DAMAGE.

# Very simple makefile to cross-compile for PRU

CODEDIRS=. lib
INCDIRS=. ./include/ # can be list

# Common flags
CROSS_COMPILE ?= pru-
CFLAGS += -g -Os
CFLAGS += -Wall -Wextra

# automatically add the -I onto each include directory
CFLAGS=$(foreach D,$(INCDIRS),-I$(D)) $(OPT) $(DEPFLAGS)

# for-style iteration (foreach) and regular expression completions (wildcard)
CFILES=$(foreach D,$(CODEDIRS),$(wildcard $(D)/*.c))

# regular expression replacement
OBJECTS=$(patsubst %.c,%.o,$(CFILES))
DEPFILES=$(patsubst %.c,%.d,$(CFILES))

# generate files that encode make rules for the .h dependencies
DEPFLAGS=-MP -MD

# Add remoteproc headers
CFLAGS += -isystem include

# Headers needed by the TI rpmsg library.
CFLAGS += -I${PRU_SUPPORT}/include -I${PRU_SUPPORT}/include/am335x

# Define this to squeeze code size by removing atexit, exit, constructors
# and destructors from CRT.
CFLAGS += -minrt

# Per-PRU core flags. The -mmcu option will select the correct linker
# script and will predefine mcu-specific macros.
CFLAGS0 += -mmcu=am335x.pru0 -DPRU0
CFLAGS1 += -mmcu=am335x.pru1 -nostdlib -nodefaultlibs -nostartfiles -DPRU1

# List of source files to compile for each PRU core.
SRC0 := $(notdir $(wildcard ./pru0-shepherd-fw/*.c) $(wildcard ./lib/src/*.c)) #main0.c calibration.c math64_safe.c ringbuffer.c sampling.c virtual_converter.c virtual_harvester.c spi_transfer_pru.S gpio_io_fast.S register_magic.S iep.c simple_lock.c
SRC1 := $(notdir $(wildcard ./pru1-shepherd-fw/*.c) $(wildcard ./lib/src/*.c)) #main1.c iep.c simple_lock.c

# GCC's -MMD does not yield the needed C dependencies when compiling all
# C source files at once. So manually list headers here.
HEADERS0 := $(notdir $(wildcard ./pru0-shepherd-fw/include/*.h) $(wildcard ./lib/include/*.h) $(wildcard ./include/*.h))
#calibration.h hw_config.h math64_safe.h resource_table0.h resource_table_def.h ringbuffer.h sampling.h spi_transfer_pru.h virtual_converter.h virtual_harvester.h commons.h shepherd_config.h gpio.h iep.h intc.h simple_lock.h stdint_fast.h
HEADERS1 := $(notdir $(wildcard ./pru1-shepherd-fw/include/*.h) $(wildcard ./lib/include/*.h) $(wildcard ./include/*.h))
#debug_routines.h intc_map.h resource_table1.h commons.h shepherd_config.h gpio.h iep.h intc.h simple_lock.h stdint_fast.h

# Where to output compiled objects
OUT := out

# Final ELF image file names
ELF0 := $(OUT)/pru-core0.elf
ELF1 := $(OUT)/pru-core1.elf


# ============================ DO NOT TOUCH BELOW ============================
all: $(ELF0) $(ELF1)
	@echo Success: $^

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

$(OUT):
	mkdir $(OUT)

$(ELF0): $(SRC0) $(HEADERS0) | $(OUT)
	$(CROSS_COMPILE)gcc $(CFLAGS) $(CFLAGS0) $(SRC0) $(LDFLAGS) -o $@

$(ELF1): $(SRC1) $(HEADERS1) | $(OUT)
	$(CROSS_COMPILE)gcc $(CFLAGS) $(CFLAGS1) $(SRC1) $(LDFLAGS) -o $@

clean:
	$(RM) -fr $(ELF0) $(ELF1) $(OUT)

cscope:
	cscope -bRk

.PHONY: all clean cscope
