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

struct VirtSource_State {
	ufloat dac_voltage_inv_factor_uV;
	/* Direct Reg */
	ufloat C_out_nf;
	/* Boost Reg, ie. BQ25504 */
	ufloat V_inp_theshold_uV; // min input-voltage for the boost converter to work
	ufloat C_stor_nF;
	ufloat V_stor_uV; // allow a proper / fast startup
	ufloat V_stor_max_uV;  // -> boost shuts off
	ufloat I_stor_leak_nA;
	ufloat V_stor_en_thrs_uV;  // -> target gets connected (hysteresis-combo with next value)
	ufloat V_stor_dis_thrs_uV; // -> target gets disconnected
	uint8_t LUT_inp_efficiency_n8[LUT_SIZE][LUT_SIZE]; // depending on inp_voltage, inp_current, (cap voltage)
	// n8 means normalized to 2^8 = 1.0
	ufloat V_pwr_good_low_thrs_uV; // range where target is informed by output-pin
	ufloat V_pwr_good_high_thrs_uV;
	/* Buck Boost, ie. BQ25570) */
	ufloat inv_efficiency_output[LUT_SIZE]; // depending on output_current,
	ufloat V_out_uV;
	uint32_t V_out_dac_raw;
};

uint32_t SquareRootRounded(uint32_t a_nInput);

// Global vars to access in update function
static struct VirtSource_State vs_cfg;
static struct CalibrationSettings cali_cfg;

#define ADC_LOAD_CURRENT_GAIN       (int32_t)(((1U << 17U) - 1) * 2.0 * 50.25 / (0.625 * 4.096))
#define ADC_LOAD_CURRENT_OFFSET     (-(1U << 17U))  // TODO: should be positive
#define ADC_LOAD_VOLTAGE_GAIN       (int32_t)(((1U << 18U) - 1) / (1.25 * 4.096))
#define ADC_LOAD_VOLTAGE_OFFSET     0


