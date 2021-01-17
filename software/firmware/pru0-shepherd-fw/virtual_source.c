#include <stdint.h>
#include <stdio.h>
#include "commons.h"
#include "shepherd_config.h"
#include "gpio.h"
#include "hw_config.h"
#include "stdint_fast.h"
#include "virtual_source.h"
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

#define SHIFT_VOLT		(12U)
#define EFFICIENCY_RANGE	(1U << 12U)

#define SHIFT_LUT		(26U)


// Output state of virtcap, TODO
static bool_ft VIRTCAP_OUT_PIN_state = 0U;

// Derived constants
static int32_t harvest_multiplier;
static int32_t output_multiplier;
static int32_t outputcap_scale_factor;
static int32_t avg_cap_voltage;

// Working vars
static uint32_t cap_voltage;
static bool_ft is_outputting;

uint32_t SquareRootRounded(uint32_t a_nInput);
static uint8_t get_msb_position(uint32_t value);

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
	calib_arg->adc_load_current_gain = ADC_LOAD_CURRENT_GAIN; // TODO: why overwriting values provided by system?
	calib_arg->adc_load_current_offset = ADC_LOAD_CURRENT_OFFSET;
	calib_arg->adc_load_voltage_gain = ADC_LOAD_VOLTAGE_GAIN;
	calib_arg->adc_load_voltage_offset = ADC_LOAD_VOLTAGE_OFFSET;
	*/

	// convert voltages and currents to logic values

	vsource_cfg.c_storage_enable_threshold_mV =	voltage_mv_to_logic(vsource_arg->c_storage_enable_threshold_mV);
	vsource_cfg.c_storage_disable_threshold_mV =	voltage_mv_to_logic(vsource_arg->c_storage_disable_threshold_mV);
	vsource_cfg.c_storage_voltage_max_mV = voltage_mv_to_logic(vsource_arg->c_storage_voltage_max_mV);
	vsource_cfg.c_storage_voltage_init_mV = voltage_mv_to_logic(vsource_arg->c_storage_voltage_init_mV);
	vsource_cfg.dc_output_voltage_mV = voltage_mv_to_logic(vsource_arg->dc_output_voltage_mV);
	vsource_cfg.c_storage_current_leak_nA = current_ua_to_logic(vsource_arg->c_storage_current_leak_nA);

	/* Calculate how much output cap should be discharged when turning on, based
	* on the storage capacitor and output capacitor size */
	// TODO: seems wrong, even the formular mentioned in thesis, it assumes C_out gets only V_cap...
	// base: C_cap * V_cap_new^2 / 2 = C_cap * V_cap_old^2 / 2 - C_out * V_out^2 / 2
	const int32_t scale =	((vsource_cfg.c_storage_capacitance_uf - vsource_cfg.c_output_capacitance_uf) << 20U) / vsource_cfg.c_storage_capacitance_uf;
	outputcap_scale_factor = SquareRootRounded(scale);

	// Initialize vars
	cap_voltage = vsource_cfg.c_storage_voltage_init_mV;
	is_outputting = false;

	// Calculate harvest multiplier
	harvest_multiplier = (SAMPLE_INTERVAL_NS << (SHIFT_VOLT + SHIFT_VOLT)) /
			     (cali_cfg.adc_load_current_gain / cali_cfg.adc_load_voltage_gain * vsource_cfg.c_storage_capacitance_uf);

	avg_cap_voltage = (vsource_cfg.c_storage_voltage_max_mV + vsource_cfg.c_storage_disable_threshold_mV) / 2;
	output_multiplier = vsource_cfg.dc_output_voltage_mV / (avg_cap_voltage >> SHIFT_VOLT);

	// TODO: add tests for valid ranges
}

