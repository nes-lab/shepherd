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

## Changes CGT vs GCC

### Assembly (solved)

- file-ending is different 
	- CGT: `.asm`
	- GCC: `.s`
- setting constants differs from ti compiler (CGT)
	- CGT: `VAR .set value`
	- GCC: `.equ VAR, value` 
- fix is to use [+x with gcc](https://gcc.gnu.org/onlinedocs/gcc/Overall-Options.html)
	-  encapsulation `-x assembler SRCASM -x none` when loading the asm-sources into the compiler

### Multiplication

- pru can only multiply with [register-magic](https://github.com/dinuxbg/gnupru/wiki/Multiplication)
- current code may use loops instead of this magic
- we probably need an asm-version for `mul32()` (with overflow safety, like the c-version)

### Overflow of program memory

- pru1-code compiles, but pru0 fails with ~ 3 kB overflow of program memory (8 kB)
- disabling debug-symbols (`-g0`) does not change program memory, but size of elf-file gets reduced significantly
	- pru1 fw size shrinks from > 40 kB to < 8 kB
- link-time-optimization helps somewhat (`-flto`, `-fuse-linker-plugin`)
	- pru1 fw size shrinks from 7.38 kB to 6.30 kB
	- pru0 overflow reduces from 3060 byte to 2690 byte
- disabling some debug code had just minimal change (-20 byte)
- did read through gnupru github-issues, but found no clue
- did read through large parts of gcc v12.1 doc (gcc.pdf) with no luck
- enabling `-ffast-math` does nothing to our code-size (should only help with float-ops)
- compiling code with `uint32`-only (replaced `uint64`) works!
- compiling u32 with `-fno-inline` overflows by 300 byte -> clean out minor FNs to allow compiling
- compiling original code (u64) with `-fno-inline` without size-hack reduces overflow from 2672 to 2276 bytes. 
	- is this a self-made inline-fuckup?
	- removing `inline` from our codebase brings overflow back to 2672 bytes
	- that is strange! 
- comparing functions-size between source with u64 and u32-mod
  - converter_xyz-Fns grow by factor 1.6 to 2.4
- **issue report confirmed at least 2 gcc-bugs**
- **possible partial solution: divide codebase into the two subsystems.**
  - but timing-constraints were tough already. Probably GCC won't help us here for now. But we keep this solution in our sight.

[more details](./readme_overflow_issue.md)

### Optional

- `-DPRU0` could be replaced, as [gcc defines](https://github.com/dinuxbg/gnuprumcu/blob/master/device-specs/am335x.pru0) something like `-D__AM335X_PRU0__` -> should be compatible with GCT

