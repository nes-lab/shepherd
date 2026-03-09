#include "virtual_converter.h"
#include "calibration.h"
#include "commons.h"
#include "hw_config.h"
#include "math64_safe.h"
#include "stdint_fast.h"
#include "virtual_storage.h"
#include <stddef.h>
#include <stdint.h>

#include "fw_config.h"
#include "shared_mem.h"

/* ---------------------------------------------------------------------
 * Virtual Converter, TODO: update description
 * ----------------------------------------------------------------------
 */

inline void set_power_good_state(const uint8_ft value)
{
    SHARED_MEM.vsource_power_good_pins_state       = value & 0x03u;
    SHARED_MEM.vsource_power_good_trigger_for_pru1 = true;
}

#ifdef EMU_SUPPORT
/* private FNs */
static uint32_t get_input_efficiency_n8(uint32_t voltage_uV, uint32_t current_nA);
static uint32_t get_output_inv_efficiency_n4(uint32_t current_nA);


  /* LUT for faster division
 *    current_nA = power_fW / voltage_uV              -> baseline
 *    current_nA_n4 = power_fW_n4 * 1 / voltage_uV    -> wanted format
 *    current_nA_n4 = (power_fW_n4 / 1_n15) * (1_n15 / voltage_uV)
 *    current_nA_n4 = power_fW_n4 * (1_n15 / voltage_uV_p17) / 1_n17 / 1_n15
 *    current_nA_n4 = power_fW_n4 * (1_n15 / voltage_uV_p17) / 1_n32
 * python:
 *    LUT_div = [round(2**15 / (n + 0.5)) for n in range(128)]
 *    print(", ".join([str(min(div, 2**16-1)) for div in LUT_div]))  # noqa: T201
 */
  #define DIV_LUT_SIZE (128u)
// 128 allows range of 131 mV to 16 V
static const uint16_t LUT_div_uV_n27[DIV_LUT_SIZE] = {
        65535, 21845, 13107, 9362, 7282, 5958, 5041, 4369, 3855, 3449, 3121, 2849, 2621, 2427, 2260,
        2114,  1986,  1872,  1771, 1680, 1598, 1524, 1456, 1394, 1337, 1285, 1237, 1192, 1150, 1111,
        1074,  1040,  1008,  978,  950,  923,  898,  874,  851,  830,  809,  790,  771,  753,  736,
        720,   705,   690,   676,  662,  649,  636,  624,  612,  601,  590,  580,  570,  560,  551,
        542,   533,   524,   516,  508,  500,  493,  485,  478,  471,  465,  458,  452,  446,  440,
        434,   428,   423,   417,  412,  407,  402,  397,  392,  388,  383,  379,  374,  370,  366,
        362,   358,   354,   350,  347,  343,  340,  336,  333,  329,  326,  323,  320,  317,  314,
        311,   308,   305,   302,  299,  297,  294,  291,  289,  286,  284,  281,  279,  277,  274,
        272,   270,   267,   265,  263,  261,  259,  257,
};

uint32_t calc_current_nA_n4(const uint64_t power_fW_n4, const uint32_t voltage_uV)
{
    /* ATTENTION: this fn needs exact inputs and is optimized for range of 130 mV to 16 V */
    uint8_t lut_pos = (voltage_uV >> 17u); // 131 mV stepsize
    if (lut_pos >= DIV_LUT_SIZE) lut_pos = DIV_LUT_SIZE - 1u;
    return (uint32_t) (mul64(power_fW_n4, (uint64_t) LUT_div_uV_n27[lut_pos]) >> 32u);
}
#endif // EMU_SUPPORT

/* data-structure that hold the state - variables for local / direct use */
struct ConverterState
{
    uint32_t interval_startup_disabled_drain_n;
    bool_ft  enable_storage;
    uint32_t V_input_uV;

