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
static inline ufloat conv_adc_raw_to_nA(uint32_t current_raw);

static inline uint32_t conv_uV_to_dac_raw(ufloat voltage_uV);

static ufloat input_efficiency(uint8_t efficiency_lut[const][LUT_SIZE], uint32_t voltage, uint32_t current);
static ufloat output_efficiency(const uint32_t inv_efficiency_lut_n24[const], uint32_t current);

/* data-structure that hold the state - variables for direct use */
struct VirtSource_State {
	/* Boost converter */
	ufloat dt_us_per_C_nF;
	ufloat V_store_uV;
	uint32_t interval_check_thrs_sample;
	/* Buck converter */
	ufloat V_out_uV;
	uint32_t V_out_dac_raw;
};

/* (local) global vars to access in update function */
static struct VirtSource_State vss;
static struct VirtSource_Config* vsc;
static struct Calibration_Config cal_cfg;
#define dt_us_const 	(SAMPLE_INTERVAL_NS / 1000u)

void vsource_init(struct VirtSource_Config *vsc_arg, struct Calibration_Config *cal_arg)
{
	// Initialize state (order in struct) - convert for direct use,
	cal_cfg = *cal_arg;
	vsc = vsc_arg;
	GPIO_OFF(DEBUG_PIN1_MASK);
	/* Boost Reg */

	vss.dt_us_per_C_nF = div0(dt_us_const, 0, vsc_arg->C_storage_nF, 0);
	/* container for the stored energy: */
	vss.V_store_uV = (ufloat){.value = vsc_arg->V_storage_init_uV, .shift = 0};

	/* Output check every n Samples */
	vss.interval_check_thrs_sample = vsc_arg->interval_check_thresholds_ns / SAMPLE_INTERVAL_NS;
	GPIO_ON(DEBUG_PIN1_MASK);

	/* Buck Boost */
	vss.V_out_uV = (ufloat){.value = vsc_arg->V_output_uV, .shift = 0};

	vss.V_out_dac_raw = conv_uV_to_dac_raw(vss.V_out_uV);

	GPIO_OFF(DEBUG_PIN1_MASK);
	/* compensate for (hard to detect) current-surge of real capacitors when converter gets turned on
	 * -> this can be const value, because the converter always turns on with "V_storage_enable_threshold_uV"
	 * TODO: currently neglecting: delay after disabling converter, boost only has simpler formula, second enabling when VCap >= V_out
	 * Math behind this calculation:
	 * Energy-Change in Storage Cap -> 	E_new = E_old - E_output
	 * with Energy of a Cap 	-> 	E_x = C_x * V_x^2 / 2
	 * combine formulas 		-> 	C_store * V_store_new^2 / 2 = C_store * V_store_old^2 / 2 - C_out * V_out^2 / 2
	 * convert formula to V_new 	->	V_store_new^2 = V_store_old^2 - (C_out / C_store) * V_out^2
	 * convert into dV	 	->	dV = V_store_new - V_store_old
	 * in case of V_cap = V_out 	-> 	dV = V_store_old * (sqrt(1 - C_out / C_store) - 1)
	 */
	/*
	// TODO: this can be done in python, even both enable-cases
	const ufloat V_old_sq_uV = mul0(vsc->V_storage_enable_threshold_uV, 0, vsc->V_storage_enable_threshold_uV, 0);
	const ufloat V_out_sq_uV = mul2(vss.V_out_uV, vss.V_out_uV);
	const ufloat cap_ratio   = div0(vsc->C_output_nF, 0, vsc->C_storage_nF, 0);
	const ufloat V_new_sq_uV = sub2(V_old_sq_uV, mul2(cap_ratio, V_out_sq_uV));
	GPIO_ON(DEBUG_PIN1_MASK);
	vss.dV_stor_en_uV = sub1r(vsc->V_storage_enable_threshold_uV, 0, sqrt_rounded(V_new_sq_uV)); // reversed, because new voltage is lower then old
	*/
	// TODO: add tests for valid ranges
}

