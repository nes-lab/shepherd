#ifndef PRU0_HW_CONFIG_H_
#define PRU0_HW_CONFIG_H_

#include "commons.h"
#include "gpio.h"

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

#ifdef CAPE_HW_V25
  #define SPI_CS_ADCs_MASK (SPI_CS_EMU_ADC_MASK)
#else
  #define SPI_CS_ADCs_MASK (SPI_CS_HRV_V_ADC_MASK | SPI_CS_HRV_C_ADC_MASK | SPI_CS_EMU_ADC_MASK)
#endif // CAPE_HW_V25

// Pins now share correct mapping with SPI1-HW-Module
#define SPI_SCLK_MASK   BIT_SHIFT(P9_31)
#define SPI_MOSI_MASK   BIT_SHIFT(P9_29)
#define SPI_MISO_MASK   BIT_SHIFT(P9_30)

// both pins have a LED
#define DEBUG_PIN0_MASK BIT_SHIFT(P8_12)
#define DEBUG_PIN1_MASK BIT_SHIFT(P8_11)

#define POWER_GOOD_LOW  BIT_SHIFT(P9_27)
#define POWER_GOOD_HIGH BIT_SHIFT(P9_41B)

#ifdef __PYTHON__
void __delay_cycles(const uint32_t num)
{
    // needs no faking
}
#endif

#endif /* PRU0_HW_CONFIG_H_ */
