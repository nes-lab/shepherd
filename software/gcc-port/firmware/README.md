# GCC Compiler port for PRU-Firmware

## Installing Prerequisites

run the commands below

```shell
git clone -b gcc-port https://github.com/fedy0/shepherd.git
cd shepherd/software/firmware
chmod +x *.sh
./setup.sh
source ~/.bashrc
```

The commands above do the following:

1. Clone this repository branch

2. Install the cross toolchain from [gnupru](https://github.com/dinuxbg/gnupru.git)

3. Install the PRU software support packages from [pssp](https://github.com/dinuxbg/pru-software-support-package.git)

4. Export toolchain-paths to users environmental variables & reload .bashrc

## Compiling GCC Port

- compilation and cleaning can and should be done without sudo
- installation needs sudo as it copies the firmware to system-

```shell
make 
sudo make install
make clean
```

## Complications

### Assembly (solved)

- file-ending is different 
	- CGT: .asm
	- GCC: .s
- setting constants differs from ti compiler (CGT)
	- CGT: "VAR .set value"
	- GCC: ".equ VAR, value" 

### Multiplication

- pru can only multiply with [register-magic](https://github.com/dinuxbg/gnupru/wiki/Multiplication)
- current code may use loops instead of this magic
- we probably need an asm-version for mul32 (with overflow safety, like the c-version)

### Overflow of program memory - the Story so far

- pru1-code compiles, but pru0 fails with ~ 3 kB overflow of program memory (8 kB)
- disabling debug-symbols (-g0) does not change program memory, but size of elf-file gets reduced significantly
	- pru1 fw size shrinks from > 40 kB to < 8 kB
- link-time-optimization helps somewhat (`-flto`, `-fuse-linker-plugin`)
	- pru1 fw size shrinks from 7.38 kB to 6.30 kB
	- pru0 overflow reduces from 3060 byte to 2690 byte
- disabling some debug code had just minimal change (-20 byte)
- did read through gnupru github-issues, but found no clue
- did read through large parts of gcc v12.1 doc (gcc.pdf) with no luck
- enabling `-ffast-math` does nothing to our code-size (should only help with float-ops)

### Overflow - help from dinuxbg

[issue](https://github.com/dinuxbg/gnupru/issues/43) helped a lot!

- compiling code with `uint32`-only (replaced `uint64`) works!
- compiling u32 with `-no-inline` overflows by 300 byte -> clean out minor FNs to allow compiling
- analyzing codes-size with (u32-version, `-no-inline`, minor cleanout):

```shell
pru-nm --size-sort --print-size out/pru-core0.elf  | grep -w '[Tt]'
...
200019d8 000000a0 t converter_calc_out_power
20000590 000000c0 t harvest_iv_cv
20000338 000000c4 t converter_initialize
200003fc 000000dc t converter_update_cap_storage
200018a8 000000ec t converter_calc_inp_power
20000888 00000100 t harvest_iv_mppt_opt
20000650 00000108 t harvest_iv_mppt_voc
20001000 0000010c t handle_kernel_com.constprop.0.isra.0
200012dc 00000120 t harvest_adc_mppt_voc
20000758 00000130 t harvest_iv_mppt_po
200011a0 0000013c t harvest_adc_ivcurve
20000a10 00000148 t converter_update_states_and_output.constprop.0
20001a78 00000148 t sample_emulator.constprop.0
20000e24 00000158 t handle_buffer_swap.constprop.0
20001e1c 000001c0 T main
200013fc 000001c4 t harvest_adc_mppt_po
20001678 000001cc t sample_init.constprop.0
20001c04 00000218 t event_loop.constprop.0
```

### Overflow - next steps (proposal)

- generate size-map of mem-regions
	- GCC: `pru-nm --size-sort --print-size out/pru-core0.elf  | grep -w '[Tt]'` (needs gnuprumcu-size-hack atm)
	- CGT: ?
	- do sizes look plausable? 
	- how does the result compare to Ti compiler?
	- working pru1-compilation may provide clues - is it also increasing size?
- possible culprits
	- u64-math may produce more complex routines
	- [32 Bit registers](https://github.com/dinuxbg/gnupru/wiki/ABI) instead of 16 Bit -> `-mabi=ti` could be the solution, but fails
		- abi=ti produces undefined references to memcpy and memset -> flag [can't use c std lib](https://gcc.gnu.org/onlinedocs/gcc-12.1.0/gcc/PRU-Options.html#PRU-Options)	
	- accidental included soft-float emulation? no way found to prevent this in GCC

### Optional

- `-DPRU0` could be replaced, as [gcc defines](https://github.com/dinuxbg/gnuprumcu/blob/master/device-specs/am335x.pru0) something like "-D__AM335X_PRU0__" -> should be compatible with GCT

