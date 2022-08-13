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

# export PRU_GCC=$PWD/tools/pru-elf-2022.05.amd64/bin
# export PRU_SUPPORT=$PWD/tools/pru-software-support-package
# export PATH=$PATH:$PRU_GCC

#PRU_GCC := $(PWD)/tools/pru-elf-2022.05.amd64/bin
#PRU_SUPPORT := $(PWD)/tools/pru-software-support-package

# Common flags
CROSS_COMPILE ?= $(PRU_GCC)/pru-

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
CFLAGS += -isystem include
CFLAGS += -I${PRU_SUPPORT}/include -I${PRU_SUPPORT}/include/am335x



# Per-PRU core flags. The -mmcu option will select the correct linker
# script and will predefine mcu-specific macros.
CFLAGS0 += -mmcu=am335x.pru0 -DPRU0
CFLAGS1 += -mmcu=am335x.pru1 -DPRU1

# include internal Headers
CFLAGS += -I ./include -I ./lib/include
CFLAGS0 += -I ./pru0-shepherd-fw/include
CFLAGS1 += -I ./pru1-shepherd-fw/include

# specialized code-paths for pru0
CFLAGS0e += $(CFLAGS0) -DENABLE_EMULATOR
CFLAGS0h += $(CFLAGS0) -DENABLE_HARVESTER
CFLAGS0a += $(CFLAGS0) -DENABLE_EMULATOR -DENABLE_HARVESTER

# generate files that encode make rules for the .h dependencies
#DEPFLAGS=-MP -MD

COMMON_SRC_DIRS:=./lib/src

SRC_DIRS0:=. $(COMMON_SRC_DIRS) ./pru0-shepherd-fw
SRC_DIRS1:=. $(COMMON_SRC_DIRS) ./pru1-shepherd-fw

SRC0:=$(foreach D,$(SRC_DIRS0),$(wildcard $(D)/*.c))
SRCASM:=$(foreach D,$(SRC_DIRS0),$(wildcard $(D)/*.S))
SRC1:=$(foreach D,$(SRC_DIRS1),$(wildcard $(D)/*.c))

# Where to output compiled objects
OUT := out

# Final ELF image file names
ELF0e := $(OUT)/pru-core0e.elf
ELF0h := $(OUT)/pru-core0h.elf
ELF0a := $(OUT)/pru-core0a.elf
ELF1 := $(OUT)/pru-core1.elf

# ============================ DO NOT TOUCH BELOW ============================
all: $(ELF1) $(ELF0h) $(ELF0e) $(ELF0a) # TODO: reversed for now, because pru0 is still failing
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

$(ELF0e): $(SRC0) $(SRCASM) | $(OUT)
	$(CROSS_COMPILE)gcc $(CFLAGS) $(CFLAGS0e) $(SRCASM) $(SRC0) $(LDFLAGS) -o $@

$(ELF0h): $(SRC0) $(SRCASM) | $(OUT)
	$(CROSS_COMPILE)gcc $(CFLAGS) $(CFLAGS0h) $(SRCASM) $(SRC0) $(LDFLAGS) -o $@
	
$(ELF0a): $(SRC0) $(SRCASM) | $(OUT)
	$(CROSS_COMPILE)gcc $(CFLAGS) $(CFLAGS0a) $(SRCASM) $(SRC0) $(LDFLAGS) -o $@

$(ELF1): $(SRC1) | $(OUT)
	$(CROSS_COMPILE)gcc $(CFLAGS) $(CFLAGS1) $(SRC1) $(LDFLAGS) -o $@

install: $(ELF0) $(ELF1)
	install -D $(ELF0h) /lib/firmware/am335x-pru0-shepherd-fw
	install -D $(ELF1) /lib/firmware/am335x-pru1-shepherd-fw

clean:
	$(RM) -fr $(ELF0e) $(ELF0h) $(ELF0a) $(ELF1) $(OUT)

cscope:
	cscope -bRk

.PHONY: all install clean cscope
