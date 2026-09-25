DTS_ALL  := $(sort $(wildcard BB-SHEPHERD-CAPE-*.dts))
DTSP_ALL := $(DTS_ALL:.dts=.dtsp)
DTBO_ALL := $(DTS_ALL:.dts=.dtbo)

CPP_FLAGS = -Iinclude -Iarch -I/opt/source/dtb-6.12/include/ \
				-D__DTS__ -undef -nostdinc

DTC_VERSION = $(shell dtc --version | grep ^Version | sed 's/^.* //g')

# Disable noisy checks by default
ifeq ($(findstring 1,$(DTC_VERBOSE)),)
DTC_FLAGS += -Wno-unit_address_vs_reg \
        -Wno-unit_address_format \
        -Wno-avoid_unnecessary_addr_size \
        -Wno-alias_paths \
        -Wno-simple_bus_reg \
        -Wno-unique_unit_address \
        -Wno-pci_device_reg
endif

ifneq ($(findstring 2,$(DTC_VERBOSE)),)
DTC_FLAGS += -Wnode_name_chars_strict \
        -Wproperty_name_chars_strict
endif

ifeq "$(DTC_VERSION)" "1.6.1"
DTC_FLAGS += -Wno-interrupt_provider
endif

.PHONY: all
all: $(DTBO_ALL)

%.dtsp: %.dts
	@echo ' '
	@echo '*******************  Precompiling DT-File: $< *******************'
	cpp $(CPP_FLAGS) -x assembler-with-cpp $< $@
	@echo ' '

%.dtbo: %.dtsp
	@echo ' '
	@echo '*******************  Compiling DT-File: $@ *******************'
	dtc $(DTC_FLAGS) -b 0 -@ -I dts -O dtb -o $@ $<
	@echo ' '

# keep the preprocessed sources
.SECONDARY: $(DTSP_ALL)

.PHONY: clean
clean:
	@echo ' '
	@echo '*******************  Cleaning DT-Files ************************'
	rm -f $(DTBO_ALL) $(DTSP_ALL)
	@echo ' '

.PHONY: install
install: $(DTBO_ALL)
	@echo ' '
	@echo '*******************  Installing DT-Files **********************'
	@for f in $(DTBO_ALL); do \
		echo "  -> $(DESTDIR)/lib/firmware/$$f"; \
		install -D $$f $(DESTDIR)/lib/firmware/$$f; \
	done
	@echo ' '
