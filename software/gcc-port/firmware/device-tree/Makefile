TARGET = BB-SHPRD-00A0

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
