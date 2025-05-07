#ifndef VIRTUAL_BATTERY_H
#define VIRTUAL_BATTERY_H

#include "commons.h"
#include <stdint.h>

struct BatteryState
{
    uint64_t SoC_u_n32;

    // These would normally be part of the ConverterState
    uint32_t V_bat_uV_n8;
    uint64_t I_out_nA_n4;
    uint64_t I_in_nA_n4;

    uint32_t V_oc_uV_n8; // For testing only
};

void     battery_initialize();

uint32_t get_V_battery_uV(void);
uint32_t get_V_battery_uV_n32(void);
uint32_t get_SoC_battery_u(void);
void     set_SoC_battery_u(const uint32_t SoC_u);
uint32_t get_V_battery_oc_uV(void); // For testing only

void     set_I_battery_out_nA(const uint64_t I_out_nA);
void     set_I_battery_in_nA(const uint64_t I_in_nA);

void     set_I_battery_out_nA_n4(const uint64_t I_out_nA_n4);
void     set_I_battery_in_nA_n4(const uint64_t I_in_nA_n4);

void     update_battery_states();

#endif //VIRTUAL_BATTERY_H