uint32_t vsource_update(const uint32_t current_adc_raw, const uint32_t input_current_nA,
		       const uint32_t input_voltage_uV)
{
	// TODO: explain design goals and limitations... why does the code looks that way
	/* Math behind this Converter
	 * Individual drains / sources -> 	P_x = I_x * V_x * eta_x  (eta is efficiency)
	 * Power in and out of Converter -> 	P = P_in - P_out
	 * Current in storage cap -> 		I = P / V_cap
	 * voltage change for Cap -> 		dV = I * dt / C
	 * voltage of storage cap -> 		V += dV
	 *
	 */
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	static bool_ft part_switch = true;
	if (part_switch) {
		part_switch = false;
		GPIO_TOGGLE(DEBUG_PIN1_MASK);
		/* BOOST, Calculate current flowing into the storage capacitor */
		const ufloat eta_inp = input_efficiency(vsc->LUT_inp_efficiency_n8, input_voltage_uV, input_current_nA);
		//const uint64_t dP_inp_pW_n8 = input_current_nA * input_voltage_uV * eta_inp_n8;
		ufloat P_inp_pW;
		ufloat V_inp_uV = { .value = 0u, .shift = 0 };
		/* disable boost if input voltage too low for boost to work, TODO: is this also only in 65ms interval? */
		if (input_voltage_uV >= vsc->V_inp_boost_threshold_uV)
			V_inp_uV.value = input_voltage_uV;
		/* limit input voltage when higher then voltage of storage cap, TODO: is this also only in 65ms interval? */
		if (compare_gt(V_inp_uV, vss.V_store_uV))
			V_inp_uV = vss.V_store_uV;

		P_inp_pW = mul1(V_inp_uV, input_current_nA, 0);
		P_inp_pW = mul2(P_inp_pW, eta_inp);

		GPIO_TOGGLE(DEBUG_PIN1_MASK);
		/* BUCK, Calculate current flowing out of the storage capacitor*/
		const ufloat I_out_nA = conv_adc_raw_to_nA(current_adc_raw);
		const ufloat eta_inv_out = output_efficiency(vsc->LUT_out_inv_efficiency_n24, current_adc_raw); // TODO: wrong input, should be nA
		const ufloat dP_leak_pW = mul1(vss.V_store_uV, vsc->I_storage_leak_nA, 0);
		ufloat P_out_pW;
		P_out_pW = mul2(I_out_nA, vss.V_out_uV);
		P_out_pW = mul2(P_out_pW, eta_inv_out);
		P_out_pW = add2(P_out_pW, dP_leak_pW);
		GPIO_TOGGLE(DEBUG_PIN1_MASK);
		return 1;
	}
	ufloat P_inp_pW = {.value = 5, .shift = 0};
	ufloat P_out_pW = {.value = 7, .shift = 3};
	part_switch = true;
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	/* Sum up Power and calculate new Capacitor Voltage
	 * NOTE: slightly more complex code due to uint -> the only downside to ufloat
	 */
	ufloat P_sum_pW; //
	ufloat I_cStor_nA;
	ufloat dV_cStor_uV;
	if (compare_gt(P_inp_pW, P_out_pW))
	{
		P_sum_pW = sub2(P_inp_pW, P_out_pW);
		I_cStor_nA = div2(P_sum_pW, vss.V_store_uV);
		dV_cStor_uV = mul2(I_cStor_nA, vss.dt_us_per_C_nF);
		vss.V_store_uV = add2(vss.V_store_uV, dV_cStor_uV);
	}
	else
	{
		P_sum_pW = sub2(P_out_pW, P_inp_pW);
		I_cStor_nA = div2(P_sum_pW, vss.V_store_uV);
		dV_cStor_uV = mul2(I_cStor_nA, vss.dt_us_per_C_nF);
		vss.V_store_uV = sub2(vss.V_store_uV, dV_cStor_uV);
	}

	// Make sure the voltage stays in it's boundaries, TODO: is this also only in 65ms interval?
	if (compare_gt(vss.V_store_uV, (ufloat){.value = vsc->V_storage_max_uV, .shift = 0}))
	{
		vss.V_store_uV.value = vsc->V_storage_max_uV;
	}

	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	/* connect or disconnect output on certain events */
	static uint32_t sample_count = 0;
	static bool_ft is_outputting = false;

	if (++sample_count == vss.interval_check_thrs_sample)
	{
		sample_count = 0;
		if (is_outputting)
		{
			if (compare_lt(vss.V_store_uV, vss.V_out_uV) | compare_lt(vss.V_store_uV, (ufloat){.value = vsc->V_storage_disable_threshold_uV, .shift= 0}))
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
				vss.V_store_uV = sub2(vss.V_store_uV, (ufloat){.value=vsc->dV_stor_low_uV, .shift=0});
			}
			if (compare_gt(vss.V_store_uV, (ufloat){.value = vsc->V_storage_enable_threshold_uV, .shift=0}))
			{
				is_outputting = true;
				vss.V_store_uV = sub2(vss.V_store_uV, (ufloat){.value=vsc->dV_stor_en_thrs_uV, .shift=0});
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
	ufloat current_nA;
	current_nA = mul0(current_raw, 0u, cal_cfg.adc_current_factor_n8, -8);
	current_nA = sub1(current_nA, cal_cfg.adc_current_offset_nA, 0u);
	return current_nA;
}

// safe conversion - 5 V is 13 bit as mV, 23 bit as uV, 31 bit as uV_n8
static inline uint32_t conv_uV_to_dac_raw(const ufloat voltage_uV)
{
	ufloat voltage_raw;
	voltage_raw = sub1(voltage_uV, cal_cfg.dac_voltage_offset_uV, 0u);
	voltage_raw = mul1(voltage_raw, cal_cfg.dac_voltage_inv_factor_n24, -24);
	return extract_value(voltage_raw);
}

// TODO: fix input to take SI-units
static ufloat input_efficiency(uint8_t efficiency_lut[const][LUT_SIZE], const uint32_t voltage, const uint32_t current)
{
	uint8_t pos_v = 32 - get_left_zero_count(voltage);
	uint8_t pos_c = 32 - get_left_zero_count(current);
	if (pos_v >= LUT_SIZE) pos_v = LUT_SIZE - 1;
	if (pos_c >= LUT_SIZE) pos_c = LUT_SIZE - 1;
	/* TODO: could interpolate here between 4 values, if there is space for overhead */
        return (ufloat){.value = efficiency_lut[pos_v][pos_c], .shift = -8};
}

// TODO: fix input to take SI-units
static ufloat output_efficiency(const uint32_t inv_efficiency_lut_n24[const], const uint32_t current)
{
	uint8_t pos_c = 32 - get_left_zero_count(current);
	if (pos_c >= LUT_SIZE) pos_c = LUT_SIZE - 1;
	/* TODO: could interpolate here between 2 values, if there is space for overhead */
	return (ufloat){.value = inv_efficiency_lut_n24[pos_c], .shift = -24};
}
