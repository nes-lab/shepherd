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
- link-time-optimization helps somewhat (-flto, -fuse-linker-plugin)
	- pru1 fw size shrinks from 7.38 kB to 6.30 kB
	- pru0 overflow reduces from 3060 byte to 2690 byte
- disabling some debug code had just minimal change (-20 byte)
- did read through gnupru github-issues, but found no clue
- did read through large parts of gcc v12.1 doc (gcc.pdf) with no luck
- enabling -ffast-math does nothing to our code-size (should only help with float-ops)

### Overflow - next steps (proposal)

- generate size-map of mem-regions 
	- dedicated switches had no success in CFLAGS: --gc-sections, -Map filename
	- do sizes look plausable? 
	- how does the result compare to Ti compiler?
	- working pru1-compilation may provide clues - is it also increasing size?
- keep defective output to analyze with decompiler-tools
	- dedicated switches had no success in CFLAGS: -noinhibit-exec
- compare asm-output of CGT and GCC 
	- file-by-file comparison could give a hint, alone by size-comparison
	- note: LTO and static analyzer may produce additional comments in asm-files
	- note: simple_lock assembly is pretty much the same on both compilers
- possible culprits
	- accidental included soft-float emulation? no way found to prevent this in GCC
	- [32 Bit registers](https://github.com/dinuxbg/gnupru/wiki/ABI) instead of 16 Bit -> "-mabi=ti" could be the solution, but fails
		- abi=ti produces undefined references to memcpy and memset -> do we have to manually link to libc.a? Does not work ...
		- did "-nostdlib -nodefaultlibs -nostartfiles" in fedys branch had a meaning? these flags broke normal compiling
	- u64-math may produce more complex routines

### Optional

- "-DPRU0" could be replaced, as [gcc defines](https://github.com/dinuxbg/gnuprumcu/blob/master/device-specs/am335x.pru0) something like "-D__AM335X_PRU0__" -> should be compatible with GCT

