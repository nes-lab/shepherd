CAPE_HW_VER ?= 24

ifeq ($(CAPE_HW_VER), 22)
override CAPE_HW_VER = 24
else ifeq ($(CAPE_HW_VER), 23)
override CAPE_HW_VER = 24
endif

TARGET = BB-SHPRD-$(CAPE_HW_VER)A0
# command above sets the default (v2.5e Rev 0, Emu only)
# -> currently supported: 22, 23, 24 (HRV & EMU) & 25 (EMU only)
# i.e. overwrite with: make CAPE_HW_VER=24
# TODO: could be dynamically determined by reading EEPROM

$(TARGET).dtbo: $(TARGET).dtsp
	@echo ' '
	@echo '*******************  Compiling DT-File ************************'
	dtc -W no-unit_address_vs_reg -@ -I dts -O dtb -o $@ $<
	@echo ' '

$(TARGET).dtsp: $(TARGET).dts
	@echo ' '
	@echo '*******************  Precompiling DT-File *********************'
	cpp -nostdinc -I include -I arch  -undef -x assembler-with-cpp $< $@
	@echo ' '

.PHONY: all
all: $(TARGET).dtbo

.PHONY: clean
clean:
	@echo ' '
	@echo '*******************  Cleaning DT-Files ************************'
	rm -f $(TARGET).dtbo
	rm -f $(TARGET).dtsp
	@echo ' '

.PHONY: install
install: $(TARGET).dtbo
	@echo ' '
	@echo '*******************  Installing DT-Files **********************'
	install -D $(TARGET).dtbo \
		$(DESTDIR)/lib/firmware/$(TARGET).dtbo
	@echo ' '
