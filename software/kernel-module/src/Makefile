TARGET_MODULE = shepherd

# If we are running by kernel building system
ifneq ($(KERNELRELEASE),)
    obj-m += $(TARGET_MODULE).o
    $(TARGET_MODULE)-objs = module_base.o
    $(TARGET_MODULE)-objs += pru_sync_control.o
else
    KVERSION:=$(shell uname -r)
	BUILDSYSTEM_DIR:=/lib/modules/$(KVERSION)/build
	PWD:=$(shell pwd)
endif

ccflags-y=-I$(src)/../common

#CFLAGS_MODULE = -Wall -Wextra
# -> not enabled by default because it also includes warnings of all external files
# Analyze with:
# make 2> output.txt
# -> look for "shepherd/software/kernel" but
# 	 you can ignore lines with: (in file included) from .. shepherd/
# /opt/shepherd/software/kernel-module/src/ is at beginning of line

# TODO: M=$(CURDIR) should be M=$(PWD)

all: build

build:
	$(MAKE) -C $(BUILDSYSTEM_DIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(BUILDSYSTEM_DIR) M=$(PWD) clean

load:
	insmod ./$(TARGET_MODULE).ko

unload:
	rmmod ./$(TARGET_MODULE).ko

install: all
	@echo 'Installing kernel module'
	-@sudo mkdir /lib/modules/$(KVERSION)/extra/
	@sudo cp $(TARGET_MODULE).ko /lib/modules/$(KVERSION)/extra/
