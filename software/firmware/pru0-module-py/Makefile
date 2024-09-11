.PHONY : clean

CFLAGS = -std=gnu99
CFLAGS += -funsigned-char
CFLAGS += -funsigned-bitfields

# Optimization -> space-saving
CFLAGS += -Os
CFLAGS += -g
CFLAGS += -flto

CFLAGS += -Wall -Wextra
CFLAGS += -fanalyzer
# workaround to allow compilation without pru
CFLAGS += -D__PYTHON__
CFLAGS += -DPRU0

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
