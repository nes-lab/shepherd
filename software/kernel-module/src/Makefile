TARGET = shepherd
KVERSION := $(shell uname -r)
KDIR ?= /lib/modules/$(KVERSION)/build

obj-m += $(TARGET).o
$(TARGET)-objs += sync_ctrl.o
$(TARGET)-objs += pru_comm.o
$(TARGET)-objs += sysfs_interface.o
$(TARGET)-objs += pru_mem_msg_sys.o
$(TARGET)-objs += pru_firmware.o
$(TARGET)-objs += module_base.o

ccflags-y=-I$(src)/../common

# CFLAGS_MODULE = -Wall -Wextra
# -> not enabled by default because it also includes warnings of all external files
# Analyze with:
# make 2> output.txt
# -> look for "shepherd/software/kernel" but
# 	 you can ignore lines with: (in file included) from .. shepherd/


all: build

build:
	make -C $(KDIR) M=$(CURDIR) modules

clean:
	make -C $(KDIR) M=$(CURDIR) clean

install: all
	@echo 'Installing kernel module'
	@sudo cp $(TARGET).ko /lib/modules/$(KVERSION)/extra/
