#include <stdint.h>
#include <stdio.h>
#include "commons.h"
#include "shepherd_config.h"
#include "gpio.h"
#include "hw_config.h"
#include "stdint_fast.h"
#include "virtual_source.h"
#include "float_pseudo.h"

/* ---------------------------------------------------------------------
 * Virtual Source, TODO: update description
 *
 * input:
 *    output current: current flowing out of shepherd
 *    output voltage: output voltage of shepherd
 *    input current: current value from recorded trace
 *    input voltage: voltage value from recorded trace
 *
 * output:
 *    toggles shepherd output
 *
 * VirtCap emulates a energy harvesting supply chain storage capacitor and
 * buck/boost converter
 *
 * This code is written as part of the thesis of Boris Blokland
 * Any questions on this code can be send to borisblokland@gmail.com
 * ----------------------------------------------------------------------
 */

/* private FNs */
static inline ufloat conv_adc_raw_to_nA(uint32_t current_raw); // TODO: the first two could also be helpful for sampling
static inline uint32_t conv_uV_to_dac_raw(ufloat voltage_uV);

static ufloat input_efficiency(uint32_t voltage_uV, uint32_t current_nA);
static ufloat get_output_efficiency(const uint32_t current);

/* data-structure that hold the state - variables for direct use */
struct VirtSource_State {
	/* Boost converter */
	ufloat P_inp_pW;
	ufloat P_out_pW;
	ufloat dt_us_per_C_nF;
	ufloat V_store_uV;
	uint32_t interval_check_thrs_sample;
	/* Buck converter */
	ufloat V_out_uV;
	uint32_t V_out_dac_raw;
};

/* (local) global vars to access in update function */
static struct VirtSource_State vss;
static struct VirtSource_Config vs_cfg;
static struct Calibration_Config cal_cfg;
#define dt_us_const 	(SAMPLE_INTERVAL_NS / 1000u)

void vsource_struct_init(volatile struct VirtSource_Config *const vsc_arg)
{
	/* this init is nonsense, but testable for byteorder and proper values */
	uint32_t i32 = 0u;
	vsc_arg->converter_mode = i32++;

	vsc_arg->C_output_nF = i32++;
	vsc_arg->V_inp_boost_threshold_uV = i32++;
	vsc_arg->C_storage_nF = i32++;
	vsc_arg->V_storage_init_uV = i32++;
	vsc_arg->V_storage_max_uV = i32++;
	vsc_arg->I_storage_leak_nA = i32++;
	vsc_arg->V_storage_enable_threshold_uV = i32++;
	vsc_arg->V_storage_disable_threshold_uV = i32++;
	vsc_arg->interval_check_thresholds_ns = i32++;
	vsc_arg->V_pwr_good_low_threshold_uV = i32++;
	vsc_arg->V_pwr_good_high_threshold_uV = i32++;
	vsc_arg->dV_stor_en_thrs_uV = i32++;

	vsc_arg->V_output_uV = i32++;
	vsc_arg->dV_stor_low_uV = i32++;

	uint8_t i8A = 0u;
	uint8_t i8B = 0u;
	for (uint32_t outer = 0u; outer < LUT_SIZE; outer++)
	{
		for (uint32_t inner = 0u; inner < LUT_SIZE; inner++)
		{
			vsc_arg->LUT_inp_efficiency_n8[outer][inner] = i8A++;
		}
		vsc_arg->LUT_out_inv_efficiency_n10[outer] = i8B++;
	}
}


void vsource_init(volatile const struct VirtSource_Config *const vsc_arg, volatile const struct Calibration_Config *const cal_arg)
{
	/* Initialize state */
	cal_cfg = *cal_arg;
	vs_cfg = *vsc_arg; // TODO: can be changed to pointer again, has same performance

	/* Boost Reg */
	vss.dt_us_per_C_nF = div((ufloat){.value=dt_us_const, .shift=0}, (ufloat){.value=vs_cfg.C_storage_nF, .shift=0});
	/* Power-flow in and out of system */
	vss.P_inp_pW = (ufloat){.value = 0, .shift = 0};
	vss.P_out_pW = (ufloat){.value = 0, .shift = 0};
	/* container for the stored energy: */
	vss.V_store_uV = (ufloat){.value = vs_cfg.V_storage_init_uV, .shift = 0};

	/* Check Output-Limits every n Samples: */
	vss.interval_check_thrs_sample = vs_cfg.interval_check_thresholds_ns / SAMPLE_INTERVAL_NS;

	/* Buck Boost */
	vss.V_out_uV = (ufloat){.value = vs_cfg.V_output_uV, .shift = 0};

	vss.V_out_dac_raw = conv_uV_to_dac_raw(vss.V_out_uV);

	/* compensate for (hard to detect) current-surge of real capacitors when converter gets turned on
	 * -> this can be const value, because the converter always turns on with "V_storage_enable_threshold_uV"
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
	/*
	const ufloat V_old_sq_uV = mul0(vs_cfg.V_storage_enable_threshold_uV, 0, vs_cfg.V_storage_enable_threshold_uV, 0);
	const ufloat V_out_sq_uV = mul2(vss.V_out_uV, vss.V_out_uV);
	const ufloat cap_ratio   = div0(vs_cfg.C_output_nF, 0, vs_cfg.C_storage_nF, 0);
	const ufloat V_new_sq_uV = sub2(V_old_sq_uV, mul2(cap_ratio, V_out_sq_uV));
	GPIO_ON(DEBUG_PIN1_MASK);
	vss.dV_stor_en_uV = sub1r(vs_cfg.V_storage_enable_threshold_uV, 0, sqrt_rounded(V_new_sq_uV)); // reversed, because new voltage is lower then old
	*/
	// TODO: add tests for valid ranges
}

