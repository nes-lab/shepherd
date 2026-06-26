# Programmer / Debugger for the MSP430

## Current state

- [MSP on Riotee can be softbricked](https://github.com/NessieCircuits/Riotee_ProbeSoftware/issues/10)
- PRU-programmer on shepherd is a lite-version of Riotee-Probe
  - 2022-09: [pru-programmer](https://github.com/nes-lab/shepherd/tree/main/software/firmware/pru0-programmer) was designed
  - 2023-01: [riotee-programmer](https://github.com/NessieCircuits/Riotee_ProbeSoftware/tree/main/firmware/src) was designed (more generalized approach)
  - 2026-06: riotee-code was merged into shepherd - with minor adjustments to the protocol
- support via OpenOCD would be perfect
  - broad support for targets and programmers (even Linux-GPIO)
  - it allows connecting via GDB
  - BUT SBW is too niche, timing-sensitive and different from ARM/SWD in OpenOCD
- there are no TI tools supporting ARM (beaglebone or raspberry pi)
- mspdebug exists as the next best thing to OpenOCD
  - BUT relies mostly on programmers (i.e. [rpi-project](https://github.com/jonathangjertsen/rpi-msp430))
  - PIF (parallel port) programmer for GPIO is available, BUT it only supports JTAG
  - it also seems
- Putting a raspberry pico inbetween as a programmer would also work
  - Pi-Pico-Sbw https://github.com/bigjosh/pi-pico-sbw
  - could leverage https://github.com/bigjosh/pi-pico-sbw/blob/main2/mpy/sbw_native.c

### OpenOCD

- simplelink (not our targets)
  - https://software-dl.ti.com/msp430/msp430_public_sw/mcu/msp430/simplelink-openocd/latest/index_FDS.html
- TI OpenOCD (also not our targets)
  - https://software-dl.ti.com/ccs/esd/vscode/ti-embedded-debug/ti-openocd.html
  - https://github.com/TexasInstruments/ti-openocd
- adapt SBW to openOCD?
  - analog to https://github.com/arduino/OpenOCD/blob/c404ff5d3a2ec568daa106455845dd403b08dab4/src/target/adi_v5_swd.c
  - patchguide https://openocd.org/doc-release/doxygen/patchguide.html
  - probably not feasible

### MSPDebug

https://dlbeer.co.nz/mspdebug/
https://github.com/dlbeer/mspdebug

Olimex Programmers
- MSP430-JTAG-TINY
  - https://www.olimex.com/Products/MSP430/JTAG/MSP430-JTAG-TINY-V2/
- MSP430-JTAG-ISO 
  - https://www.olimex.com/Products/MSP430/JTAG/MSP430-JTAG-ISO/ (obsolete)
  - https://www.olimex.com/Products/MSP430/JTAG/MSP430-JTAG-ISO-MK2/

There seems to be a [device_gpio & device_bp](https://github.com/dlbeer/mspdebug/blob/master/drivers/pif.h)
- pif is parallel port, bp is bus-pirate
- device_gpio uses [/sys/class/gpio](https://github.com/dlbeer/mspdebug/blob/master/drivers/pif.c#L445)
- HOW? `mspdebug --help` does not list GPIO. change was 12 years old, but apt-version is 13 years old ...
- according to [this website](https://rpm.pbone.net/manpage_idpl_29179731_numer_1_nazwa_mspdebug.html) only JTAG is supported for GPIO-device, proposed call: `mspdebug gpio -d "tdi=7 tdo=8 tms=9 tck=4"`
- **it seems all 3 devices in pif.c lack SBW-support

There is a [PR for bitbanging via FTDI](https://github.com/dlbeer/mspdebug/pull/118) that could be adapted to linux-GPIO.

Compile

```Shell
# sudo apt install libusb-1.0-0-dev
sudo apt install libusb-dev
cd
git clone https://github.com/dlbeer/mspdebug
# git clone https://github.com/dlbeer/mspdebug/tree/v0.26
cd mspdebug
git checkout tags/v0.26
make WITHOUT_READLINE=1
# ~ 3min
sudo make install WITHOUT_READLINE=1
# /usr/local/lib//mspdebug
/usr/local/bin/mspdebug --version
```


TODO:
- adapt gpio-driver of openOCD for mspdebug?

## Program

sudo shepherd-sheep -v target-power --gpio-pass --target-port=A

sudo shepherd-sheep program -pA -m2 --mcu-type msp430 /var/shepherd/content/fw/nes_lab/msp430_deep_sleep/build.hex
sudo shepherd-sheep program -pA -m2 --mcu-type msp430 /opt/shepherd/hardware/tests_manual/msp430_testable.hex