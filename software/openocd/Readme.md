# OpenOCD Programming

## Pin Definition

This method was already used on shepherd v1, but now there is a level-shifter with discrete direction-pin between SBC and Target.
The relevant GPIO for programming are printed below.

### Prog 1

CLK - P9_17 - GPIO[5]
DIO - P9_18 - GPIO[4]
DIR - P8_31 - GPIO[10]
DevTree configures these pins already as GPIO!

### Prog 2

CLK - P8_35 - GPIO[8]
DIO - P8_33 - GPIO[9]
DIR - P8_32 - GPIO[11]
DevTree configures these pins already as GPIO!

## Preparation

First install OpenOCD

```shell
sudo apt install openocd
```

Activate Port A or B with

```Shell
sudo shepherd-sheep -v target-power --gpio-pass --target-port=A
#sudo shepherd-sheep -v target-power --gpio-pass --target-port=B
```

## HowTo

### Info

```Shell
sudo openocd -f shepherd.cfg -c init -c targets -c 'nrf5 info' -c exit
```

## Erase

Mass-erase

```Shell
sudo openocd -f shepherd.cfg -c init -c 'reset halt' -c 'nrf5 mass_erase' -c exit
```

Chip-Erase

```Shell
sudo openocd -f shepherd.cfg -c init -c 'reset halt' -c 'nrf52_recover' -c exit
sudo /usr/bin/openocd -f /opt/shepherd/software/openocd/shepherd.cfg -c 'init; reset halt; nrf52_recover; exit;'
```

### Program

```Shell
sudo openocd -f shepherd.cfg -c "program /opt/shepherd/hardware/tests_manual/nrf52_testable.hex verify reset; exit;"
```

Works, with the output

```Shell
Open On-Chip Debugger 0.12.0
Licensed under GNU GPL v2
For bug reports, read
        http://openocd.org/doc/doxygen/bugs.html
adapter speed: 10 kHz

Info : Linux GPIOD JTAG/SWD bitbang driver
Info : This adapter doesn't support configurable speed
Info : SWD DPIDR 0x2ba01477
Info : [nrf52.cpu] Cortex-M4 r0p1 processor detected
Info : [nrf52.cpu] target has 6 breakpoints, 4 watchpoints
Info : starting gdb server for nrf52.cpu on 3333
Info : Listening on port 3333 for gdb connections
[nrf52.cpu] halted due to debug-request, current mode: Thread
xPSR: 0x01000000 pc: 0x00000134 msp: 0x20002000
** Programming Started **
Info : nRF52840-xxAA(build code: D0) 1024kB Flash, 256kB RAM
Warn : Adding extra erase range, 0x0000307c .. 0x00003fff
** Programming Finished **
** Verify Started **
** Verified OK **
** Resetting Target **
shutdown command invoked
```

## Shortcuts

The config was extended for useful functions:

```Shell
sudo openocd -f shepherd.cfg -c chip_erase
sudo openocd -f shepherd.cfg -c mass_erase
sudo openocd -f /opt/shepherd/software/openocd/shepherd.cfg -c 'prog /opt/shepherd/hardware/tests_manual/nrf52_testable.hex'
# now integrated into sheep
sudo shepherd-sheep program -pA -m1 --mcu-type nrf52 /opt/shepherd/hardware/tests_manual/nrf52_testable.hex
```
