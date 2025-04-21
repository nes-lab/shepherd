#include "virtual_battery.h"
#include "math64_safe.h"
#include "stdint_fast.h"
#include <stdint.h>

/**
* Battery model based on:
* A Hybrid Battery Model Capable of Capturing Dynamic Circuit Characteristics and Nonlinear Capacity Effects
* (link: https://digitalcommons.unl.edu/cgi/viewcontent.cgi?article=1210&context=electricalengineeringfacpub)
*
* with large parts of the adapted model matching that from:
* An Accurate Electrical Battery Model Capable of Predicting Runtime and I–V Performance
* (link: https://rincon-mora.gatech.edu/publicat/jrnls/tec05_batt_mdl.pdf)
*
* Modified for use with the SHEpHERD testbed (realtime application on a BeagleBone Black PRU):
* - adapted equation 6 to work with discrete, fixed-length time steps and remove rate-capacity effect
* - adapted equation 8 to remove transient voltage effects
* - adapted equations 7 and 12 to use lookup-tables for reduced runtime
**/

static struct BatteryState                  state;
static const volatile struct BatteryConfig *cfg;

static uint32_t                             lookup_V_oc_uV_n8(const uint64_t SoC_u_n32)
{
    uint8_t pos_soc = SoC_u_n32 >> cfg->LUT_voc_SoC_min_log2_u_n32;
    if (pos_soc >= VOC_LUT_SIZE) { pos_soc = VOC_LUT_SIZE - 1; }
    return (uint32_t) cfg->LUT_voc_uV_n8[pos_soc];
}

static uint32_t lookup_R_series_KOhm_n32(const uint64_t SoC_u_n32)
{
    uint8_t pos_soc = SoC_u_n32 >> cfg->LUT_rseries_SoC_min_log2_u_n32;
    if (pos_soc >= RSERIES_LUT_SIZE) { pos_soc = RSERIES_LUT_SIZE - 1; }
    return (uint32_t) cfg->LUT_rseries_KOhm_n32[pos_soc];
}

void battery_initialize(const volatile struct BatteryConfig *const config)
{
    cfg = config;
    set_SoC_u(1000000u);
    state.I_out_nA_n4 = 0;
    state.I_in_nA_n4  = 0;
}

uint32_t get_V_battery_uV(void) { return (uint32_t) (state.V_bat_uV_n8 >> 8u); }

uint32_t get_V_oc_uV(void) // For testing only
{
    return (uint32_t) (state.V_oc_uV_n8 >> 8u);
}

uint32_t get_SoC_u(void) { return (uint32_t) (state.SoC_u_n32 >> 32u); }

void     set_SoC_u(uint32_t SoC_u)
{
    state.SoC_u_n32   = (uint64_t) SoC_u << 32u;
    state.V_bat_uV_n8 = lookup_V_oc_uV_n8(SoC_u << 4);
    state.V_oc_uV_n8  = state.V_bat_uV_n8; // For testing only
}

void set_I_out_nA(const uint64_t I_out_nA) { state.I_out_nA_n4 = I_out_nA << 4u; }

void set_I_in_nA(const uint64_t I_in_nA) { state.I_in_nA_n4 = I_in_nA << 4u; }

void update_states()
{
    uint64_t I_leak_nA_n4 = mul64(state.SoC_u_n32 >> 32lu, cfg->Constant_1_per_kOhm_n18) >> 14;
    uint64_t I_out_nA_n4  = state.I_out_nA_n4 + I_leak_nA_n4;

    // Avoid signed types by branching here
    if (state.I_in_nA_n4 > I_out_nA_n4)
    {
        uint64_t       I_in_nA_n4      = state.I_in_nA_n4 - I_out_nA_n4;

        // Update SoC by tracking the charge (equation 6)
        const uint64_t SoC_delta_u_n32 = mul64(cfg->Constant_s_per_mAs_n48, I_in_nA_n4) >> 20;
        state.SoC_u_n32 += SoC_delta_u_n32;
        // Protect limit SoC to 100%
        if (state.SoC_u_n32 > (1000000ul << 32u)) { state.SoC_u_n32 = 1000000ul << 32u; }

        // Get open-circuit voltage (equation 7)
        const uint64_t V_oc_uV_n8        = lookup_V_oc_uV_n8(state.SoC_u_n32);
        // Get series resistance (equation 12)
        const uint64_t R_series_KOhm_n32 = lookup_R_series_KOhm_n32(state.SoC_u_n32);

        // Update cell voltage (equation 8)
        const uint64_t V_drop_uV_n36     = mul64(R_series_KOhm_n32, I_in_nA_n4);
        state.V_bat_uV_n8                = add64(V_oc_uV_n8, V_drop_uV_n36 >> 28);

        state.V_oc_uV_n8                 = V_oc_uV_n8; // For testing only
    }
    else
    {
        I_out_nA_n4                    = sub64(I_out_nA_n4, state.I_in_nA_n4);

        // Update SoC by tracking the charge (equation 6)
        const uint64_t SoC_delta_u_n32 = mul64(cfg->Constant_s_per_mAs_n48, I_out_nA_n4) >> 20;
        // Protect from overflow
        if (state.SoC_u_n32 > SoC_delta_u_n32) { state.SoC_u_n32 -= SoC_delta_u_n32; }
        else { state.SoC_u_n32 = 0; }

        // Get open-circuit voltage (equation 7)
        const uint64_t V_oc_uV_n8        = lookup_V_oc_uV_n8(state.SoC_u_n32);
        // Get series resistance (equation 12)
        const uint64_t R_series_KOhm_n32 = lookup_R_series_KOhm_n32(state.SoC_u_n32);

        // Update cell voltage (equation 8)
        const uint64_t V_drop_uV_n36     = mul64(R_series_KOhm_n32, I_out_nA_n4);
        state.V_bat_uV_n8                = sub64(V_oc_uV_n8, V_drop_uV_n36 >> 28);

        state.V_oc_uV_n8                 = V_oc_uV_n8; // For testing only
    }
}
