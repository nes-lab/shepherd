.PHONY : clean

CFLAGS = -std=gnu99
CFLAGS += -funsigned-char
CFLAGS += -funsigned-bitfields

# Cape Hardware, with sensible default
CAPE_HW_VER ?= 25
CFLAGS += -DCAPE_HW_VER=$(CAPE_HW_VER)

# Optimization -> space-saving
CFLAGS += -Os
CFLAGS += -g
CFLAGS += -flto

CFLAGS += -Wall -Wextra -Wpedantic
# TODO: add -Wpedantic and fix warnings
CFLAGS += -fanalyzer
# workaround to allow compilation without pru
CFLAGS += -D__PYTHON__
CFLAGS += -DPRU0
CFLAGS += -DEMU_SUPPORT
# sanitizers for unittests (should be disabled if used as sim-model)
CFLAGS += -fsanitize=undefined
#CFLAGS += -fsanitize=leak  # -> Runtime-error 'cannot allocate memory in static TLS block'
#CFLAGS += -fsanitize=shadow-call-stack # -> compile-error (not implemented / supported)
#CFLAGS += -fsanitize=address # -> unittests don't run at all
CFLAGS += -fcf-protection=full
CFLAGS += -fsanitize-address-use-after-scope
CFLAGS += -fsanitize-trap=all
CFLAGS += -fharden-conditional-branches
# CFLAGS += -fhardened # -> not existing, but it activates the following
CFLAGS += -D_FORTIFY_SOURCE=3 -D_GLIBCXX_ASSERTIONS
CFLAGS += -ftrivial-auto-var-init=zero
CFLAGS += -fPIE  -pie  -Wl,-z,relro,-z,now
CFLAGS += -fstack-protector-strong
CFLAGS += -fstack-clash-protection
CFLAGS += -fPIC  # -> allows symbol 'shared_mem' for hardened shared object

LDFLAGS= -shared -lm

# TODO: cross-compile for windows & linux

BASE_PATH ?= ./..

# include headers with -I or --include_path= (cgt-only)
INCLUDE = -I$(BASE_PATH)/pru0-shepherd-fw/include
INCLUDE += -I$(BASE_PATH)/lib/include
INCLUDE += -I$(BASE_PATH)/include

# sources - add manually
SOURCES = $(BASE_PATH)/pru0-shepherd-fw/virtual_harvester.c
SOURCES += $(BASE_PATH)/pru0-shepherd-fw/virtual_converter.c
SOURCES += $(BASE_PATH)/pru0-shepherd-fw/virtual_storage.c
SOURCES += $(BASE_PATH)/pru0-shepherd-fw/calibration.c
SOURCES += $(BASE_PATH)/pru0-shepherd-fw/math64_safe.c
SOURCES += $(BASE_PATH)/pru0-module-py/shepherd_pru/pru_source.c

OBJECTS=$(SOURCES:.c=.o)

TARGET=./shepherd_pru/_shared_pru.so

all: $(TARGET)

clean:
	rm -f $(OBJECTS) $(TARGET)

$(TARGET) : $(SOURCES)
	$(CC) $(CFLAGS) $(INCLUDE) $(SOURCES) $(LDFLAGS) -o $@

#$(TARGET) : $(OBJECTS)
#	$(CC) $(CFLAGS) -I $(INCLUDE) $(OBJECTS) $(LDFLAGS) -o $@
#$(SOURCES)