void vsource_init(struct VirtSourceSettings *vsource_arg, struct CalibrationSettings *calib_arg)
{
	cali_cfg = *calib_arg;

	// convert new config values for direct use, TODO: adapt names in vsource_arg-struct

	vs_cfg.dac_voltage_inv_factor_uV = div0(1u, 0u, cali_cfg.dac_voltage_factor_uV_n8, -8);
	/* Direct Reg */
	vs_cfg.C_out_nf = mul0(vsource_arg->c_output_capacitance_uf, 0u, 1000u, 0u);
	/* Boost Reg */
	vs_cfg.V_inp_theshold_uV = mul0(vsource_arg->v_harvest_boost_threshold_mV, 0u, 1000u, 0u);
	vs_cfg.C_stor_nF = mul0(vsource_arg->c_storage_capacitance_uf, 0u, 1000u, 0u);
	/* container for the stored energy: */
	vs_cfg.V_stor_uV = mul0(vsource_arg->c_storage_voltage_init_mV, 0u, 1000u, 0u);
	vs_cfg.V_stor_max_uV = mul0(vsource_arg->c_storage_voltage_max_mV, 0u, 1000u, 0u);
	vs_cfg.I_stor_leak_nA = mul0(vsource_arg->c_storage_current_leak_nA, 0u, 1u, 0u);
	vs_cfg.V_stor_en_thrs_uV = mul0(vsource_arg->c_storage_enable_threshold_mV, 0u, 1000u, 0u);
	vs_cfg.V_stor_dis_thrs_uV = mul0(vsource_arg->c_storage_disable_threshold_mV, 0u, 1000u, 0u);
	/* LUT see below */
	vs_cfg.V_pwr_good_low_thrs_uV = mul0(vsource_arg->c_storage_voltage_max_mV, 0u, 1000u, 0u);
	vs_cfg.V_pwr_good_high_thrs_uV = mul0(vsource_arg->c_storage_voltage_max_mV, 0u, 1000u, 0u);
	/* Buck Boost */
	/* LUT see below */
	vs_cfg.V_out_uV = mul0(vsource_arg->c_storage_voltage_max_mV, 0u, 1000u, 0u);
	vs_cfg.V_out_dac_raw = conv_uV_to_dac_raw_n8(vs_cfg.V_out_uV);

	uint8_t LUT_inp_efficiency_n8[LUT_SIZE][LUT_SIZE]; // depending on inp_voltage, inp_current, (cap voltage)
	ufloat inv_efficiency_output[LUT_SIZE];

	/* Calculate how much output cap should be discharged when turning on, based
	* on the storage capacitor and output capacitor size */
	// TODO: seems wrong, even the formular mentioned in thesis, it assumes C_out gets only V_cap...
	// base: C_cap * V_cap_new^2 / 2 = C_cap * V_cap_old^2 / 2 - C_out * V_out^2 / 2
	const int32_t scale =	((vsource_cfg.c_storage_capacitance_uf - vsource_cfg.c_output_capacitance_uf) << 20U) / vsource_cfg.c_storage_capacitance_uf;
	outputcap_scale_factor = SquareRootRounded(scale);

	// Initialize vars
	V_cStor_uV = mul0(vsource_cfg.c_storage_voltage_init_mV, 0u, 1000u, 0u);
	V_cStor_max_uV = mul0(vsource_cfg.c_storage_voltage_max_mV, 0u, 1000u, 0u);
	is_outputting = false;

	// Calculate harvest multiplier
	ufloat Cs_nF = mul0(vsource_cfg.c_storage_capacitance_uf, 0u, 1000u, 0u);
	ufloat dt_us = div0(SAMPLE_INTERVAL_NS, 0u, 1000u, 0u);
	dt_us_per_C_nF = div2(dt_us, Cs_nF);

	// Output check every n Samples
	check_thresholds_sample_count = vsource_arg->interval_check_thresholds_ns / SAMPLE_INTERVAL_NS;

	//avg_cap_voltage = (vsource_cfg.c_storage_voltage_max_mV + vsource_cfg.c_storage_disable_threshold_mV) / 2;
	//output_multiplier = vsource_cfg.dc_output_voltage_mV / (avg_cap_voltage >> SHIFT_VOLT);

	for (uint8_t index = 0; index < LUT_SIZE; index++)
	{
		if (vsource_cfg.LUT_output_efficiency_n8[index] > 0)
		{
			inv_efficiency_output_n8[index] = (255u << 8u) / vsource_cfg.LUT_output_efficiency_n8[index];
		}
		else
		{
			/* 0% is aproximated by biggest inverse value to avoid div0 */
			inv_efficiency_output_n8[index] = (255u << 8u);
		}
	}

	// TODO: inverse efficiency for output, to get rid of division in loop

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
	 */

	/* BOOST, Calculate current flowing into the storage capacitor */
    	const ufloat eta_inp = input_efficiency(vsource_cfg.LUT_inp_efficiency_n8, input_voltage_uV, input_current_nA);
	//const uint64_t dP_inp_pW_n8 = input_current_nA * input_voltage_uV * eta_inp_n8;
	ufloat P_inp_pW;
	P_inp_pW = mul0(input_current_nA, 0, input_voltage_uV, 0);
	P_inp_pW = mul2(P_inp_pW, eta_inp);

	/* BUCK, Calculate current flowing out of the storage capacitor*/
	const ufloat eta_inv_out = output_efficiency(inv_efficiency_output_n8, current_adc_raw); // TODO: wrong input, should be nA
	const uint32_t current_out_nA_n6 = conv_adc_raw_to_nA_n6(current_adc_raw); // TODO: better uFloat
	const ufloat dP_leak_pW = mul1(V_cStor_uV, vsource_cfg.c_storage_current_leak_nA, 0u);
	ufloat P_out_pW;
	P_out_pW = mul0(current_out_nA_n6, -6, output_voltage_uV, 0);
	P_out_pW = mul2(P_out_pW, eta_inv_out);
	P_out_pW = add2(P_out_pW, dP_leak_pW);

	/* Sum up Power and calculate new Capacitor Voltage */
	ufloat P_sum_pW; // TODO: the only downside to ufloat, but sign is only needed here (for now)
	ufloat I_cStor_nA;
	ufloat dV_cStor_uV;
	if (compare_gt(P_inp_pW, P_out_pW))
	{
		P_sum_pW = sub2(P_inp_pW, P_out_pW);
		I_cStor_nA = div2(P_sum_pW, V_cStor_uV);
		dV_cStor_uV = mul2(I_cStor_nA, dt_us_per_C_nF);
		V_cStor_uV = add2(V_cStor_uV, dV_cStor_uV);
	}
	else
	{
		P_sum_pW = sub2(P_out_pW, P_inp_pW);
		I_cStor_nA = div2(P_sum_pW, V_cStor_uV);
		dV_cStor_uV = mul2(I_cStor_nA, dt_us_per_C_nF);
		V_cStor_uV = sub2(V_cStor_uV, dV_cStor_uV);
	}

	// Make sure the voltage does not go beyond it's boundaries
	if (compare_gt(V_cStor_uV, V_cStor_max_uV))	V_cStor_uV = V_cStor_max_uV;

	static uint32_t sample_count = 0;
	if (++sample_count == check_thresholds_sample_count)
	{
		sample_count = 0;

	}

	//else if (new_cap_voltage < vsource_cfg.min_cap_voltage)    new_cap_voltage = vsource_cfg.min_cap_voltage;
	// TODO: test for zero, but this can be done earlier, before adding delta_v

	// TODO: there is another effect of the converter -> every 16 seconds it optimizes power-draw, is it already in the data-stream?

	// determine whether we should be in a new state
	if (is_outputting &&
	    (new_cap_voltage < vsource_cfg.c_storage_disable_threshold_mV)) {
		is_outputting = 0U; // we fall under our threshold
		//virtcap_set_output_state(0U); // TODO: is_outputting and this fn each keep the same state ...
	} else if (!is_outputting &&(new_cap_voltage > vsource_cfg.c_storage_enable_threshold_mV)) {
		is_outputting = 1U; // we have enough voltage to switch on again
		//virtcap_set_output_state(1U);
		new_cap_voltage = (new_cap_voltage >> 10) * outputcap_scale_factor; // TODO: magic numbers ... could be replaced by matching FN, analog to scale-calculation in init()
	}


	// TODO: add second branch (like before) for pwr_good
	cap_voltage_uV = new_cap_voltage;

	const uint32_t output_dac_raw = conv_uV_to_dac_raw_n8(output_voltage_uV) >> 8u;
	return output_dac_raw;
}

