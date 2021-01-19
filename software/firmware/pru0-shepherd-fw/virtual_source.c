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

// Output state of virtcap, TODO
static bool_ft VIRTCAP_OUT_PIN_state = 0U;

// Derived constants
static uint32_t harvest_multiplier;
static uint32_t output_multiplier;
static uint32_t outputcap_scale_factor;
static uint32_t avg_cap_voltage;

// Working vars
static uint32_t cap_voltage_uV;
static bool_ft is_outputting;

// new source vars
static uint32_t inv_efficiency_output_n8[LUT_SIZE];
static uint32_t output_voltage_uV;

struct VirtSource_State {
	/* Direct Reg */
	uint32_t c_output_capacitance_uf; // final (always last) stage to catch current spikes of target
	/* Boost Reg, ie. BQ25504 */
	uint32_t v_harvest_boost_threshold_mV; // min input-voltage for the boost converter to work
	uint32_t c_storage_capacitance_uf;
	uint32_t c_storage_voltage_init_mV; // allow a proper / fast startup
	uint32_t c_storage_voltage_max_mV;  // -> boost shuts off
	uint32_t c_storage_current_leak_nA;
	uint32_t c_storage_enable_threshold_mV;  // -> target gets connected (hysteresis-combo with next value)
	uint32_t c_storage_disable_threshold_mV; // -> target gets disconnected
	uint8_t LUT_inp_efficiency_n8[12][12]; // depending on inp_voltage, inp_current, (cap voltage)
	// n8 means normalized to 2^8 = 1.0
	uint32_t pwr_good_low_threshold_mV; // range where target is informed by output-pin
	uint32_t pwr_good_high_threshold_mV;
	/* Buck Boost, ie. BQ25570) */
	uint32_t dc_output_voltage_mV;
	uint8_t LUT_output_efficiency_n8[12]; // depending on output_current, TODO: was inverse
	/* TODO: is there a drop voltage?, can input voltage be higher than cap-voltage, and all power be used? */
} __attribute__((packed));

uint32_t SquareRootRounded(uint32_t a_nInput);


// Global vars to access in update function
static struct VirtSourceSettings vsource_cfg;
static struct CalibrationSettings cali_cfg;

#define ADC_LOAD_CURRENT_GAIN       (int32_t)(((1U << 17U) - 1) * 2.0 * 50.25 / (0.625 * 4.096))
#define ADC_LOAD_CURRENT_OFFSET     (-(1U << 17U))  // TODO: should be positive
#define ADC_LOAD_VOLTAGE_GAIN       (int32_t)(((1U << 18U) - 1) / (1.25 * 4.096))
#define ADC_LOAD_VOLTAGE_OFFSET     0