uint32_t vsource_update(const uint32_t current_measured, const uint32_t input_current,
		       const uint32_t input_voltage)
{
	// TODO: explain design goals and limitations... why does the code looks that way

	/* input meta */
	const uint8_t size_iv = get_msb_position(input_voltage);
	const uint8_t size_ic = get_msb_position(input_current);
	const uint8_t size_oc = get_msb_position(current_measured);
	/* TODO: build into pseudo float system */

	/* BOOST */
    	const uint32_t inp_efficiency_n8 = input_efficiency(vsource_cfg.LUT_inp_efficiency_n8, input_voltage, input_current);
	const uint32_t inp_power = input_current * input_voltage; // TODO: data could already be preprocessed by system fpu

	// TODO: whole model should be transformed to unsigned, values don't change sign (except sum of dV_cap), we get more resolution, cleaner bit-shifts and safer array access
	/* Calculate current (cin) flowing into the storage capacitor */
	const int32_t input_power = input_current * input_voltage; // TODO: data could already be preprocessed by system fpu
	int32_t cin = input_power / (cap_voltage >> SHIFT_VOLT); // TODO: cin, cout are dI_in, dI_out
	cin *= input_efficiency;
	cin = cin >> SHIFT_VOLT;

	/* Calculate current (cout) flowing out of the storage capacitor*/
	//if (!is_outputting) current_measured = 0;

	int32_t cout = (current_measured * output_multiplier) >> SHIFT_VOLT; // TODO: crude simplification here, brings error of +-5%
	cout *= output_efficiency; // TODO: efficiency should be divided for the output, LUT seems to do that, but name confuses
	cout = cout >> SHIFT_VOLT; // TODO: shift should be some kind of DIV4096() or the real thing, it will get optimized (probably)
	cout += vsource_cfg.c_storage_current_leak_nA; // TODO: ESR could also be considered

	/* Calculate delta V*/
	const int32_t delta_i = cin - cout;
	const int32_t delta_v = (delta_i * harvest_multiplier) >> SHIFT_VOLT; // TODO: looks wrong, harvest mult is specific for V*A ADC-Gains, but for OUT we have no Volt, and for leakage neither
	uint32_t new_cap_voltage = cap_voltage + delta_v; // TODO: var can already be the original cap_voltage

	// Make sure the voltage does not go beyond it's boundaries
	if (new_cap_voltage > vsource_cfg.c_storage_voltage_max_mV)         new_cap_voltage = vsource_cfg.c_storage_voltage_max_mV;
	//else if (new_cap_voltage < vsource_cfg.min_cap_voltage)    new_cap_voltage = vsource_cfg.min_cap_voltage;
	// TODO: test for zero, but this can be done earlier, before adding delta_v

	// TODO: there is another effect of the converter -> every 16 seconds it optimizes power-draw, is it already in the data-stream?

	const uint32_t out_efficiency_n8 = output_efficiency(vsource_cfg.LUT_output_efficiency_n8, current_measured);


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

	cap_voltage = new_cap_voltage;
	return cap_voltage;
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

static inline uint32_t voltage_mv_to_logic(const uint32_t voltage)
{
	/* Compensate for adc gain and offset, division for mv is split to optimize accuracy */
	uint32_t logic_voltage = voltage * (cali_cfg.adc_load_voltage_gain / 100) / 10;
	logic_voltage += cali_cfg.adc_load_voltage_offset;
	return logic_voltage << SHIFT_VOLT;
}

static inline uint32_t current_ua_to_logic(const uint32_t current)
{
	/* Compensate for adc gain and offset, division for ua is split to optimize accuracy */
	uint32_t logic_current = current * (cali_cfg.adc_load_current_gain / 1000) / 1000;
	/* Add 2^17 because current is defined around zero, not 2^17 */
	logic_current += cali_cfg.adc_load_current_offset + (1U << 17U); // TODO: why first remove 1<<17 and then add it again?
	return logic_current;
}


static uint8_t get_msb_position(const uint32_t value)
{
	uint32_t _value = value;
	uint8_t	position = 0;
	for (; _value > 0; _value >>= 1) position++;
	return position;
}


static uint8_ft input_efficiency(uint8_t efficiency_lut[const][LUT_SIZE], const uint32_t voltage, const uint32_t current)
{
	uint8_t pos_v = get_msb_position(voltage);
	uint8_t pos_c = get_msb_position(current);
	if (pos_v >= LUT_SIZE) pos_v = LUT_SIZE - 1;
	if (pos_c >= LUT_SIZE) pos_c = LUT_SIZE - 1;
	/* TODO: could interpolate here between 4 values, if there is space for overhead */
        return efficiency_lut[pos_v][pos_c];
}

static uint8_ft output_efficiency(uint8_t efficiency_lut[const], const uint32_t current)
{
	uint8_t pos_c = get_msb_position_for_lut(current);
	if (pos_c >= LUT_SIZE) pos_c = LUT_SIZE - 1;
	/* TODO: could interpolate here between 2 values, if there is space for overhead */
	return efficiency_lut[pos_c];
}

bool_ft virtcap_get_output_state()
{
	return VIRTCAP_OUT_PIN_state; // TODO: legacy
}
