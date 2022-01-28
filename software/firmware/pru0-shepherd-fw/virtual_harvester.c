#include <stdint.h>
#include "hw_config.h"
#include "spi_transfer_pru.h"
#include "virtual_harvester.h"
#include "math64_safe.h"
#include "calibration.h"

// internal variables
static uint32_t voltage_set_uV = 0u;

static uint32_t window_samples = 0u;
static uint32_t voltage_hold = 0u;
static uint32_t current_hold = 0u;
static uint32_t voltage_step_x4_uV = 0u;

static const volatile struct HarvesterConfig *cfg;

static void harvest_adc_ivcurve(struct SampleBuffer *const, uint32_t);
static void harvest_adc_cv(struct SampleBuffer *const, uint32_t);
static void harvest_adc_mppt_voc(struct SampleBuffer *const, uint32_t);
static void harvest_adc_mppt_po(struct SampleBuffer *const, uint32_t);

static void harvest_iv_cv(uint32_t *const p_voltage_uV, uint32_t *const p_current_nA);
static void harvest_iv_mppt_voc(uint32_t *const p_voltage_uV, uint32_t *const p_current_nA);
static void harvest_iv_mppt_po(uint32_t *const p_voltage_uV, uint32_t *const p_current_nA);
static void harvest_iv_mppt_opt(uint32_t *const p_voltage_uV, uint32_t *const p_current_nA);

#define HRV_IVCURVE		(1u << 4u)
#define HRV_CV			(1u << 8u)
#define HRV_MPPT_VOC		(1u << 12u)
#define HRV_MPPT_PO		(1u << 13u)
#define HRV_MPPT_OPT		(1u << 14u)


void harvester_initialize(const volatile struct HarvesterConfig *const config)
{
	// for ADC- and IVCurve-Version
	cfg = config;
	voltage_set_uV = cfg->voltage_uV;

	// for IV-Curve-Version, mostly resets states
	window_samples = cfg->window_size; // already manipulated in py, samples = window_size * (1 + wait_samples)
	voltage_hold = 0u;
	current_hold = 0u;
	voltage_step_x4_uV = cfg->voltage_step_uV << 2u;
	// TODO: all static vars in sub-fns should be globals (they are anyway), saves space due to overlaps
	// TODO: check that ConfigParams are used in SubFns if applicable
	// TODO: divide lib into IVC and ADC Parts
}

void sample_adc_harvester(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
	if (cfg->algorithm >= HRV_MPPT_PO)
		harvest_adc_mppt_po(buffer, sample_idx);
	else if (cfg->algorithm >= HRV_MPPT_VOC)
		harvest_adc_mppt_voc(buffer, sample_idx);
	else if (cfg->algorithm >= HRV_CV)
		harvest_adc_cv(buffer, sample_idx);
	else if (cfg->algorithm >= HRV_IVCURVE)
		harvest_adc_ivcurve(buffer, sample_idx);
	// todo: else send error to system
}

static void harvest_adc_cv(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
/* 	Set constant voltage and log resulting current
 * 	- ADC and DAC voltage should match but can vary, depending on calibration and load (no closed loop)
 * 	- influencing parameters: voltage_uV,
 */

	/* ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	/* NOTE: it's in here so this timeslot can be used for calculations */
	__delay_cycles(800 / 5);
	const uint32_t current_adc = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	const uint32_t voltage_adc = adc_fastread(SPI_CS_HRV_V_ADC_PIN);
	// TODO: could be self-adjusting (in loop with adc) if needed
	if (voltage_set_uV != cfg->voltage_uV)
	{
		voltage_set_uV = cfg->voltage_uV;
		const uint32_t voltage_raw = cal_conv_uV_to_dac_raw(voltage_set_uV);
		dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | voltage_raw);
	}
	buffer->values_current[sample_idx] = current_adc;
	buffer->values_voltage[sample_idx] = voltage_adc;
}

static void harvest_adc_ivcurve(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
/* 	Record iv-curves
 * 	- by controlling voltage with sawtooth
 * 	- influencing parameters: window_size, voltage_min_uV, voltage_max_uV, voltage_step_uV, wait_cycles_n
 */
	static uint32_t settle_steps = 0;
	static uint32_t interval_step = 1u << 30u; // deliberately out of bounds

	/* ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	/* NOTE: it's in here so this timeslot can be used for calculations */
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
		if (voltage_set_uV > cfg->voltage_max_uV)
			voltage_set_uV = cfg->voltage_max_uV;
		const uint32_t voltage_raw = cal_conv_uV_to_dac_raw(voltage_set_uV);
		dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | voltage_raw);
		settle_steps = cfg->wait_cycles_n;
	}
	else
		settle_steps--;

	buffer->values_current[sample_idx] = current_adc;
	buffer->values_voltage[sample_idx] = voltage_adc;
}

