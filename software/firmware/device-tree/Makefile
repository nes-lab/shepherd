DTS_ALL  := $(sort $(wildcard BB-SHEPHERD-CAPE-*.dts))
DTSP_ALL := $(DTS_ALL:.dts=.dtsp)
DTBO_ALL := $(DTS_ALL:.dts=.dtbo)


.PHONY: all
all: $(DTBO_ALL)

%.dtsp: %.dts
	@echo ' '
	@echo '*******************  Precompiling DT-File: $< *******************'
	cpp -nostdinc -I include -I arch  -undef -x assembler-with-cpp $< $@
	@echo ' '

%.dtbo: %.dtsp
	@echo ' '
	@echo '*******************  Compiling DT-File: $@ *******************'
	dtc -W no-unit_address_vs_reg -@ -I dts -O dtb -o $@ $<
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
