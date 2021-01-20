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
static ufloat output_efficiency(const ufloat efficiency_lut[const], uint32_t current);

/* data-structure that hold the state - variables for direct use */
struct VirtSource_State {
	ufloat dac_voltage_inv_factor_uV;
	/* Direct Reg */
	ufloat C_out_nf;
	ufloat dV_stor_en_uV;
	/* Boost Reg */
	ufloat V_inp_boost_thrs_uV; // min input-voltage for the boost converter to work
	ufloat C_store_nF;
	ufloat dt_us_per_C_nF;
	ufloat V_store_uV;
	ufloat V_store_max_uV;  // -> boost shuts off
	ufloat I_store_leak_nA;
	ufloat V_store_en_thrs_uV;  // -> target gets connected (hysteresis-combo with next value)
	ufloat V_store_dis_thrs_uV; // -> target gets disconnected
	uint32_t interval_check_thrs_sample;
	uint8_t LUT_inp_efficiency_n8[LUT_SIZE][LUT_SIZE]; // depending on inp_voltage, inp_current, (cap voltage)
	// n8 means normalized to 2^8 = 1.0
	ufloat V_pwr_good_low_thrs_uV; // range where target is informed by output-pin
	ufloat V_pwr_good_high_thrs_uV;
	/* Buck Boost, ie. BQ25570) */
	ufloat LUT_out_inv_efficiency[LUT_SIZE]; // depending on output_current,
	ufloat V_out_uV;
	uint32_t V_out_dac_raw;
};

/* (local) global vars to access in update function */
static struct VirtSource_State vss;
static struct CalibrationSettings cali_cfg;

