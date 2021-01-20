#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "commons.h"
#include "float_pseudo.h"

void vsource_init(struct VirtSourceSettings *vsource_arg, struct CalibrationSettings *calib_arg);
uint32_t vsource_update(uint32_t current_adc_raw, uint32_t input_current_nA, uint32_t input_voltage_uV);

bool_ft get_output_state();

static inline uint32_t conv_adc_raw_to_nA_n6(uint32_t current_raw);

static inline uint32_t conv_uV_to_dac_raw_n8(ufloat voltage_uV);

static ufloat input_efficiency(uint8_t efficiency_lut[const][LUT_SIZE], uint32_t voltage, uint32_t current);
static ufloat output_efficiency(const uint32_t efficiency_lut[const], uint32_t current);


// TODO: get sampletime from main or config

/* Direct Connection
 * - Voltage-value in buffer is written to DAC
 * - (optional) current-value in buffer is used as a limiter (power to target shuts down if it is drawing to much)
 * - (optional) output-capacitor (C != 0) is catching current-spikes of target
 * - this regulator is currently the closest possible simulation of solar -> diode -> target (with voltage-value set to threshold of target)
 * - further usage: on/off-patterns
 */

/* Boost Converter
 * - boost converter with storage_cap and output_cap on output (i.e. BQ25504)
 * - storage-capacitor has capacitance, init-voltage, current-leakage
 * - converter has min input threshold voltage, max capacitor voltage (shutoff), efficiency-LUT (depending on input current & voltage)
 * - capacitor-guard has enable and disable threshold voltage (hysteresis) to detach target
 * - target / output disconnect check is only every 65 ms
 * - TODO: to disable set c_storage_voltage_max_mV to 0
 * - input voltage can not be higher than cap_voltage and will be limited by algo
 * - the power point setting will be handled in pyPackage and work with IV-Curves
 */

/* Buck-Boost-Converter
 * - uses boost stage from before, but output is regulated (i.e. BQ25570)
 * - buck-converter has output_voltage and efficiency-LUT (depending on output-current)
 * - it will disconnect output when disable threshold voltage is reached or v_storage < v_out
 * - to disable set output_voltage to 0
 */

/* Solar - Diode - Target
 * -> currently not possible to emulate
 * - needs IV-curves and feedback to
 */

/*
TODO: normally there is a lower threshold for the input where the boost can't work -> in our case 130mV
TODO: not only depending on inp_current -> inp_voltage, (cap_voltage_uV) 10x10x10, x1 byte, or 2 byte

VCap-Variables not needed:
	sample_period_us // should be linked to default sample time
	discretize // only update output every 'discretize' time

TODO: PGOOD / BAT-OK threshold -> extra pin, two thresholds, other PRU
 */
