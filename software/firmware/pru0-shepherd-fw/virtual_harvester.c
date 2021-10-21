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
	config->current_limit_nA = ivalue++;
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

void harvest_adc_cv(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
/* 	Set constant voltage and log resulting current
 * 	- ADC and DAC voltage should match but can vary, depending on calibration and load (no closed loop)
 * 	- influencing parameters: voltage_uV,
 */
	static uint32_t voltage_set_uV = 1u << 30u;

	/* NOTE: ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	/* NOTE2: it is in here so this timeslot can be used for calculations later */
	__delay_cycles(800 / 5);
	const uint32_t current_adc = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	const uint32_t voltage_adc = adc_fastread(SPI_CS_HRV_V_ADC_PIN);
	// TODO: could be self-adjusting (in loop with adc) if needed
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
/* 	Record iv-curves
 * 	- by controlling voltage with sawtooth
 * 	- influencing parameters: window_size, voltage_min_uV, (voltage_max_uV), voltage_step_uV, wait_cycles_n
 */
	static uint32_t voltage_set_uV = 1u << 30u;
	static uint32_t settle_steps = 0;
	static uint32_t interval_step = 1u << 30u;

	/* NOTE: ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	/* NOTE2: it is in here so this timeslot can be used for calculations later */
	__delay_cycles(800 / 5);
	const uint32_t current_adc = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	const uint32_t voltage_adc = adc_fastread(SPI_CS_HRV_V_ADC_PIN);

	if (settle_steps == 0u)
	{
		if (interval_step >= cfg->window_size)
		{
			voltage_set_uV = cfg->voltage_min_uV;
			interval_step = 0u;
		}
		else
		{
			voltage_set_uV += cfg->voltage_step_uV;
			interval_step++;
		}
		const uint32_t voltage_raw = conv_uV_to_dac_raw(voltage_set_uV);
		dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | voltage_raw);
		settle_steps = cfg->wait_cycles_n;
	}
	else
		settle_steps--;

	buffer->values_current[sample_idx] = current_adc;
	buffer->values_voltage[sample_idx] = voltage_adc;
}

void harvest_adc_mppt_voc(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
/*	Determine VOC and harvest
 * 	- search by Divide and Conquer (until predefined resolution limit is reached)
 *	- logs current adc-values except during VOC-Search (values = 0)
 *	- influencing parameters: interval_n, duration_n, setpoint_n8, current_limit_nA, dac_resolution_bit, wait_cycles_n
 */
	static uint32_t interval_step = 1u << 30u; // deliberately out of bounds
	static uint32_t settle_steps = 0u;
	static uint32_t voltage_raw = 0u;
	static uint32_t refinement_pos = 0u;

	/* NOTE: ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	/* NOTE2: it is in here so this timeslot can be used for calculations later */
	__delay_cycles(800 / 5);
	const uint32_t current_adc = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	const uint32_t voltage_adc = adc_fastread(SPI_CS_HRV_V_ADC_PIN);

	if (interval_step >= cfg->interval_n)
	{
		interval_step = 0u;
		settle_steps = 0u;
		current_voc_raw = 0u;
		refinement_pos = (DAC_M_BIT - 1u);
	}
	else
	{
		interval_step++;
	}

	if (interval_step < cfg->duration_n)
	{
		/* VOC Search @ beginning of interval duration */
		if (settle_steps == 0u)
		{
			if (refinement_pos > DAC_M_BIT)
			{
				/* NOP (after last step) */
			}
			if (refinement_pos == DAC_M_BIT)
			{
				/* last step, calculate and set setpoint */
				voltage_raw = mul32(voltage_raw, cfg->setpoint_n8) >> 8u;
				refinement_pos = 2u * DAC_M_BIT; // deactivate
			}
			if (refinement_pos == (DAC_M_BIT - 1u))
			{
				/* first step */
				voltage_raw |= 1u << refinement_pos;
				refinement_pos--;
			}
			else if (refinement_pos >= cfg->dac_resolution_bit)
			{
				/* further steps */
				const uint32_t current_nA = conv_adc_raw_to_nA(current_adc);
				if (current_nA <= cfg->current_limit_nA)
				{
					/* go lower, reverse last addition */
					voltage_raw &= ~(1u << (refinement_pos + 1u));
				}
				/* go higher, halve value */
				voltage_raw |= 1u << refinement_pos;
				if (refinement_pos > cfg->dac_resolution_bit)
				{
					refinement_pos--; // goto further step
				}
				else
				{
					refinement_pos = DAC_M_BIT; // goto last step
				}
			}

			dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | voltage_raw);
			settle_steps = cfg->wait_cycles_n;
		}
		else
		{
			settle_steps--;
		}

		buffer->values_current[sample_idx] = 0u;
		buffer->values_voltage[sample_idx] = 0u;
	}
	else
	{
		buffer->values_current[sample_idx] = current_adc;
		buffer->values_voltage[sample_idx] = voltage_adc;
	}
}

