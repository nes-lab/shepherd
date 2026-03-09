#ifndef PRU1_DEBUG_ROUTINES_H_
#define PRU1_DEBUG_ROUTINES_H_

#include "gpio.h"
#include "hw_config.h"

// debug macros moved to hw_config.h to be consistent with PRU0

#if DEBUG_LOOP_EN
// "print" number by toggling debug pins bitwise, lowest bitvalue first
static void inline shift_gpio(const uint32_t number)
{
    const uint32_t gpio_off  = read_r30() & ~(DEBUG_PIN0_MASK | DEBUG_PIN1_MASK);
    const uint32_t gpio_one  = gpio_off | (DEBUG_PIN0_MASK | DEBUG_PIN1_MASK);
    const uint32_t gpio_zero = gpio_off | DEBUG_PIN0_MASK;
    uint32_t       value     = number << 1u;
    while (value >>= 1u)
    {
        write_r30(gpio_off);
        write_r30((value & 1u) ? gpio_one : gpio_zero);
    }
    write_r30(gpio_off);
    __delay_cycles(8);
}

// analyze ticks between fn-calls (=time in loop), and output values for min, mean, max on debug pins
static void inline debug_loop_delays(const uint32_t shp_pru_state)
{
    static uint32_t ticks_last  = 0;
    static uint32_t ticks_max   = 0;
    static uint32_t ticks_min   = 0xFFFFFFFF;
    static uint32_t ticks_sum   = 0;
    static uint32_t ticks_count = 0;

    if (shp_pru_state == STATE_RUNNING)
    {
        const uint32_t ticks_current = CT_IEP.TMR_CNT;
        if (ticks_last > ticks_current)
        {
            ticks_last = ticks_current;
            return;
        }
        // this following part should be around 11-14 instructions
        const uint32_t ticks_diff = ticks_current - ticks_last;
        if (ticks_diff > ticks_max) ticks_max = ticks_diff;
        if (ticks_diff < ticks_min) ticks_min = ticks_diff;
        ticks_sum += ticks_diff;
        ticks_count += 1;

        if (ticks_count == (1u << 20u))
        {
            _GPIO_ON(DEBUG_PIN0_MASK | DEBUG_PIN1_MASK);
            __delay_cycles(10);
            _GPIO_OFF(DEBUG_PIN0_MASK | DEBUG_PIN1_MASK);
            __delay_cycles(8);

            shift_gpio(ticks_min);
            shift_gpio(ticks_sum >> 20u);
            shift_gpio(ticks_max);

            ticks_sum   = 0;
            ticks_count = 0;
        }
    }
    ticks_last = CT_IEP.TMR_CNT;
}
#endif

#ifdef GPIO_SPEED_TEST
static void inline debug_gpio_sweep(void)
{
    int32_t value;
    for (int32_t iter = 2048; iter > 0; iter >>= 1u)
    {
        value = iter;
        while (value--) __delay_cycles(1);
        GPIO_TOGGLE(GPIO_POWER_GOOD_HIGH);
        value = iter;
        while (value--) __delay_cycles(1);
        GPIO_TOGGLE(GPIO_POWER_GOOD_HIGH);
    }
}
#endif


#endif //PRU1_DEBUG_ROUTINES_H_
