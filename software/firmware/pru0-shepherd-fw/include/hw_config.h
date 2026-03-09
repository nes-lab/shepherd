#ifndef PRU0_HW_CONFIG_H_
#define PRU0_HW_CONFIG_H_

#include "gpio.h"

#if ((CAPE_HW_VER == 24) || (CAPE_HW_VER == 23) || (CAPE_HW_VER == 22))

  #define SPI_CS_HRV_DAC_PIN    (P9_27)
  #define SPI_CS_HRV_DAC_MASK   BIT_SHIFT(SPI_CS_HRV_DAC_PIN)
  #define SPI_CS_HRV_V_ADC_PIN  (P9_41B)
  #define SPI_CS_HRV_V_ADC_MASK BIT_SHIFT(SPI_CS_HRV_V_ADC_PIN)
  #define SPI_CS_HRV_C_ADC_PIN  (P9_25)
  #define SPI_CS_HRV_C_ADC_MASK BIT_SHIFT(SPI_CS_HRV_C_ADC_PIN)

  #define SPI_CS_EMU_DAC_PIN    (P9_28)
  #define SPI_CS_EMU_DAC_MASK   BIT_SHIFT(SPI_CS_EMU_DAC_PIN)
  #define SPI_CS_EMU_ADC_PIN    (P9_42B)
  #define SPI_CS_EMU_ADC_MASK   BIT_SHIFT(SPI_CS_EMU_ADC_PIN)

  #define SPI_CS_ADCs_MASK (SPI_CS_HRV_V_ADC_MASK | SPI_CS_HRV_C_ADC_MASK | SPI_CS_EMU_ADC_MASK)

  // Pins now share correct mapping with SPI1-HW-Module
  #define SPI_SCLK_MASK    BIT_SHIFT(P9_31)
  #define SPI_MOSI_MASK    BIT_SHIFT(P9_29)
  #define SPI_MISO_MASK    BIT_SHIFT(P9_30)

#elif (CAPE_HW_VER == 25)

    // CS_HRV not used ATM

  #define SPI_CS_EMU_DAC_PIN   (P9_28)
  #define SPI_CS_EMU_DAC_MASK  BIT_SHIFT(SPI_CS_EMU_DAC_PIN)
  #define SPI_CS_EMU_ADC_PIN   (P9_42B)
  #define SPI_CS_EMU_ADC_MASK  BIT_SHIFT(SPI_CS_EMU_ADC_PIN)

  #define SPI_CS_ADCs_MASK     (SPI_CS_EMU_ADC_MASK)

  // Pins now share correct mapping with SPI1-HW-Module
  #define SPI_SCLK_MASK        BIT_SHIFT(P9_31)
  #define SPI_MOSI_MASK        BIT_SHIFT(P9_29)
  #define SPI_MISO_MASK        BIT_SHIFT(P9_30)

  #define GPIO_POWER_GOOD_HIGH BIT_SHIFT(P9_41B)
  #define GPIO_POWER_GOOD_LOW  BIT_SHIFT(P9_27)

#else

  #error "CAPE_HW_VER is either unknown or was unspecified"

#endif

#if (defined(SPI_CS_HRV_DAC_PIN) && defined(SPI_CS_HRV_V_ADC_PIN) && defined(SPI_CS_HRV_C_ADC_PIN))
  #define HRV_AVAILABLE (true)
    // TODO: these macro are used together with XXX_AVAILABLE, but are used differently
    //       the value here avoids compile issues
#else
  #define HRV_AVAILABLE (false)
#endif

#if (defined(SPI_CS_EMU_DAC_PIN) && defined(SPI_CS_EMU_ADC_PIN))
  #define EMU_AVAILABLE (true)
#else
  #define EMU_AVAILABLE (false)
    // TODO: it would be cleaner to just disable individual PIN_usage
#endif


#define DEBUG_EVENT_EN  (0u)
#define DEBUG_PGOOD_EN  (1u) // send power_good to LED1		-> default ON

// both pins have a LED
#define DEBUG_PIN0_MASK BIT_SHIFT(P8_12)
#define DEBUG_PIN1_MASK BIT_SHIFT(P8_11)

#define DEBUG_STATE_0   write_r30(read_r30() & ~(DEBUG_PIN0_MASK | DEBUG_PIN1_MASK))
#define DEBUG_STATE_1   write_r30((read_r30() | DEBUG_PIN0_MASK) & ~DEBUG_PIN1_MASK)
#define DEBUG_STATE_2   write_r30((read_r30() | DEBUG_PIN1_MASK) & ~DEBUG_PIN0_MASK)
#define DEBUG_STATE_3   write_r30(read_r30() | (DEBUG_PIN0_MASK | DEBUG_PIN1_MASK))

#if DEBUG_EVENT_EN
  #define DEBUG_EVENT_STATE_0 DEBUG_STATE_0
  #define DEBUG_EVENT_STATE_1 DEBUG_STATE_1
  #define DEBUG_EVENT_STATE_2 DEBUG_STATE_2
  #define DEBUG_EVENT_STATE_3 DEBUG_STATE_3
#else
  #define DEBUG_EVENT_STATE_0
  #define DEBUG_EVENT_STATE_1
  #define DEBUG_EVENT_STATE_2
  #define DEBUG_EVENT_STATE_3
#endif

#if DEBUG_PGOOD_EN
  #define DEBUG_PGOOD_STATE_L0 write_r30(read_r30() & ~DEBUG_PIN0_MASK)
  #define DEBUG_PGOOD_STATE_L1 write_r30(read_r30() | DEBUG_PIN0_MASK)
  #define DEBUG_PGOOD_STATE_H0 write_r30(read_r30() & ~DEBUG_PIN1_MASK)
  #define DEBUG_PGOOD_STATE_H1 write_r30(read_r30() | DEBUG_PIN1_MASK)
#else
  #define DEBUG_PGOOD_STATE_L0
  #define DEBUG_PGOOD_STATE_L1
  #define DEBUG_PGOOD_STATE_H0
  #define DEBUG_PGOOD_STATE_H1
#endif

#ifdef __PYTHON_TMP_OFF__
void __delay_cycles(const uint32_t num)
{
    // needs no faking
}
#endif

#endif /* PRU0_HW_CONFIG_H_ */
