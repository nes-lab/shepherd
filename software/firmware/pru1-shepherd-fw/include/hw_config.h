#ifndef HW_CONFIG_H_
#define HW_CONFIG_H_

#include "gpio.h"

/* The Arm to Host interrupt for the timestamp event is mapped to Host interrupt 0 -> Bit 30 (see resource_table.h) */
#define HOST_INT_TIMESTAMP_MASK (1U << 30U)

// both pins have a LED
#define DEBUG_PIN0_MASK         BIT_SHIFT(P8_28)
#define DEBUG_PIN1_MASK         BIT_SHIFT(P8_30)

#if (CAPE_HW_VER == 24)

  #define GPIO_POWER_GOOD_HIGH BIT_SHIFT(P8_29) // default PGOOD pin for cape v2.4
  //#define GPIO_POWER_GOOD_LOW     BIT_SHIFT(P8_29)
  /* Algo will switch to hysteresis if _LOW-pin is missing */
  #define GPIO_POWER_GOOD_POS  (9u)

  #define GPIO_MASK            (0x03FFu)
    /* this will be combined with the user-configurable mask to derive the mask used for the Tracer */

    /* overview for pin-mirroring - HW-Rev2.4b

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

Note: this table is copied (for hdf5-reference) in commons.py
*/

#elif (CAPE_HW_VER == 25)

  // GPIO_POWER_GOOD is on PRU0 in this Version!

  /* Algo will switch to hysteresis if _LOW-pin is missing */
  #define GPIO_POWER_GOOD_POS (12u)

  #define GPIO_MASK           (0x3FFFu)
    /* this will be combined with the user-configurable mask to derive the mask used for the Tracer */

    /* overview for pin-mirroring - HW-Rev2.5e

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

Note: this table is copied (for hdf5-reference) in commons.py
*/

#endif

#if (GPIO_MASK > 0xFFFFu)
  #error "Current GPIO-Buffer won't fit the masked values"
#endif


#endif /* HW_CONFIG_H_ */