void vsource_init(struct VirtSourceSettings *vss_arg, struct CalibrationSettings *calib_arg)
{
	cali_cfg = *calib_arg;

	// Initialize state (order in struct) - convert for direct use, TODO: adapt names in vss_arg-struct
	const ufloat dt_us = div0(SAMPLE_INTERVAL_NS, 0u, 1000u, 0u);

	vss.dac_voltage_inv_factor_uV = div0(1u, 0u, cali_cfg.dac_voltage_factor_uV_n8, -8);

	/* Direct Reg */
	vss.C_out_nf = mul0(vss_arg->C_output_uf, 0u, 1000u, 0u);

	/* Boost Reg */
	vss.V_inp_boost_thrs_uV = mul0(vss_arg->V_inp_boost_threshold_mV, 0u, 1000u, 0u);

	vss.C_store_nF = mul0(vss_arg->C_storage_uf, 0u, 1000u, 0u);

	vss.dt_us_per_C_nF = div2(dt_us, vss.C_store_nF);

	/* container for the stored energy: */
	vss.V_store_uV = mul0(vss_arg->V_storage_init_mV, 0u, 1000u, 0u);

	vss.V_store_max_uV = mul0(vss_arg->V_storage_max_mV, 0u, 1000u, 0u);

	vss.I_store_leak_nA = mul0(vss_arg->I_storage_leak_nA, 0u, 1u, 0u);

	vss.V_store_en_thrs_uV = mul0(vss_arg->V_storage_enable_threshold_mV, 0u, 1000u, 0u);
	vss.V_store_dis_thrs_uV = mul0(vss_arg->V_storage_disable_threshold_mV, 0u, 1000u, 0u);
	/* LUT see below */

	// Output check every n Samples
	vss.interval_check_thrs_sample = vss_arg->interval_check_thresholds_ns / SAMPLE_INTERVAL_NS;

	vss.V_pwr_good_low_thrs_uV = mul0(vss_arg->V_pwr_good_high_threshold_mV, 0u, 1000u, 0u);
	vss.V_pwr_good_high_thrs_uV = mul0(vss_arg->V_pwr_good_low_threshold_mV, 0u, 1000u, 0u);

	/* Buck Boost */
	/* LUT see below */
	vss.V_out_uV = mul0(vss_arg->V_output_mV, 0u, 1000u, 0u);
	vss.V_out_dac_raw = conv_uV_to_dac_raw(vss.V_out_uV);

	/* LUTs */
	for (uint8_t index1 = 0; index1 < LUT_SIZE; index1++)
	{
		vss.LUT_out_inv_efficiency[index1] = div0(1u, 0, (uint32_t)(vss_arg->LUT_output_efficiency_n8[index1]), -8);

		for (uint8_t index2 = 0; index2 < LUT_SIZE; index2++)
		{
			vss.LUT_inp_efficiency_n8[index1][index2] = vss_arg->LUT_inp_efficiency_n8[index1][index2];
		}
	}

	/* compensate for (hard to detect) current-surge of real capacitors when converter gets turned on
	 * -> this can be const value, because the converter always turns on with "V_storage_enable_threshold_mV"
	 * TODO: currently neglecting: delay after disabling converter, boost only has simpler formula, second enabling when VCap >= V_out
	 * Math behind this calculation:
	 * Energy-Change in Storage Cap -> 	E_new = E_old - E_output
	 * with Energy of a Cap 	-> 	E_x = C_x * V_x^2 / 2
	 * combine formulas 		-> 	C_cap * V_cap_new^2 / 2 = C_cap * V_cap_old^2 / 2 - C_out * V_out^2 / 2
	 * convert formula to V_new 	->	V_cap_new^2 = V_cap_old^2 - (C_out / C_cap) * V_out^2
	 * convert into dV	 	->	dV = V_cap_new - V_cap_old
	 */
	const ufloat V_old_uV = vss.V_store_en_thrs_uV;
	const ufloat V_out_uV = vss.V_out_uV;
	const ufloat V_old_sq_uV = mul2(V_old_uV, V_old_uV);
	const ufloat V_out_sq_uV = mul2(V_out_uV, V_out_uV);
	const ufloat cap_ratio   = div2(vss.C_out_nf, vss.C_store_nF);
	const ufloat V_new_sq_uV = sub2(V_old_sq_uV, mul2(cap_ratio, V_out_sq_uV));
	vss.dV_stor_en_uV = sub2(V_old_uV, sqrt_rounded(V_new_sq_uV)); // reversed, because new voltage is lower then old

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

	/* BOOST, Calculate current flowing into the storage capacitor */
    	const ufloat eta_inp = input_efficiency(vss.LUT_inp_efficiency_n8, input_voltage_uV, input_current_nA);
	//const uint64_t dP_inp_pW_n8 = input_current_nA * input_voltage_uV * eta_inp_n8;
	ufloat P_inp_pW;
	ufloat V_inp_uV = {.value = input_voltage_uV, .shift = 0};
	/* limit input voltage when higher then voltage of storage cap, TODO: is this also only in 65ms interval? */
	if (compare_gt(V_inp_uV, vss.V_store_uV))  V_inp_uV = vss.V_store_uV;
	/* disable boost if input voltage too low for boost to work, TODO: is this also only in 65ms interval? */
	if (compare_lt(V_inp_uV, vss.V_inp_boost_thrs_uV)) V_inp_uV.value = 0;
	P_inp_pW = mul1(V_inp_uV, input_current_nA, 0);
	P_inp_pW = mul2(P_inp_pW, eta_inp);

	/* BUCK, Calculate current flowing out of the storage capacitor*/
	const ufloat I_out_nA = conv_adc_raw_to_nA(current_adc_raw);
	const ufloat eta_inv_out = output_efficiency(vss.LUT_out_inv_efficiency, current_adc_raw); // TODO: wrong input, should be nA
	const ufloat dP_leak_pW = mul2(vss.I_store_leak_nA, vss.V_store_uV);
	ufloat P_out_pW;
	P_out_pW = mul2(I_out_nA, vss.V_out_uV);
	P_out_pW = mul2(P_out_pW, eta_inv_out);
	P_out_pW = add2(P_out_pW, dP_leak_pW);

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
	if (compare_gt(vss.V_store_uV, vss.V_store_max_uV))
	{
		vss.V_store_uV = vss.V_store_max_uV;
	}

	/* connect or disconnect output on certain events */
	static uint32_t sample_count = 0;
	static bool_ft is_outputting = false;

	if (++sample_count == vss.interval_check_thrs_sample)
	{
		sample_count = 0;
		if (is_outputting)
		{
			if (compare_lt(vss.V_store_uV, vss.V_out_uV) | compare_lt(vss.V_store_uV, vss.V_store_dis_thrs_uV))
			{
				is_outputting = false;
			}
		}
		else
		{
			if (compare_gt(vss.V_store_uV, vss.V_out_uV) | compare_gt(vss.V_store_uV, vss.V_store_en_thrs_uV))
			{
				is_outputting = true;
				/* fast charge virtual output-cap */
				vss.V_store_uV = sub2(vss.V_store_uV, vss.dV_stor_en_uV);
			}
		}
	}

	/* emulate power-good-signal */
	/* TODO: pin is on other PRU
	ufloat V_pwr_good_low_thrs_uV; // range where target is informed by output-pin
	ufloat V_pwr_good_high_thrs_uV;
	*/

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
	current_nA = mul0(current_raw, 0u, cali_cfg.adc_current_factor_nA_n8, -8);
	current_nA = sub1(current_nA, cali_cfg.adc_current_offset_nA, 0u);
	return current_nA;
}

// safe conversion - 5 V is 13 bit as mV, 23 bit as uV, 31 bit as uV_n8
static inline uint32_t conv_uV_to_dac_raw(const ufloat voltage_uV)
{
	ufloat voltage_raw;
	voltage_raw = sub1(voltage_uV, cali_cfg.dac_voltage_offset_uV, 0u);
	voltage_raw = mul2(voltage_raw, vss.dac_voltage_inv_factor_uV);
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
	ufloat result = {.value = efficiency_lut[pos_v][pos_c], .shift = -8};
        return result;
}

// TODO: fix input to take SI-units
static ufloat output_efficiency(const ufloat inv_efficiency_lut[const], const uint32_t current)
{
	uint8_t pos_c = 32 - get_left_zero_count(current);
	if (pos_c >= LUT_SIZE) pos_c = LUT_SIZE - 1;
	/* TODO: could interpolate here between 2 values, if there is space for overhead */
	return inv_efficiency_lut[pos_c];
}
