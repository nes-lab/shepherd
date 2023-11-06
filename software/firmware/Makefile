DIRS = pru0-shepherd-fw pru1-shepherd-fw device-tree pru0-programmer pru1-sync
# TODO: this makefile currently can't produce both versions of the programmer

BUILDDIRS = $(DIRS:%=build-%)
CLEANDIRS = $(DIRS:%=clean-%)
INSTADIRS = $(DIRS:%=insta-%)

.PHONY: all
all: $(BUILDDIRS)

.PHONY: clean
clean: $(CLEANDIRS)

.PHONY: install
install: $(INSTADIRS)

$(BUILDDIRS):
	$(MAKE) -C $(@:build-%=%) all

$(CLEANDIRS):
	$(MAKE) -C $(@:clean-%=%) clean

$(INSTADIRS):
	$(MAKE) -C $(@:insta-%=%) install