    /* Boost converter */
    bool_ft  enable_boost;
    bool_ft  enable_log_mid;
    uint64_t P_inp_fW_n8;
    uint64_t P_out_fW_n4;
    uint64_t V_mid_uV_n32;
    /* Buck converter */
    bool_ft  enable_buck;
    uint32_t V_out_dac_uV;
    uint32_t V_out_dac_raw;
    /* hysteresis */
    uint32_t V_mid_enable_output_threshold_uV;
    uint32_t V_mid_disable_output_threshold_uV;
    uint32_t dV_mid_enable_output_uV;
};

/* feedback to harvester - global vars */
bool_ft                      feedback_to_hrv    = 0u;
uint32_t                     V_input_request_uV = 0u;

/* (local) global vars to access in update function */
static struct ConverterState state;

#define CNV_CFG                                                                                    \
    (*((volatile struct ConverterConfig *) (PRU_SHARED_MEM_OFFSET +                                \
                                            offsetof(struct SharedMem, converter_settings))))

void converter_initialize()
{
    storage_initialize();

    /* Power-flow in and out of system */
    state.V_input_uV                        = 0u; // TODO: is it used?
    state.P_inp_fW_n8                       = 0ull;
    state.P_out_fW_n4                       = 0ull;
    state.interval_startup_disabled_drain_n = CNV_CFG.interval_startup_delay_drain_n;

    /* container for the stored energy: */
    state.V_mid_uV_n32                      = ((uint64_t) get_V_OC_uV()) << 32u;

    /* Buck Boost */
    state.enable_storage                    = (CNV_CFG.converter_mode & (1u << 0u)) > 0;
    state.enable_boost                      = (CNV_CFG.converter_mode & (1u << 1u)) > 0;
    state.enable_buck                       = (CNV_CFG.converter_mode & (1u << 2u)) > 0;
    state.enable_log_mid                    = (CNV_CFG.converter_mode & (1u << 3u)) > 0;

    state.V_out_dac_uV                      = CNV_CFG.V_output_uV;
    state.V_out_dac_raw                     = cal_conv_uV_to_dac_raw(CNV_CFG.V_output_uV);

    /* prepare hysteresis-thresholds */
    state.dV_mid_enable_output_uV           = CNV_CFG.dV_mid_enable_output_uV;
    state.V_mid_enable_output_threshold_uV  = CNV_CFG.V_mid_enable_output_threshold_uV;
    state.V_mid_disable_output_threshold_uV = CNV_CFG.V_mid_disable_output_threshold_uV;

    if (state.dV_mid_enable_output_uV > state.V_mid_enable_output_threshold_uV)
    {
        // safe V_mid_uV_n32 from underflow in vsource_update_states_and_output()
        // this should not happen, but better safe than ...
        state.V_mid_enable_output_threshold_uV = state.dV_mid_enable_output_uV;
    }

    /* feedback to harvester */
    feedback_to_hrv    = (CNV_CFG.converter_mode & (1u << 4u)) > 0u;
    V_input_request_uV = get_V_OC_uV();

    /* compensate for (hard to detect) current-surge of real capacitors when converter gets turned on
	 * -> this can be const value, because the converter always turns on with "V_intermediate_enable_output_threshold_uV"
	 * TODO: currently neglecting: delay after disabling converter, boost only has simpler formula, second enabling when VCap >= V_out
	 * TODO: this can be done in python, even both enable-cases
	 * Math behind this calculation:
	 * Energy-Change in Storage Cap -> 	E_new = E_old - E_output
	 * with Energy of a Cap 	-> 	E_x = C_x * V_x^2 / 2
	 * combine formulas 		-> 	C_store * V_store_new^2 / 2 = C_store * V_store_old^2 / 2 - C_out * V_out^2 / 2
	 * convert formula to V_new 	->	V_store_new^2 = V_store_old^2 - (C_out / C_store) * V_out^2
	 * convert into dV	 	->	dV = V_store_new - V_store_old
	 * in case of V_cap = V_out 	-> 	dV = V_store_old * (sqrt(1 - C_out / C_store) - 1)
	 */
    // TODO: add tests for valid ranges -> not here
    // TODO: redo unit-test so that normal emulation is used, no special messages anymore (or substantially less)
}

