# History of Changes

## 0.8.25

- special test-version for cape hw v25
- adapt device tree
- power good low & high -> directly in PRU0
- mirror power good in gpio-recording for PRU1
- record r31_00 to r32_11, 12 bit
- py - update & use dir groups A, B, C
- py - remove en_recorder
- py - avoid using harvester

### Tests

+ programming nRF
+ programming MSP
+ correct voltage on target
+ power-recording is fine
+ pins are all recorded
+ uart is received after pins were swapped

### TODO

- make decision dependent from eeprom
- rename power_good_enable/disable_threshold -> power_good_low/high,
- ERROR on PCB - UART swapped
  - resistors are next to each other and are crossable (R66, R68)
