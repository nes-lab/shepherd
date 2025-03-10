This PCB was never produced due to unforseen changes in the supply-chain.
Two ICs disappeared from the earth.

## Main Goals

- replace old target connector
- redo interface to target completely
- add 17 V regulator to clean POE-Supply

## Implemented Changes v2.5b/c

- production optimized for JLC
  - 6 layer includes via filling & capping (type 7) -> optional as via in pad is not used
  - vias were reduced to 0.2 mm hole, 0.35 ring dia
- replace target header with 40pin edge-Connector
- add 17V converter (previously external)
- Screw-Connector now supports 7 - 17V
- remove XYZ - for this last version - testbed only
  - usb-input
  - harvester frontend
  - ~~external switch & LED~~
- pin-changes on BBB Sockets, documented in `shepherd-git/hardware/_deprecated/beaglebone_pinout_concept.xlsx`
  - P8_14 is GPIO7, was targets GPIO0
  - P8_17 is GPIO8, was targets GPIO1
  - P8_27 is pru1_GPIO8, was pru_uart_tx
  - P8_28 is pru1_GPIO10, in addition to PRU1-LED0 (switch to input)
  - P8_29 is pru1_GPIO9, was pru1_batOK (switch to input)
  - P8_30 is pru1_GPIO11, in addition to PRU1-LED1 (switch to input)
  - P8_37 is now controlling direction of gpio-group A
  - P8_38 is now controlling direction of gpio-group B
  - P8_40 is pru1_GPIO7, was pru_uart_rx
  - P9_14 is now controlling direction of gpio-group C, was EN_Recorder
  - P9_25 is free, was CS_ADC2_REC
  - P9_27 is PWR_GOOD_L, was CS_DAC_REC
  - P9_41B is PWR_GOOD_H, was CS_ADC1_REC
- Target mapping Changed!
  - Target-GPIO9..11 are now input pru0-r31 (P8_29, P8_28, P8_30)
  - Target_GPIO0 is now UART-RX
  - BBone Pins changed
  - PinDirections are different
  - new BBone to target mapping is in separate section below, it now supports recording 12 pins
- GPS-Sync-Header added
