#include "shared_mem.h"

#include "hw_config.h"

bool power_good_update(void)
{
#ifdef GPIO_POWER_GOOD_HIGH
    if (SHARED_MEM.vsource_power_good_trigger_for_pru1)
    {
  #ifdef GPIO_POWER_GOOD_LOW // use both pins to signal pgood (needs cape_hw_v25+)
        if (SHARED_MEM.vsource_power_good_pins_state & 0b10u)
        {
            GPIO_ON(GPIO_POWER_GOOD_HIGH);
            DEBUG_PGOOD_STATE_H1;
        }
        else
        {
            GPIO_OFF(GPIO_POWER_GOOD_HIGH);
            DEBUG_PGOOD_STATE_H0;
        }
        if (SHARED_MEM.vsource_power_good_pins_state & 0b01u)
        {
            GPIO_ON(GPIO_POWER_GOOD_LOW);
            DEBUG_PGOOD_STATE_L1;
        }
        else
        {
            GPIO_OFF(GPIO_POWER_GOOD_LOW);
            DEBUG_PGOOD_STATE_L0;
        }
  #else  // hysteresis (default for cape_hw_v24)
        if (SHARED_MEM.vsource_power_good_pins_state >= 0b11u)
        {
            GPIO_ON(GPIO_POWER_GOOD_HIGH);
            DEBUG_PGOOD_STATE_H1;
        }
        if (SHARED_MEM.vsource_power_good_pins_state == 0b00u)
        {
            GPIO_OFF(GPIO_POWER_GOOD_HIGH);
            DEBUG_PGOOD_STATE_H0;
        }
  #endif // GPIO_POWER_GOOD_LOW
        SHARED_MEM.vsource_power_good_trigger_for_pru1 = false;
        return true;
    }
#endif // GPIO_POWER_GOOD_HIGH
    return false;
}
