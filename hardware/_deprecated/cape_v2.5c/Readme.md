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

## Pin Def

### Target Port - Cape 2.4

```
pru_reg     name            BB_pin	sys_pin sys_reg
r31_00      TARGET_GPIO0    P8_45	P8_14, g0[26] -> 26
r31_01      TARGET_GPIO1    P8_46	P8_17, g0[27] -> 27
r31_02      TARGET_GPIO2    P8_43	P8_16, g1[14] -> 46
r31_03      TARGET_GPIO3    P8_44	P8_15, g1[15] -> 47
r31_04      TARGET_GPIO4    P8_41	P8_26, g1[29] -> 61
r31_05      TARGET_GPIO5    P8_42	P8_36, g2[16] -> 80
r31_06      TARGET_GPIO6    P8_39	P8_34, g2[17] -> 81
r31_07      TARGET_UART_RX  P8_40	P9_26, g0[14] -> 14
r31_08      TARGET_UART_TX  P8_27	P9_24, g0[15] -> 15
r30_09/out  TARGET_BAT_OK   P8_29	-
```

### Target Port - Cape 2.5

```
pru_reg       name              BB_pin	sys_pin sys_reg
pru1_r31_00   TARGET_GPIO0/uRx  P8_45	P9_26, g0[14] -> 14 (also Sys/PRU-UART)
pru1_r31_01   TARGET_GPIO1/uTx  P8_46	P9_24, g0[15] -> 15 (also Sys/PRU-UART)
pru1_r31_02   TARGET_GPIO2      P8_43	P8_16, g1[14] -> 46
pru1_r31_03   TARGET_GPIO3      P8_44	P8_15, g1[15] -> 47
pru1_r31_04   TARGET_GPIO4      P8_41	P8_26, g1[29] -> 61
pru1_r31_05   TARGET_GPIO5      P8_42	P8_36, g2[16] -> 80
pru1_r31_06   TARGET_GPIO6      P8_39	P8_34, g2[17] -> 81
pru1_r31_07   TARGET_GPIO7      P8_40	P8_14, g0[26] -> 26
pru1_r31_08   TARGET_GPIO8      P8_27	P8_17, g0[27] -> 27
pru1_r31_09   TARGET_GPIO9      P8_29	-
pru1_r31_10   TARGET_GPIO10     P8_28   - !! PRU1-LED0, direction must be changed in DTree for debugging
pru1_r31_11   TARGET_GPIO11     P8_30   - !! PRU1-LED1, direction must be changed in DTree

pru0_r30_05   PWR_GOOD_L        P9_27     (was CS_DAC_REC), gets added to bit 12 for GPIO-Sampling
pru0_r30_06   PWR_GOOD_H        P9_41B    (was CS_ADC1_REC), gets added to bit 13 for GPIO-Sampling
pru0_r30_07   -                 P9_25     (was CS_ADC2_REC)
```
