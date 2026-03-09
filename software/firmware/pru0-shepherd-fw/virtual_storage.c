#include "virtual_storage.h"
#include "math64_safe.h"
#include "shared_mem.h"
#include "stdint_fast.h"
#include <stddef.h>
#include <stdint.h>

/*
Battery model based on:

A Hybrid Battery Model Capable of Capturing Dynamic Circuit Characteristics and Nonlinear Capacity Effects
(link: https://digitalcommons.unl.edu/cgi/viewcontent.cgi?article=1210&context=electricalengineeringfacpub)

with large parts of the adapted model matching that from:
An Accurate Electrical Battery Model Capable of Predicting Runtime and I–V Performance
(link: https://rincon-mora.gatech.edu/publicat/jrnls/tec05_batt_mdl.pdf)

Modified for use with the SHEpHERD testbed (realtime application on a BeagleBone Black PRU):

- omit transient voltages (step 4 & 5, expensive calculation)
- omit rate capacity effect (step 1, expensive calculation)
- replace two expensive Fn by LuT
   - mapping SoC to open circuit voltage (step 3)
   - mapping SoC to series resistance (step 4)
- add self discharge resistance (step 2a)
- support signaling 0 % SoC by nulling voltage

Compared to the current shepherd capacitor (charge-based), it:

- supports emulation of battery types like lipo and lead acid (non-linear SOC-to-V_OC mapping)
- has a parallel leakage resistor instead of an oversimplified leakage current
- a series resistance is added to improve model matching
- as a drawback the open circuit voltage is quantified and shows steps (LuT with 128 entries)
*/

struct StorageState
{
    uint64_t SoC_1_n62;
    uint32_t V_OC_uV_n8;
};

static struct StorageState state;

#define STORE_CFG                                                                                  \
    (*((volatile struct StorageConfig *) (PRU_SHARED_MEM_OFFSET +                                  \
                                          offsetof(struct SharedMem, storage_settings))))

#define SoC_MAX_1_n62  ((1ull << 62u) - 1ull)
#define SoC_TO_POS_DIV (62u - 32u - LUT_STORAGE_sLOG)
static uint8_ft position_LuT(void);

void            storage_initialize()
{
    state.SoC_1_n62  = ((uint64_t) STORE_CFG.SoC_init_1_n30) << 32u;
    state.V_OC_uV_n8 = STORE_CFG.LuT_VOC_uV_n8[position_LuT()];
}

static uint8_ft position_LuT()
{
    const uint32_t SoC_n30 = state.SoC_1_n62 >> 32u;
    uint8_ft       pos_SoC = SoC_n30 >> SoC_TO_POS_DIV;
    if (pos_SoC >= LUT_STORAGE_SIZE) pos_SoC = LUT_STORAGE_SIZE - 1u;
    return pos_SoC;
}

uint32_t get_V_OC_uV() { return (uint32_t) (state.V_OC_uV_n8 >> 8u); }

uint32_t get_SoC_1_n30() { return (uint32_t) (state.SoC_1_n62 >> 32u); }

#ifdef EMU_SUPPORT

uint32_t storage_update(const uint32_t I_delta_nA_n4, const bool_ft is_charging)
{
    /*  3 Multiplications in this FN
        dSoC_leak   u64 = u32 * u32
        dSoC_curr   u64 = u32 * u32
        V_delta     u64 = u32 * u32
    */
    uint64_t dSoC_leak_1_n62  = mul32e(state.V_OC_uV_n8 >> 6u, STORE_CFG.Constant_1_per_uV_n60);
    // alternatively this could be added to P_out_fW (like before)
    state.SoC_1_n62           = sub64(state.SoC_1_n62, dSoC_leak_1_n62);

    const uint64_t dSoC_1_n62 = mul32e(I_delta_nA_n4, STORE_CFG.Constant_1_per_nA_n60) >> 2u;
    if (is_charging)
    {
        state.SoC_1_n62 += dSoC_1_n62;
        if (state.SoC_1_n62 > SoC_MAX_1_n62) state.SoC_1_n62 = SoC_MAX_1_n62;
    }
    else state.SoC_1_n62 = sub64(state.SoC_1_n62, dSoC_1_n62);

    const uint8_ft pos_lut           = position_LuT();
    state.V_OC_uV_n8                 = STORE_CFG.LuT_VOC_uV_n8[pos_lut];
    const uint32_t R_series_kOhm_n32 = STORE_CFG.LuT_RSeries_kOhm_n32[pos_lut];
    const uint32_t V_delta_uV_n8     = mul32e(I_delta_nA_n4, R_series_kOhm_n32) >> 28u;

    uint32_t       V_cell_uV_n8;
    if (is_charging) V_cell_uV_n8 = add32(state.V_OC_uV_n8, V_delta_uV_n8);
    else V_cell_uV_n8 = sub32(state.V_OC_uV_n8, V_delta_uV_n8);

    if (state.SoC_1_n62 == 0u) return 0u;
    return V_cell_uV_n8;
}
#endif //EMU_SUPPORT