static void harvest_adc_mppt_voc(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
/*	Determine VOC and harvest
 * 	- search by Divide and Conquer (until predefined resolution limit is reached)
 *	- logs current adc-values except during VOC-Search (values = 0)
 *	- influencing parameters: interval_n, duration_n, setpoint_n8, current_limit_nA, dac_resolution_bit, wait_cycles_n
 *	TODO: algorithm could probably be easier, see harvester_voc() below
 *	TODO: include v_min/max
 */
	static uint32_t interval_step = 1u << 30u; // deliberately out of bounds
	static uint32_t settle_steps = 0u;
	static uint32_t voltage_raw = 0u;
	static uint32_t refinement_pos = 0u;

	/* ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	/* NOTE: it's in here so this timeslot can be used for calculations later */
	__delay_cycles(800 / 5);
	const uint32_t current_adc = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	const uint32_t voltage_adc = adc_fastread(SPI_CS_HRV_V_ADC_PIN);

	/* keep track of time */
	interval_step = (interval_step >= cfg->interval_n) ? 0u : interval_step + 1u;

	if (interval_step == 0)
	{
		settle_steps = 0u;
		voltage_raw = 0u;
		refinement_pos = (DAC_M_BIT - 1u);
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
				const uint32_t current_nA = cal_conv_adc_raw_to_nA(current_adc);
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


static void harvester_voc(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
	/* empty playground for new algorithms to test in parallel with above reference algorithm */
	/* demo-algorithm: VOC */
	// TODO: better alternative to algo above, but not ready to be a plug-in-replacement

	static const uint8_ft SETTLE_INC = 5;
	/* ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	__delay_cycles(800 / 5);
	//GPIO_TOGGLE(DEBUG_PIN1_MASK);
	const uint32_t current_adc = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	const uint32_t voltage_adc = adc_fastread(SPI_CS_HRV_V_ADC_PIN);
	//GPIO_TOGGLE(DEBUG_PIN1_MASK);
	/* just a simple algorithm that sets 75% of open circuit voltage_adc  */
	if (sample_idx <= SETTLE_INC)
	{
		if (sample_idx == 0)
		{
			dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | DAC_MAX_VAL);
		}
		else if (sample_idx == SETTLE_INC)
		{
			/* factor = 75 % * 76.2939 uV / 19.5313 uV = ~ 393 / 2048  */
			const uint32_t voltage_dac = (393u * voltage_adc) >> 11u;
			dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | voltage_dac);
		}
	}

	/* TODO: also use ch-a of adc, shared_mememory->dac_auxiliary_voltage_raw */
	//static uint32_t aux_voltage_mV =

	buffer->values_current[sample_idx] = current_adc;
	buffer->values_voltage[sample_idx] = voltage_adc;
}


static void harvest_adc_mppt_po(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
	/*	perturbe & observe
	 * 	- move a voltage step every interval and evaluate power-increase
	 * 		- if higher -> keep this step-direction and begin doubling step-size
	 * 		- if lower -> reverse direction and move smallest step back
	 * 		- resulting steps if direction is kept: 1, 1, 2, 4, 8, ...
	 *	- influencing parameters: interval_n, voltage_set_uV, voltage_step_uV, voltage_min_uV, voltage_max_uV,
	 *				(current_limit_nA)
	 */
	static uint32_t interval_step = 1u << 30u; // deliberately out of bound
	static bool_ft incr_direction = 1u; // 0: down, 1: up
	static uint32_t incr_step_uV = 100u;
	static uint32_t power_last_raw = 0u;

	/* ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	/* NOTE: it's in here so this timeslot can be used for calculations */
	__delay_cycles(800 / 5);
	const uint32_t current_adc = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	const uint32_t voltage_adc = adc_fastread(SPI_CS_HRV_V_ADC_PIN);

	/* keep track of time */
	interval_step = (interval_step >= cfg->interval_n) ? 0u : interval_step + 1u;

	if (interval_step == 0)
	{
		const uint32_t power_raw = mul32(current_adc, voltage_adc);
		if (power_raw > power_last_raw)
		{
			/* got higher power -> keep direction, move further, speed up */
			if (incr_direction)
				voltage_set_uV = add32(voltage_set_uV, incr_step_uV);
			else
				voltage_set_uV = sub32(voltage_set_uV, incr_step_uV);
			incr_step_uV = mul32(2u, incr_step_uV);
		}
		else
		{
			/* got less power -> reverse direction */
			incr_direction ^= 1u;
			incr_step_uV = cfg->voltage_step_uV;
			if (incr_direction)
				voltage_set_uV = add32(voltage_set_uV, incr_step_uV);
			else
				voltage_set_uV = sub32(voltage_set_uV, incr_step_uV);
		}
		power_last_raw = power_raw;

		if (voltage_set_uV > cfg->voltage_max_uV)
			voltage_set_uV = cfg->voltage_max_uV;
		if (voltage_set_uV < cfg->voltage_min_uV)
			voltage_set_uV = cfg->voltage_min_uV;
		const uint32_t voltage_raw = cal_conv_uV_to_dac_raw(voltage_set_uV);
		dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | voltage_raw);
	}
	buffer->values_current[sample_idx] = current_adc;
	buffer->values_voltage[sample_idx] = voltage_adc;
}