// TODO: explain design goals and limitations... why does the code looks that way
/* Math behind this Converter
 * Individual drains / sources -> 	P_x = I_x * V_x * eta_x  (eta is efficiency)
 * Power in and out of Converter -> 	P = P_in - P_out
 * Current in storage cap -> 		I = P / V_cap
 * voltage change for Cap -> 		dV = I * dt / C
 * voltage of storage cap -> 		V += dV
 *
 */

void vsource_calc_inp_power(const uint32_t input_current_nA, const uint32_t input_voltage_uV)
{
	/* BOOST, Calculate current flowing into the storage capacitor */
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	ufloat V_inp_uV = { .value = 0u, .shift = 0 };
	/* disable boost if input voltage too low for boost to work, TODO: is this also in 65ms interval? */
	if (input_voltage_uV >= vs_cfg.V_inp_boost_threshold_uV)
		V_inp_uV.value = input_voltage_uV;
	/* limit input voltage when higher than voltage of storage cap, TODO: is this also in 65ms interval? */
	if (compare_gt(V_inp_uV, vss.V_store_uV))
		V_inp_uV = vss.V_store_uV;

	const ufloat eta_inp = input_efficiency(input_voltage_uV, input_current_nA);
	vss.P_inp_pW = mul(V_inp_uV, (ufloat){ .value = input_current_nA, .shift = 0 });
	vss.P_inp_pW = mul(vss.P_inp_pW, eta_inp);
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
}

void vsource_calc_out_power(const uint32_t current_adc_raw)
{
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	/* BUCK, Calculate current flowing out of the storage capacitor*/
	const ufloat I_out_nA = conv_adc_raw_to_nA(current_adc_raw);
	const ufloat eta_inv_out = get_output_efficiency(current_adc_raw); // TODO: wrong input, should be nA
	const ufloat dP_leak_pW = mul(vss.V_store_uV, (ufloat){.value=vs_cfg.I_storage_leak_nA, .shift=0}); // TODO: re-enable
	vss.P_out_pW = mul(I_out_nA, vss.V_out_uV);
	vss.P_out_pW = mul(vss.P_out_pW, eta_inv_out);
	vss.P_out_pW = add(vss.P_out_pW, dP_leak_pW); // TODO: re-enable
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
}

void vsource_update_capacitor(void)
{
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	/* Sum up Power and calculate new Capacitor Voltage
	 * NOTE: slightly more complex code due to uint -> the only downside to ufloat
	 */
	ufloat P_sum_pW; //
	ufloat I_cStor_nA;
	ufloat dV_cStor_uV;
	if (compare_gt(vss.P_inp_pW, vss.P_out_pW)) {
		P_sum_pW = sub(vss.P_inp_pW, vss.P_out_pW);
		I_cStor_nA = div(P_sum_pW, vss.V_store_uV);
		dV_cStor_uV = mul(I_cStor_nA, vss.dt_us_per_C_nF);
		vss.V_store_uV = add(vss.V_store_uV, dV_cStor_uV);
	} else {
		P_sum_pW = sub(vss.P_out_pW, vss.P_inp_pW);
		I_cStor_nA = div(P_sum_pW, vss.V_store_uV);
		dV_cStor_uV = mul(I_cStor_nA, vss.dt_us_per_C_nF);
		vss.V_store_uV = sub(vss.V_store_uV, dV_cStor_uV);
	}
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
}