// TODO: explain design goals and limitations... why does the code looks that way
/* Math behind this Converter
 * Individual drains / sources -> 	P_x = I_x * V_x
 * Efficiency 				eta_x = P_out_x / P_inp_x  -> P_out_x = P_inp_x * eta_x
 * Power in and out of Converter -> 	P = P_in - P_out
 * Current in storage cap -> 		I = P / V_cap
 * voltage change for Cap -> 		dV = I * dt / C
 * voltage of storage cap -> 		V += dV
 *
 */
#ifdef EMU_SUPPORT

void converter_calc_inp_power(uint32_t input_voltage_uV, uint32_t input_current_nA)
{
    // info input: voltage is max 5V => 23 bit, current is max 50 mA => 26 bit
    // info output: with eta being 8 bit in size, there is 56 bit headroom for P = U*I = ~ 72 W
    // NOTE: p_inp_fW could be calculated in python, even with efficiency-interpolation -> hand voltage and power to pru
    /* BOOST, Calculate current flowing into the storage capacitor */
    //GPIO_TOGGLE(DEBUG_PIN1_MASK);
    input_voltage_uV = sub32(input_voltage_uV, CNV_CFG.V_input_drop_uV);

    if (input_voltage_uV > CNV_CFG.V_input_max_uV) { input_voltage_uV = CNV_CFG.V_input_max_uV; }

    if (input_current_nA > CNV_CFG.I_input_max_nA) { input_current_nA = CNV_CFG.I_input_max_nA; }

    state.V_input_uV = input_voltage_uV;

    if (state.enable_boost)
    {
        /* disable boost if input voltage too low for boost to work, TODO: is this also in 65ms interval? */
        if (input_voltage_uV < CNV_CFG.V_input_boost_threshold_uV) { input_voltage_uV = 0u; }

        // if (input_voltage_uV > (state.V_mid_uV_n32 >> 32u) + CNV_CFG.V_input_drop_uV)
        // TODO: vdrop in case of v_input > v_storage (non-boost)?
    }
    else if (state.enable_storage)
    {
        // no boost, but cap, for ie. diode+cap (+resistor)
        const uint32_t V_mid_uV  = (state.V_mid_uV_n32 >> 32u);
        const uint32_t V_diff_uV = sub32(input_voltage_uV, V_mid_uV);
        const uint32_t V_res_drop_uV =
                (uint32_t) (mul32e(input_current_nA, CNV_CFG.R_input_kOhm_n22) >> 22u);
        if (V_res_drop_uV > V_diff_uV) { input_voltage_uV = V_mid_uV; }
        else
        {
            input_voltage_uV = sub32(input_voltage_uV, V_res_drop_uV);
        }

        if (feedback_to_hrv)
        {
            // IF input==ivcurve request new CV
            V_input_request_uV = add32(V_mid_uV, add32(V_res_drop_uV, CNV_CFG.V_input_drop_uV));
        }
        else if (input_voltage_uV < V_mid_uV)
        {
            // without feedback there is no usable energy here
            input_voltage_uV = 0u;
        }
    }
    else
    {
        /* direct connection
           modifying V_mid here is not clean, but simpler
           -> V_mid is needed in calc_out, before cap is updated
        */
        state.V_mid_uV_n32 = ((uint64_t) input_voltage_uV) << 32u;
        input_voltage_uV   = 0u;
        // ⤷ input will not be evaluated
    }

    const uint32_t eta_inp_n8 =
            (state.enable_boost) ? get_input_efficiency_n8(input_voltage_uV, input_current_nA)
                                 : (1u << 8u);
    state.P_inp_fW_n8 = mul64(mul32e(eta_inp_n8, input_voltage_uV), input_current_nA);

    //GPIO_TOGGLE(DEBUG_PIN1_MASK);
}