void vsource_init(struct VirtSourceSettings *vsource_arg, struct CalibrationSettings *calib_arg)
{
	vsource_cfg = *vsource_arg; // copies content of whole struct
	cali_cfg = *calib_arg;

	/*
	calib_arg->adc_current_factor_nA_n8 = ADC_LOAD_CURRENT_GAIN; // TODO: why overwriting values provided by system?
	calib_arg->adc_current_offset_nA = ADC_LOAD_CURRENT_OFFSET;
	calib_arg->adc_voltage_factor_mV_n8 = ADC_LOAD_VOLTAGE_GAIN;
	calib_arg->adc_voltage_offset_uV = ADC_LOAD_VOLTAGE_OFFSET;
	*/

	// convert voltages and currents to logic values

	vsource_cfg.c_storage_enable_threshold_mV = conv_uV_to_adc_raw_n8(vsource_arg->c_storage_enable_threshold_mV);
	vsource_cfg.c_storage_disable_threshold_mV = conv_uV_to_adc_raw_n8(vsource_arg->c_storage_disable_threshold_mV);
	vsource_cfg.c_storage_voltage_max_mV = conv_uV_to_adc_raw_n8(vsource_arg->c_storage_voltage_max_mV);
	vsource_cfg.c_storage_voltage_init_mV = conv_uV_to_adc_raw_n8(vsource_arg->c_storage_voltage_init_mV);
	vsource_cfg.dc_output_voltage_mV = conv_uV_to_adc_raw_n8(vsource_arg->dc_output_voltage_mV);
	vsource_cfg.c_storage_current_leak_nA = conv_nA_to_adc_raw_n8(vsource_arg->c_storage_current_leak_nA);

	/* Calculate how much output cap should be discharged when turning on, based
	* on the storage capacitor and output capacitor size */
	// TODO: seems wrong, even the formular mentioned in thesis, it assumes C_out gets only V_cap...
	// base: C_cap * V_cap_new^2 / 2 = C_cap * V_cap_old^2 / 2 - C_out * V_out^2 / 2
	const int32_t scale =	((vsource_cfg.c_storage_capacitance_uf - vsource_cfg.c_output_capacitance_uf) << 20U) / vsource_cfg.c_storage_capacitance_uf;
	outputcap_scale_factor = SquareRootRounded(scale);

	// Initialize vars
	cap_voltage_uV = vsource_cfg.c_storage_voltage_init_mV;
	is_outputting = false;

	// Calculate harvest multiplier
	harvest_multiplier = (SAMPLE_INTERVAL_NS) /
			     (cali_cfg.adc_current_factor_nA_n8 / cali_cfg.adc_voltage_factor_mV_n8 * vsource_cfg.c_storage_capacitance_uf);

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

	/* BOOST, Calculate current flowing into the storage capacitor */
    	const ufloat eta_inp = input_efficiency(vsource_cfg.LUT_inp_efficiency_n8, input_voltage_uV, input_current_nA);
	//const uint64_t dP_inp_pW_n8 = input_current_nA * input_voltage_uV * eta_inp_n8;
	ufloat dP_inp_pW;
	dP_inp_pW = mul0(input_current_nA, 0, input_voltage_uV, 0);
	dP_inp_pW = mul2(dP_inp_pW, eta_inp);

	/* BUCK, Calculate current flowing out of the storage capacitor*/
	const ufloat eta_inv_out = output_efficiency(inv_efficiency_output_n8, current_adc_raw);
	const uint32_t current_out_nA_n6 = conv_adc_raw_to_nA_n6(current_adc_raw);
	const ufloat dP_leak_pW = mul0(vsource_cfg.c_storage_current_leak_nA, 0, cap_voltage_uV, 0);
	ufloat dP_out_pW;
	dP_out_pW = mul0(current_out_nA_n6, -6, output_voltage_uV, 0);
	dP_out_pW = mul2(dP_out_pW, eta_inv_out);
	dP_out_pW = add2(dP_out_pW, dP_leak_pW);

	ufloat dP_sum_pW; // TODO: the only downside to ufloat
	if (compare_gt(dP_inp_pW, dP_out_pW))
	{
		dP_sum_pW = sub2(dP_inp_pW, dP_out_pW);
	}
	else
	{
		dP_sum_pW = sub2(dP_out_pW, dP_inp_pW);
	}


	uint32_t dI_out = (current_adc_raw * output_multiplier) >> SHIFT_VOLT; // TODO: crude simplification here, brings error of +-5%
	dI_out += vsource_cfg.c_storage_current_leak_nA;

	/* Calculate delta V*/
	const int32_t delta_i = cin - cout;
	const int32_t delta_v = (delta_i * harvest_multiplier) >> SHIFT_VOLT; // TODO: looks wrong, harvest mult is specific for V*A ADC-Gains, but for OUT we have no Volt, and for leakage neither
	uint32_t new_cap_voltage = cap_voltage_uV + delta_v; // TODO: var can already be the original cap_voltage_uV

	// Make sure the voltage does not go beyond it's boundaries
	if (new_cap_voltage > vsource_cfg.c_storage_voltage_max_mV)         new_cap_voltage = vsource_cfg.c_storage_voltage_max_mV;
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
static inline uint32_t conv_uV_to_adc_raw_n8(const uint32_t voltage_uV)
{
	uint32_t voltage_raw_n8 = 0;
	if ((int32_t)voltage_uV > cali_cfg.adc_voltage_offset_uV)
	{
		voltage_raw_n8 = voltage_uV - cali_cfg.adc_voltage_offset_uV;
	}
	voltage_raw_n8 *= cali_cfg.adc_voltage_ifactor_uV_n8;
	return voltage_raw_n8;
}

// safe conversion - 50mA are 16 bit as uA, 26 bit as nA // raw is 18 bit, raw_n8 is 26 bit
// TODO: adc_current_ifactor_nA_n8 is near 1 ... not optimal
static inline uint32_t conv_nA_to_adc_raw_n8(const uint32_t current_nA)
{
	uint32_t current_raw_n8 = 0;
	if ((int32_t)current_nA > cali_cfg.adc_current_offset_nA)
	{
		current_raw_n8 = current_nA - cali_cfg.adc_current_offset_nA;
	}
	current_raw_n8 *= cali_cfg.adc_current_ifactor_nA_n8;
	return current_raw_n8;
}

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
static inline uint32_t conv_uV_to_dac_raw_n8(const uint32_t voltage_uV)
{
	uint32_t voltage_raw_n8 = 0;
	if ((int32_t)voltage_uV > cali_cfg.dac_voltage_offset_uV)
	{
		voltage_raw_n8 = voltage_uV - cali_cfg.dac_voltage_offset_uV;
	}
	voltage_raw_n8 *= cali_cfg.dac_voltage_ifactor_mV_n8;
	return voltage_raw_n8;
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
