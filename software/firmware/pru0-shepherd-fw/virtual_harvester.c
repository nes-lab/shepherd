#include <stdint.h>
#include "hw_config.h"
#include "spi_transfer_pru.h"
#include "virtual_harvester.h"
#include "math64_safe.h"

static const volatile struct HarvesterConfig *cfg;
static const volatile struct CalibrationConfig *cal;

void harvester_struct_init(volatile struct HarvesterConfig *const config)
{
	/* why? this init is nonsense, but testable for byteorder and proper values */
	uint32_t ivalue = 200u;
	config->algorithm = 0u;
	config->window_size = ivalue++;
	config->voltage_uV = ivalue++;
	config->voltage_min_uV = ivalue++;
	config->voltage_max_uV = ivalue++;
	config->current_nA = ivalue++;
	config->setpoint_n8 = ivalue++;
	config->interval_n = ivalue++;
	config->duration_n = ivalue++;
	config->dac_resolution_bit = ivalue++;
	config->wait_cycles_n = ivalue++;
}

void harvester_initialize(const volatile struct HarvesterConfig *const config, const volatile struct CalibrationConfig *const calibration)
{
	cfg = config;
	cal = calibration;

}


void harvest()
{
	// TODO: guide in sub-harvester here, based on algo-value

}

void harvest_adc_cv(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
	static uint32_t voltage_set_uV = 1u << 30u;

	/* NOTE: ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	__delay_cycles(800 / 5);
	const uint32_t current_adc = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	const uint32_t voltage_adc = adc_fastread(SPI_CS_HRV_V_ADC_PIN);
	// TODO: could be self-adjusting if needed
	if (voltage_set_uV != cfg->voltage_uV)
	{
		voltage_set_uV = cfg->voltage_uV;
		const uint32_t voltage_raw = conv_uV_to_dac_raw(voltage_set_uV);
		dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | voltage_raw);
	}
	buffer->values_current[sample_idx] = current_adc;
	buffer->values_voltage[sample_idx] = voltage_adc;
}

void harvest_adc_ivcurve(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
	static uint32_t voltage_set_uV = 1u << 30u;
	static uint32_t waits_n = 0;
	static uint32_t steps_n = 1u << 30u;

	/* NOTE: ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	__delay_cycles(800 / 5);
	const uint32_t current_adc = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	const uint32_t voltage_adc = adc_fastread(SPI_CS_HRV_V_ADC_PIN);

	if (waits_n == 0)
	{
		if (steps_n >= cfg->window_size)
		{
			voltage_set_uV = cfg->voltage_min_uV;
			steps_n = 0;
		}
		else
		{
			voltage_set_uV += cfg->voltage_step_uV;
			steps_n++;
		}
		const uint32_t voltage_raw = conv_uV_to_dac_raw(voltage_set_uV);
		dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | voltage_raw);
		waits_n = cfg->wait_cycles_n;
	}
	else waits_n--;

	buffer->values_current[sample_idx] = current_adc;
	buffer->values_voltage[sample_idx] = voltage_adc;
}

/* bring values into adc domain with -> voltage_uV = adc_value * gain_factor + offset
 * original definition in: https://github.com/geissdoerfer/shepherd/blob/master/docs/user/data_format.rst */
// Note: n8 can overflow uint32, 50mA are 16 bit as uA, 26 bit as nA, 34 bit as nA_n8-factor
// TODO: negative residue compensation, new undocumented feature to compensate for noise around 0 - current uint-design cuts away negative part and leads to biased mean()
#define NOISE_ESTIMATE_nA   (2000u)
#define RESIDUE_SIZE_FACTOR (30u)
#define RESIDUE_MAX_nA      (NOISE_ESTIMATE_nA * RESIDUE_SIZE_FACTOR)
inline uint32_t conv_adc_raw_to_nA(const uint32_t current_raw)
{
	static uint32_t negative_residue_nA = 0;
	const uint32_t I_nA = (uint32_t)(((uint64_t)current_raw * (uint64_t)cal->adc_current_factor_nA_n8) >> 8u);
	// avoid mixing signed and unsigned OPs
	if (cal->adc_current_offset_nA >= 0)
	{
		const uint32_t adc_offset_nA = cal->adc_current_offset_nA;
		return add64(I_nA, adc_offset_nA);
	}
	else
	{
		const uint32_t adc_offset_nA = -cal->adc_current_offset_nA + negative_residue_nA;

		if (I_nA > adc_offset_nA)
		{
			return (I_nA - adc_offset_nA);
		}
		else
		{
			negative_residue_nA = adc_offset_nA - I_nA;
			if (negative_residue_nA > RESIDUE_MAX_nA) negative_residue_nA = RESIDUE_MAX_nA;
			return 0u;
		}
	}
}

// safe conversion - 5 V is 13 bit as mV, 23 bit as uV, 31 bit as uV_n8
// TODO: copy from virtual converter
inline uint32_t conv_uV_to_dac_raw(const uint32_t voltage_uV)
{
	uint32_t dac_raw = 0u;
	// return (((uint64_t)(voltage_uV - cal->dac_voltage_offset_uV) * (uint64_t)cal->dac_voltage_inv_factor_uV_n20) >> 20u);
	// avoid mixing signed and unsigned OPs
	if (cal->dac_voltage_offset_uV >= 0)
	{
		const uint32_t dac_offset_uV = cal->dac_voltage_offset_uV;
		if (voltage_uV > dac_offset_uV)	dac_raw = ((uint64_t)(voltage_uV - dac_offset_uV) * (uint64_t)cal->dac_voltage_inv_factor_uV_n20) >> 20u;
		// else dac_raw = 0u;
	}
	else
	{
		const uint32_t dac_offset_uV = -cal->dac_voltage_offset_uV;
		dac_raw = ((uint64_t)(voltage_uV + dac_offset_uV) * (uint64_t)cal->dac_voltage_inv_factor_uV_n20) >> 20u;
	}
	return (dac_raw > 0xFFFFu) ? 0xFFFFu : dac_raw;
}