/* // TODO: do we need a constant-current-version?
const uint32_t current_nA = cal_conv_adc_raw_to_nA(current_adc); // TODO: could be simplified by providing raw-value in cfg
if (current_nA > cfg->current_limit_nA)
*/


void sample_iv_harvester(uint32_t * const p_voltage_uV, uint32_t * const p_current_nA)
{
	// check for IVCurve-Input Indicator and use selected algo
	if (cfg->window_size <= 1)
		return;
	else if (cfg->algorithm >= HRV_MPPT_OPT)
		harvest_iv_mppt_opt(p_voltage_uV, p_current_nA);
	else if (cfg->algorithm >= HRV_MPPT_PO)
		harvest_iv_mppt_po(p_voltage_uV, p_current_nA);
	else if (cfg->algorithm >= HRV_MPPT_VOC)
		harvest_iv_mppt_voc(p_voltage_uV, p_current_nA);
	else if (cfg->algorithm >= HRV_CV)
		harvest_iv_cv(p_voltage_uV, p_current_nA);
	// todo: else send error to system
}


static void harvest_iv_cv(uint32_t * const p_voltage_uV, uint32_t * const p_current_nA)
{
	/* look for wanted constant voltage in an iv-curve-stream (constantly moving up or down in voltage, jumping back when limit reached)
	 * - influencing parameters: voltage_uV (in init)
	 * - no min/max usage here, the main FNs do that, or python if cv() is used directly
	 * */
	static uint32_t voltage_last = 0u, current_last = 0u;
	static bool_ft	compare_last = 0u;

	/* find matching voltage with threshold-crossing-detection -> direction of curve is irrelevant */
	const bool_ft compare_now = *p_voltage_uV < voltage_set_uV;
	// -> abs()
	const uint32_t voltage_step = (*p_voltage_uV > voltage_last) ? (*p_voltage_uV - voltage_last) : (voltage_last - *p_voltage_uV);

	if ((compare_now != compare_last) && (voltage_step < voltage_step_x4_uV))
	{
		/* a new ConstVoltage was found, take the smaller / safer voltage
		 * TODO: could also be interpolated if sampling-routine has time to spare */
		if (voltage_last < *p_voltage_uV)
		{
			voltage_hold = voltage_last;
			current_hold = current_last;
		}
		else
		{
			voltage_hold = *p_voltage_uV;
			current_hold = *p_current_nA;
		}
	}
	voltage_last = *p_voltage_uV;
	current_last = *p_current_nA;
	compare_last = compare_now;

	/* manipulate the return-value */
	*p_voltage_uV = voltage_hold;
	*p_current_nA = current_hold;
}

