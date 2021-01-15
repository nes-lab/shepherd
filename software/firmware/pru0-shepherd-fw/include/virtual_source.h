#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "commons.h"

#define SHIFT_VOLT          12U
#define EFFICIENCY_RANGE    (1U << 12U)

void vsource_init(struct virtSourceSettings *vsource_arg, struct CalibrationSettings *calib_arg);
uint32_t vsource_update(const uint32_t current_measured, const uint32_t input_current, const uint32_t input_voltage);

bool_ft get_output_state();

static inline int32_t voltage_mv_to_logic(int32_t voltage);
static inline int32_t current_ua_to_logic(int32_t current);
//int32_t current_ma_to_logic(int32_t current);

static int32_t lookup(int32_t table[const][9], int32_t current);
static void lookup_init();

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
 * - the real boost converter will be handled in pyPackage and work with IV-Curves
 */

/* Buck-Boost-Converter
 * - boost stage from before, but output is regulated (i.e. BQ25570)
 * - buck-converter has output_voltage and efficiency-LUT (depending on output-current)
 */

/* Solar - Diode - Target
 * -> currently not possible to emulate
 * - needs IV-curves and feedback to
 */

/*
TODO: normally there is a lower threshold for the input where the boost can't work -> in our case 130mV
TODO: not only depending on inp_current -> inp_voltage, (cap_voltage) 10x10x10, x1 byte, or 2 byte

VCap-Variables not needed:
	sample_period_us // should be linked to default sample time
	discretize // only update output every 'discretize' time

TODO: PGOOD / BAT-OK threshold -> extra pin, zwei thresholds,
 */