uint32_t SquareRootRounded(const uint32_t a_nInput)
{
	uint32_t op = a_nInput;
	uint32_t res = 0U;
	uint32_t one = 1uL << 30U;

	while (one > op) {
		one >>= 2u;
	}

	while (one != 0u) {
		if (op >= res + one) {
			op = op - (res + one);
			res = res + 2U * one;
		}
		res >>= 1U;
		one >>= 2U;
	}

	if (op > res) {
		res++;
	}

	return res;
}


// TODO: bring the following FNs to uflaot
/* bring values into adc domain with -> voltage_uV = adc_value * gain_factor + offset
 * original definition in: https://github.com/geissdoerfer/shepherd/blob/master/docs/user/data_format.rst */
// TODO: n8 can overflow uint32, 50mA are 16 bit as uA, 26 bit as nA, 34 bit as nA_n8-factor
static inline uint32_t conv_adc_raw_to_nA_n6(const uint32_t current_raw)
{
	uint32_t current_nA_n6 = (current_raw * cali_cfg.adc_current_factor_nA_n8) >> 2u;
	int32_t offset_nA_n6 = cali_cfg.adc_current_offset_nA * (1u << 6u);

	if ((int32_t)current_nA_n6 > offset_nA_n6)
	{
		current_nA_n6 -= offset_nA_n6;
	}
	else
		current_nA_n6 = 0;
	return current_nA_n6;
}

// safe conversion - 5 V is 13 bit as mV, 23 bit as uV, 31 bit as uV_n8
static inline uint32_t conv_uV_to_dac_raw_n8(const ufloat voltage_uV)
{
	ufloat voltage_raw;
	voltage_raw = sub1(voltage_uV, cali_cfg.dac_voltage_offset_uV, 0u);
	voltage_raw = mul2(voltage_raw, vs_cfg.dac_voltage_inv_factor_uV);
	return extract_value(voltage_raw);
}

#ifdef __GNUC__
static uint8_t get_left_zero_count(const uint32_t value)
{
	/* TODO: there is a ASM-COMMAND for that, LMBD r2, r1, 1 */
	uint32_t _value = value;
	uint8_t	count = 32;
	for (; _value > 0; _value >>= 1) count--;
	return count;
}
#endif

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

static ufloat output_efficiency(const uint32_t inv_efficiency_lut[const], const uint32_t current)
{
	uint8_t pos_c = 32 - get_left_zero_count(current);
	if (pos_c >= LUT_SIZE) pos_c = LUT_SIZE - 1;
	/* TODO: could interpolate here between 2 values, if there is space for overhead */
	ufloat result = {.value = inv_efficiency_lut[pos_c], .shift = -8};
	return result;
}

bool_ft virtcap_get_output_state()
{
	return VIRTCAP_OUT_PIN_state; // TODO: legacy
}