void harvest_adc_mppt_po(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
	/*	perturbe & observe
	 * 	- move a voltage step every interval and evaluate power-increase
	 * 		- if higher -> keep this step-direction and begin doubling step-size
	 * 		- if lower -> reverse direction and move smallest step back
	 * 		- resulting steps if direction is kept: 1, 1, 2, 4, 8, ...
	 *	- influencing parameters: interval_n, voltage_uV, voltage_step_uV, voltage_min_uV, voltage_max_uV,
	 */
	static uint32_t interval_step = 1u << 30u; // deliberately out of bounds
	static bool_ft incr_direction = 1u; // 0: down, 1: up
	static uint32_t incr_step_uV = 0u;
	static uint32_t power_last_raw = 0u;
	static uint32_t voltage_uV = cfg->voltage_uV;

	/* NOTE: ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	/* NOTE2: it is in here so this timeslot can be used for calculations later */
	__delay_cycles(800 / 5);
	const uint32_t current_adc = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	const uint32_t voltage_adc = adc_fastread(SPI_CS_HRV_V_ADC_PIN);

	if (interval_step > cfg->interval_n)
	{
		interval_step = 0u;
		const uint32_t power_raw = mul32(current_adc, voltage_adc);
		const uint32_t current_nA = conv_adc_raw_to_nA(current_adc); // TODO: could be simplified by providing raw-value
		if (current_nA > cfg->current_limit_nA)
		{
			// TODO: not the best design: better divide power from current tracking!
			/* current out of bound -> increase voltage */
			voltage_uV = add32(voltage_uV, incr_step_uV);
			incr_step_uV = mul32(2u, incr_step_uV);
		}
		else if (power_raw > power_last_raw)
		{
			/* got higher power -> keep direction, move further */
			if (incr_direction)
			{
				voltage_uV = add32(voltage_uV, incr_step_uV);
			}
			else
			{
				voltage_uV = sub32(voltage_uV, incr_step_uV);
			}
			incr_step_uV = mul32(2u, incr_step_uV);
		}
		else
		{
			/* got less power -> reverse direction */
			incr_direction ^= 1u;
			incr_step_uV = cfg->voltage_step_uV;
			if (incr_direction)
			{
				voltage_uV = add32(voltage_uV, incr_step_uV);
			}
			else
			{
				voltage_uV = sub32(voltage_uV, incr_step_uV);
			}

		}
		power_last_raw = power_raw;

		if (voltage_uV > cfg->voltage_max_uV)
		{
			voltage_uV = cfg->voltage_max_uV;
		}
		if (voltage_uV < cfg->voltage_min_uV)
		{
			voltage_uV = cfg->voltage_min_uV;
		}
		const uint32_t voltage_raw = conv_uV_to_dac_raw(voltage_uV);
		dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | voltage_raw);
	}
	interval_step++;

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