void converter_calc_out_power(const uint32_t current_adc_raw)
{
    // input: current is max 50 mA => 26 bit
    // states: voltage is 23 bit,
    // output: with eta being 14 bit in size, there is 50 bit headroom for P = U*I = ~ 1 W
    //GPIO_TOGGLE(DEBUG_PIN1_MASK);
    /* BUCK, Calculate current flowing out of the storage capacitor */
    //const uint64_t V_mid_uV_n4 = (state.V_mid_uV_n32 >> 28u);
    const uint32_t I_out_nA = cal_conv_adc_raw_to_nA(current_adc_raw);
    const uint32_t eta_inv_out_n4 =
            (state.enable_buck) ? get_output_inv_efficiency_n4(I_out_nA) : (1u << 4u);
    state.P_out_fW_n4 = mul64(mul32e(eta_inv_out_n4, state.V_out_dac_uV), I_out_nA);

    // allows target to initialize and go to sleep
    if (state.interval_startup_disabled_drain_n > 0u)
    {
        state.interval_startup_disabled_drain_n--;
        state.P_out_fW_n4 = 0u;
    }
    //GPIO_TOGGLE(DEBUG_PIN1_MASK);
}

void converter_update_storage(void)
{
    //GPIO_TOGGLE(DEBUG_PIN1_MASK);
    if (state.enable_storage)
    {
        uint32_t V_mid_uV = state.V_mid_uV_n32 >> 32u;
        if (V_mid_uV < 1u) V_mid_uV = 1u; // avoid and possible div0
        const uint64_t P_inp_fW_n4 = state.P_inp_fW_n8 >> 4u;
        // avoid mixing in signed data-types -> slows pru and reduces resolution
        const bool_ft  is_charging = P_inp_fW_n4 >= state.P_out_fW_n4;
        const uint32_t I_delta_nA_n4 =
                is_charging ? calc_current_nA_n4(P_inp_fW_n4 - state.P_out_fW_n4, V_mid_uV)
                            : calc_current_nA_n4(state.P_out_fW_n4 - P_inp_fW_n4, V_mid_uV);
        state.V_mid_uV_n32 = (uint64_t) storage_update(I_delta_nA_n4, is_charging) << 24u;
    }

    // Make sure the voltage stays in it's boundaries, TODO: is this also in 65ms interval?
    if ((uint32_t) (state.V_mid_uV_n32 >> 32u) > CNV_CFG.V_mid_max_uV)
    {
        state.V_mid_uV_n32 = ((uint64_t) CNV_CFG.V_mid_max_uV) << 32u;
    }
    if ((uint32_t) (state.V_mid_uV_n32 >> 32u) < 1u)
    {
        state.V_mid_uV_n32 = ((uint64_t) 1u) << 32u;
    }
    //GPIO_TOGGLE(DEBUG_PIN1_MASK);
}

// TODO: not optimized, initial t_exec is quite high
uint32_t converter_update_states_and_output()
{
    //GPIO_TOGGLE(DEBUG_PIN1_MASK);

    /* connect or disconnect output on certain events */
    static uint32_t sample_count     = 0xFFFFFFF0u;
    static bool_ft  is_outputting    = false;
    const bool_ft   check_thresholds = (++sample_count >= CNV_CFG.interval_check_thresholds_n);
    const uint32_t  V_mid_uV         = (uint32_t) (state.V_mid_uV_n32 >> 32u);
    // this local copy also avoids not enabling pwr_good (due to large dV_mid_enable_output_uV)

    if (check_thresholds)
    {
        sample_count = 0;
        if (is_outputting)
        {
            if (V_mid_uV < state.V_mid_disable_output_threshold_uV) { is_outputting = false; }
        }
        else if (V_mid_uV >= state.V_mid_enable_output_threshold_uV)
        {
            is_outputting      = true;
            /* fast charge external virtual output-cap */
            state.V_mid_uV_n32 = ((uint64_t) sub32(V_mid_uV, state.dV_mid_enable_output_uV)) << 32u;
        }
    }

    if (check_thresholds || CNV_CFG.immediate_pwr_good_signal)
    {
        /* emulate two power-good-signals (low & high) */
        const bool_ft pgood_high = V_mid_uV >= CNV_CFG.V_pwr_good_enable_threshold_uV;
        const bool_ft pgood_low  = V_mid_uV > CNV_CFG.V_pwr_good_disable_threshold_uV;
        set_power_good_state(is_outputting ? (pgood_low | (pgood_high << 1u)) : 0u);
    }

    if (is_outputting || (state.interval_startup_disabled_drain_n > 0u))
    {
        if ((state.enable_buck == false) ||
            (V_mid_uV <= CNV_CFG.V_output_uV + CNV_CFG.V_buck_drop_uV))
        {
            state.V_out_dac_uV = sub32(V_mid_uV, CNV_CFG.V_buck_drop_uV);
        }
        else
        {
            state.V_out_dac_uV = CNV_CFG.V_output_uV;
        }
        state.V_out_dac_raw = cal_conv_uV_to_dac_raw(state.V_out_dac_uV);
    }
    else
    {
        state.V_out_dac_uV  = 0u;
        /* ⤷ needs to be higher or equal min(V_mid_uV) to avoid jitter on low voltages */
        state.V_out_dac_raw = 0u;
    }

    // helps to prevent jitter / noise in gpio-traces
    SHARED_MEM.vsource_skip_gpio_logging =
            (state.V_out_dac_uV < CNV_CFG.V_output_log_gpio_threshold_uV);

    //GPIO_TOGGLE(DEBUG_PIN1_MASK);
    /* output proper voltage to dac */
    return state.V_out_dac_raw;
}