uint32_t vsource_update_buckboost(void)
{
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	// Make sure the voltage stays in it's boundaries, TODO: is this also in 65ms interval?
	if (compare_gt(vss.V_store_uV, (ufloat){.value = vs_cfg.V_storage_max_uV, .shift = 0}))
	{
		vss.V_store_uV.value = vs_cfg.V_storage_max_uV;
	}

	/* connect or disconnect output on certain events */
	static uint32_t sample_count = 0;
	static bool_ft is_outputting = false;

	if (++sample_count == vss.interval_check_thrs_sample)
	{
		sample_count = 0;
		if (is_outputting)
		{
			if (compare_lt(vss.V_store_uV, vss.V_out_uV) | compare_lt(vss.V_store_uV, (ufloat){.value = vs_cfg.V_storage_disable_threshold_uV, .shift= 0}))
			{
				is_outputting = false;
			}
		}
		else
		{
			/* fast charge virtual output-cap */
			if (compare_gt(vss.V_store_uV, vss.V_out_uV))
			{
				is_outputting = true;
				vss.V_store_uV = sub(vss.V_store_uV, (ufloat){.value=vs_cfg.dV_stor_low_uV, .shift=0});
			}
			if (compare_gt(vss.V_store_uV, (ufloat){.value = vs_cfg.V_storage_enable_threshold_uV, .shift=0}))
			{
				is_outputting = true;
				vss.V_store_uV = sub(vss.V_store_uV, (ufloat){.value=vs_cfg.dV_stor_en_thrs_uV, .shift=0});
			}
		}
	}

	/* emulate power-good-signal */
	/* TODO: pin is on other PRU
	ufloat V_pwr_good_low_thrs_uV; // range where target is informed by output-pin
	ufloat V_pwr_good_high_thrs_uV;
	*/
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	/* output proper voltage to dac */
	if (is_outputting)	return vss.V_out_dac_raw;
	else 			return 0u;
}


/* bring values into adc domain with -> voltage_uV = adc_value * gain_factor + offset
 * original definition in: https://github.com/geissdoerfer/shepherd/blob/master/docs/user/data_format.rst */

// (previous) unsafe conversion -> n8 can overflow uint32, 50mA are 16 bit as uA, 26 bit as nA, 34 bit as nA_n8-factor
static inline ufloat conv_adc_raw_to_nA(const uint32_t current_raw)
{
	const ufloat current_nA = mul((ufloat){.value=current_raw, .shift=0}, (ufloat){.value=cal_cfg.adc_current_factor_nA_n8, .shift=-8});
	return  sub(current_nA, (ufloat){.value=cal_cfg.adc_current_offset_nA, .shift=0});
}

// safe conversion - 5 V is 13 bit as mV, 23 bit as uV, 31 bit as uV_n8
static inline uint32_t conv_uV_to_dac_raw(const ufloat voltage_uV)
{
	ufloat voltage_raw = sub(voltage_uV, (ufloat){.value=cal_cfg.dac_voltage_offset_uV, .shift=0});
	voltage_raw = mul(voltage_raw, (ufloat){.value=cal_cfg.dac_voltage_inv_factor_uV_n20, .shift=-20}); // TODO: rework both factors
	return extract_value(voltage_raw);
}

static ufloat input_efficiency(const uint32_t voltage_uV, const uint32_t current_nA)
{
	uint8_t pos_v = 32 - get_left_zero_count(voltage_uV>>10);
	uint8_t pos_c = 32 - get_left_zero_count(current_nA>>10);
	if (pos_v >= LUT_SIZE) pos_v = LUT_SIZE - 1;
	if (pos_c >= LUT_SIZE) pos_c = LUT_SIZE - 1;
	/* TODO: could interpolate here between 4 values, if there is space for overhead */
        return (ufloat){.value = vs_cfg.LUT_inp_efficiency_n8[pos_v][pos_c], .shift = -8};
}

// TODO: fix input to take SI-units
static ufloat get_output_efficiency(const uint32_t current)
{
	uint8_t pos_c = 32 - get_left_zero_count(current);
	if (pos_c >= LUT_SIZE) pos_c = LUT_SIZE - 1;
	/* TODO: could interpolate here between 2 values, if there is space for overhead */
	return (ufloat){.value = vs_cfg.LUT_out_inv_efficiency_n10[pos_c], .shift = -10};
}

void set_input_power_pW(const uint32_t P_pW)
{
	vss.P_inp_pW = (ufloat){.value = P_pW, .shift = 0};
}

void set_output_power_pW(const uint32_t P_pW)
{
	vss.P_out_pW = (ufloat){.value = P_pW, .shift = 0};
}

void set_storage_Capacitor_uV(const uint32_t C_uV)
{
	vss.V_store_uV = (ufloat){.value = C_uV, .shift = 0};
}

uint32_t get_input_power_pW(void)
{
	return extract_value(vss.P_inp_pW);
}

uint32_t get_output_power_pW(void)
{
	return extract_value(vss.P_out_pW);
}

uint32_t get_storage_Capacitor_uV(void)
{
	return extract_value(vss.V_store_uV);
}
