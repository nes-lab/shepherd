# Next Gen Target Connector

## Current State

- 40 Pin double-sided edge-connector
- safe from reverse plugging
- contains
  - target voltage
  - 16x GPIO (Cape 2.5 routes 11)
  - PowerGood Low & High
  - 4 Programming Lines
  - 3V3
  - lots of grounding for low impedance & shielding
- connector has still 2 unused Pins

## Wishlist

- emulate Cap-Voltage (2nd DAC-Output)
  - +1Pin for aux voltage
- dedicated reset line (nRF & msp have nReset) -> 2 lines or negate if needed
  - +1Pin for reset line
- ~~Identification via I2C-EEPROM~~
  - +2-3Pins (I2C & Write-Protection) OR
  - **just use chip ID / UID**
- ~~replace with FPC- or FCC-cable (flex-printed-circuit, flex-circuit-connector) to be less constraint positioning the target~~
  - features to keep: rotation-safe & shielded (currently 12x extra GND)
  - needed IO: 16 GPIO, 2 Voltages, 2 PwrGood, 4 Prog, 1+ GND => 25+ Pins
  - in total 5 pins extra
  - 40 pin FFC/FPC, 0.5 mm Pitch, 1.5€ -> 05-40-A-0050-A-4-06-4-T-HF
  - 40 pin connector has similar space req. as edge connector, 0.5 € per connector, FFC2B35-40-G
- Target-Board - cut ties to Riotee and default to reset-pin from DK?

=> 2 additional pins fit on current edge-connector

## Desktop-Interface for Targets

A USB-Device for

- programming, debugging & testing targets, and
- local dev-work with capabilities close to Shepherd, mainly
  - record GPIO chatter
  - record power draw
  - emulate energy environments (EEnvs)

Detailed features & requirements might be

- target-port from shepherd
- RP2350 serves as programmer (2x2 traces)
  - staying on the Pico-platform makes Riotee-Repo compatible
  - could just use an of-the-shelve pico-board
- ~~static 2.0 or 3.3 V target-voltage~~ dynamic voltage via DAC
  - for the sake of compatibility to generic targets a DAC should be used
- fully connect (all 16) GPIO
  - directional level-changer in between (if 2.0 V or dynamic target voltage wanted)
- fully connect PowerGood Low & High
  - add LEDs for visualization
- fully connect (new) reset-line
  - add button for manual reset
- fully connect (new) 2nd aux/capacitor voltage
- NOTE: "fully connect" means, that the hardware is made capable. Software-functionality can be implemented on demand
- route pin-traces to a dedicated Pin-header as interface for logic analyzer
- add 2 Ohm shunt-resistor with connectors for external scope or current ranger
- (optional) add VSrc-Lite via additional DAC & ADC + analog frontend
  - MCU emulates "simple" EEnvs, i.e. mean/static 1 mW input (USB1.1 is limiting factor)
  - emulating capacitor-voltage and power good is easy
  - recording current draw should also be feasible
  - (optional) pico2 has 12bit ADCs, could save a separate ADC? probably not
- (optional) external target-power for transducer + harvester via analog switch
- (optional) Sync-Port to connect a small fleet of devices
- (optional) SD-Slot to load/store more complex EEnvs

Main missing features might be

- the full emulation of complex EEnvs,
- time-sync to other observers (sub 1 us of shepherd)
- 100 kHz measurement rate

Pin-estimation aka feasibility Pico2

- 16x GPIO
- 3x Dir GPIO
- 4x Programming
- 2x Dir Programming
- 2x Pwr Good
- 1x Reset-Line
- 5x SPI (DAC & ADC)

Makes a total of 30 Pins.
The RP2354B has 48 GPIO and 2 MB of internal storage (10x10 mm QFN80).
If 30 pins total is enough the RP2354A can be used (7x7 mm QFN60).

**TODO**
- discuss