// TODO: global /nonstatic for tests
uint32_t get_input_efficiency_n8(const uint32_t voltage_uV, const uint32_t current_nA)
{
    uint8_t pos_v = voltage_uV >> CNV_CFG.LUT_input_V_min_log2_uV; // V-Scale is Linear!
    uint8_t pos_c = log2safe(current_nA >> CNV_CFG.LUT_input_I_min_log2_nA);
    if (pos_v >= LUT_SIZE) pos_v = LUT_SIZE - 1;
    if (pos_c >= LUT_SIZE) pos_c = LUT_SIZE - 1;
    /* TODO: could interpolate here between 4 values, if there is time for overhead */
    return (uint32_t) CNV_CFG.LUT_inp_efficiency_n8[pos_v][pos_c];
}

uint32_t get_output_inv_efficiency_n4(const uint32_t current_nA)
{
    uint8_t pos_c = log2safe(current_nA >> CNV_CFG.LUT_output_I_min_log2_nA);
    if (pos_c >= LUT_SIZE) pos_c = LUT_SIZE - 1u;
    /* TODO: could interpolate here between 2 values, if there is space for overhead */
    return CNV_CFG.LUT_out_inv_efficiency_n4[pos_c];
}

inline void set_P_input_fW(const uint32_t P_fW) { state.P_inp_fW_n8 = ((uint64_t) P_fW) << 8u; }

inline void set_P_output_fW(const uint32_t P_fW) { state.P_out_fW_n4 = ((uint64_t) P_fW) << 4u; }

inline void set_V_intermediate_uV(const uint32_t C_uV)
{ state.V_mid_uV_n32 = ((uint64_t) C_uV) << 32u; }

inline uint64_t get_P_input_fW(void) { return (state.P_inp_fW_n8 >> 8u); }

inline uint64_t get_P_output_fW(void) { return (state.P_out_fW_n4 >> 4u); }

inline uint32_t get_V_intermediate_uV(void) { return (uint32_t) (state.V_mid_uV_n32 >> 32u); }

inline uint32_t get_V_intermediate_raw(void)
{ return cal_conv_uV_to_dac_raw((uint32_t) (state.V_mid_uV_n32 >> 32u)); }

inline uint32_t get_V_output_uV(void) { return state.V_out_dac_uV; }

uint32_t        get_I_mid_out_nA(void)
{ return (uint32_t) (calc_current_nA_n4(state.P_out_fW_n4, state.V_mid_uV_n32 >> 32u) >> 4u); }

inline bool_ft get_state_log_intermediate(void) { return state.enable_log_mid; }

#endif // EMU_SUPPORT