static void harvest_iv_mppt_voc(uint32_t * const p_voltage_uV, uint32_t * const p_current_nA)
{
	/* VOC - working on an iv-curve-stream, without complete curve-memory
	 * NOTE with no memory, there is a time-gap before CV gets picked up by harvest_iv_cv()
	 *  - influencing parameters: interval_n, duration_n, current_limit_nA, voltage_min_uV, voltage_max_uV, setpoint_n8
	 * 		   from init: window_size, (wait_cycles_n), voltage_uV (for cv())
	 */
	static uint32_t age_now = 0u, voc_now = 0u;
	static uint32_t age_nxt = 0u, voc_nxt = 0u;
	static uint32_t interval_step = 1u << 30u; // deliberately out of bound

	/* keep track of time */
	interval_step = (interval_step >= cfg->interval_n) ? 0u : interval_step + 1u;
	age_nxt++;
	age_now++;

	/* lookout for new VOC */
	if ((*p_current_nA < cfg->current_limit_nA) &&
	    (*p_voltage_uV <= voc_nxt) &&
	    (*p_voltage_uV >= cfg->voltage_min_uV) &&
	    (*p_voltage_uV <= cfg->voltage_max_uV))
	{
		voc_nxt = *p_voltage_uV;
		age_nxt = 0u;
	}

	/* current "best VOC" (lowest voltage with zero-current) can not get too old, or be NOT the best */
	if ((age_now > window_samples) || (voc_nxt <= voc_now))
	{
		age_now = age_nxt;
		voc_now = voc_nxt;
		age_nxt = 0u;
		voc_nxt = cfg->voltage_max_uV;
	}

	/* underlying cv-algo is doing the rest */
	harvest_iv_cv(p_voltage_uV, p_current_nA);

	/* emulate VOC Search @ beginning of interval duration */
	if (interval_step < cfg->duration_n)
	{
		/* No Output here, also update wanted const voltage */
		voltage_set_uV = mul32(voc_now, cfg->setpoint_n8) >> 8u;
		*p_current_nA = 0u;
	}
}

static void harvest_iv_mppt_po(uint32_t * const p_voltage_uV, uint32_t * const p_current_nA)
{
	/*	perturbe & observe
	 * NOTE with no memory, there is a time-gap before CV gets picked up by harvest_iv_cv()
	 * - influencing parameters: interval_n, voltage_step_uV, voltage_max_uV, voltage_min_uV
	 */
	static uint32_t interval_step = 1u << 30u; // deliberately out of bounds
	static uint32_t power_last = 0u;
	static bool_ft incr_direction = 1u; // 0: down, 1: up
	static uint32_t incr_step_uV = 100u;

	/* keep track of time */
	interval_step = (interval_step >= cfg->interval_n) ? 0u : interval_step + 1u;

	if (interval_step == 0)
	{
		const uint32_t power_now = mul32(*p_voltage_uV, *p_current_nA);
		if (power_now > power_last)
		{
			/* got higher power -> keep direction, move further, speed up */
			if (incr_direction)
				voltage_set_uV = add32(voltage_set_uV, incr_step_uV);
			else
				voltage_set_uV = sub32(voltage_set_uV, incr_step_uV);
			incr_step_uV = mul32(2u, incr_step_uV);
		}
		else
		{
			/* got less power -> reverse direction */
			incr_direction ^= 1u;
			incr_step_uV = cfg->voltage_step_uV;
			if (incr_direction)
				voltage_set_uV = add32(voltage_set_uV, incr_step_uV);
			else
				voltage_set_uV = sub32(voltage_set_uV, incr_step_uV);
		}
		power_last = power_now;

		if (voltage_set_uV > cfg->voltage_max_uV)
			voltage_set_uV = cfg->voltage_max_uV;
		if (voltage_set_uV < cfg->voltage_min_uV)
			voltage_set_uV = cfg->voltage_min_uV;
	}

	/* underlying cv-algo is doing the rest */
	harvest_iv_cv(p_voltage_uV, p_current_nA);
}

static void harvest_iv_mppt_opt(uint32_t * const p_voltage_uV, uint32_t * const p_current_nA)
{
	/*	derivate of VOC -> selects highest power directly
	 * - influencing parameters: interval_n, voltage_min_uV, voltage_max_uV,
	 */
	static uint32_t age_now = 0u, power_now = 0u, voltage_now = 0u, current_now = 0u;
	static uint32_t age_nxt = 0u, power_nxt = 0u, voltage_nxt = 0u, current_nxt = 0u;

	/* keep track of time */
	age_nxt++;
	age_now++;

	/* search for new max */
	const uint32_t power_fW = mul32(*p_voltage_uV, *p_current_nA);
	if ((power_fW >= power_nxt) &&
	    (*p_voltage_uV >= cfg->voltage_min_uV) &&
	    (*p_voltage_uV <= cfg->voltage_max_uV))
	{
		age_nxt = 0u;
		power_nxt = power_fW;
		voltage_nxt = *p_voltage_uV;
		current_nxt = *p_current_nA;
	}

	/* current "best VOC" (lowest voltage with zero-current) can not get too old, or NOT be the best */
	if ((age_now > window_samples) || (power_nxt >= power_now))
	{
		age_now = age_nxt;
		power_now = power_nxt;
		voltage_now = voltage_nxt;
		current_now = current_nxt;

		age_nxt = 0u;
		power_nxt = 0u;
		voltage_nxt = 0u;
		current_nxt = 0u;
	}

	/* return current max */
	*p_voltage_uV = voltage_now;
	*p_current_nA = current_now;
}
