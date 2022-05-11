#include <stdint.h>
#include "hw_config.h"
#include "spi_transfer_pru.h"
#include "virtual_harvester.h"
#include "math64_safe.h"
#include "calibration.h"

// internal variables
static uint32_t voltage_set_uV = 0u;
static bool_ft is_rising = 0u;

static uint32_t voltage_hold = 0u;
static uint32_t current_hold = 0u;
static uint32_t voltage_step_x4_uV = 0u;

static uint32_t settle_steps = 0; // adc_ivcurve
static uint32_t interval_step = 1u << 30u;

static uint32_t volt_step_uV = 0u;
static uint32_t power_last_raw = 0u; // adc_mppt_po

static const volatile struct HarvesterConfig *cfg;

// to be used with harvester-frontend
static void harvest_adc_ivcurve(struct SampleBuffer *const, uint32_t);
static void harvest_adc_cv(struct SampleBuffer *const, uint32_t);
static void harvest_adc_mppt_voc(struct SampleBuffer *const, uint32_t);
static void harvest_adc_mppt_po(struct SampleBuffer *const, uint32_t);

// to be used in virtual harvester (part of emulator)
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
	// basic (shared) states for ADC- and IVCurve-Version
	cfg = config;
	voltage_set_uV = cfg->voltage_uV + 1u; // deliberately off for cv-version
	settle_steps = 0u;
	interval_step = 1u << 30u; // deliberately out of bounds

	// TODO: hrv_mode-bit0 is "emulation"-detector
	is_rising = (cfg->hrv_mode >> 1u) & 1u;

	// MPPT-PO
	volt_step_uV = cfg->voltage_step_uV;
	power_last_raw = 0u;

	// for IV-Curve-Version, mostly resets states
	voltage_hold = 0u;
	current_hold = 0u;
	voltage_step_x4_uV = cfg->voltage_step_uV << 2u;
	// TODO: all static vars in sub-fns should be globals (they are anyway), saves space due to overlaps
	// TODO: check that ConfigParams are used in SubFns if applicable
	// TODO: divide lib into IVC and ADC Parts
}

uint32_t sample_adc_harvester(struct SampleBuffer *const buffer, const uint32_t sample_idx)
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
	return 0u;
}

static void harvest_adc_cv(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
/* 	Set constant voltage and log resulting current
 * 	- ADC and DAC voltage should match but can vary, depending on calibration and load (no closed loop)
 * 	- Note: could be self-adjusting (in loop with adc) if needed
 * 	- influencing parameters: voltage_uV,
 */

	/* ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	/* NOTE: it's in here so this timeslot can be used for calculations */
	__delay_cycles(800 / 5);
	const uint32_t current_adc = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	const uint32_t voltage_adc = adc_fastread(SPI_CS_HRV_V_ADC_PIN);

	if (voltage_set_uV != cfg->voltage_uV)
	{
		/* set new voltage if not already set */
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
 * 	- influencing parameters: window_size, voltage_min_uV, voltage_max_uV, voltage_step_uV, wait_cycles_n, hrv_mode (init)
 */

	/* ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	/* NOTE: it's in here so this timeslot can be used for calculations */
	__delay_cycles(800 / 5);
	const uint32_t current_adc = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	const uint32_t voltage_adc = adc_fastread(SPI_CS_HRV_V_ADC_PIN);

	if (settle_steps == 0u)
	{
		if (++interval_step >= cfg->window_size)
		{
			/* reset curve to start */
			voltage_set_uV = is_rising ? cfg->voltage_min_uV : cfg->voltage_max_uV;
			interval_step = 0u;
		}
		else
		{
			/* stepping through */
			if (is_rising)
				voltage_set_uV = add32(voltage_set_uV, cfg->voltage_step_uV);
			else
				voltage_set_uV = sub32(voltage_set_uV, cfg->voltage_step_uV);
		}
		/* check boundaries */
		if (is_rising && (voltage_set_uV > cfg->voltage_max_uV))
			voltage_set_uV = cfg->voltage_max_uV;
		if ((!is_rising) && (voltage_set_uV < cfg->voltage_min_uV))
			voltage_set_uV = cfg->voltage_min_uV;

		/* write new step */
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
 * 	- first part of interval is used for determining the open circuit voltage
 *	- Determine VOC: set DAC to max voltage -> hrv will settle at open voltage -> wait till end of measurement duration and sample valid voltage
 *	- influencing parameters: interval_n, duration_n, setpoint_n8, voltage_max_uV, voltage_min_uV, indirectly wait_cycles_n,
 */
	/* ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	/* NOTE: it's in here so this timeslot can be used for calculations later */
	__delay_cycles(800 / 5);
	const uint32_t current_adc = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	const uint32_t voltage_adc = adc_fastread(SPI_CS_HRV_V_ADC_PIN);

	/* keep track of time, do  step = mod(step + 1, n) */
	if (++interval_step >= cfg->interval_n)	interval_step = 0u;

	if (interval_step == 0u)
	{
		/* open the circuit -> voltage will settle */
		dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | DAC_MAX_VAL);
	}

	if (interval_step == cfg->duration_n - 1u)
	{
		/* end of voc-measurement -> lock-in the value */
		const uint32_t voc_uV = cal_conv_adc_raw_to_uV(voltage_adc);
		voltage_set_uV = mul32(voc_uV, cfg->setpoint_n8) >> 8u;

		/* check boundaries */
		if (voltage_set_uV > cfg->voltage_max_uV)
			voltage_set_uV = cfg->voltage_max_uV;
		if (voltage_set_uV < cfg->voltage_min_uV)
			voltage_set_uV = cfg->voltage_min_uV;

		/* write setpoint voltage */
		const uint32_t voltage_raw = cal_conv_uV_to_dac_raw(voltage_set_uV);
		dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | voltage_raw);
	}

	if (interval_step < cfg->duration_n)
	{
		/* output disconnected during voc-measurement */
		buffer->values_current[sample_idx] = 0u;
		buffer->values_voltage[sample_idx] = voltage_adc; // keep voltage for debug-purposes
	}
	else
	{
		/* converter-mode at pre-set VOC */
		buffer->values_current[sample_idx] = current_adc;
		buffer->values_voltage[sample_idx] = voltage_adc;
	}
}



static void harvest_adc_mppt_po(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
	/*	perturbe & observe
	 * 	- move a voltage step every interval and evaluate power-increase
	 * 		- if higher -> keep this step-direction and begin doubling step-size
	 * 		- if lower -> reverse direction and move smallest step back
	 * 		- resulting steps if direction is kept: 1, 1, 2, 4, 8, ...
	 *	- influencing parameters: interval_n, voltage_set_uV, voltage_step_uV, voltage_min_uV, voltage_max_uV,
	 */
	/* ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	/* NOTE: it's in here so this timeslot can be used for calculations */
	__delay_cycles(800 / 5);
	const uint32_t current_adc = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	const uint32_t voltage_adc = adc_fastread(SPI_CS_HRV_V_ADC_PIN);

	/* keep track of time, do  step = mod(step + 1, n) */
	if (++interval_step >= cfg->interval_n)	interval_step = 0u;

	if (interval_step == 0u)
	{
		const uint32_t power_raw = mul32(current_adc, voltage_adc);
		if (power_raw > power_last_raw)
		{
			/* got higher power -> keep direction, move further, speed up */
			if (is_rising)
				voltage_set_uV = add32(voltage_set_uV, volt_step_uV);
			else
				voltage_set_uV = sub32(voltage_set_uV, volt_step_uV);
			volt_step_uV = mul32(2u, volt_step_uV);
			if (volt_step_uV > 300000u) volt_step_uV = 300000u; // TODO: new, max step size
		}
		else
		{
			/* got less power -> reverse direction, restart step-size */
			is_rising ^= 1u;
			volt_step_uV = cfg->voltage_step_uV;
			if (is_rising)
				voltage_set_uV = add32(voltage_set_uV, volt_step_uV);
			else
				voltage_set_uV = sub32(voltage_set_uV, volt_step_uV);
		}
		power_last_raw = power_raw;

		// TODO: experimental, to keep contact to solar-voltage when voltage is dropping
		const uint32_t adc_uV = cal_conv_adc_raw_to_uV(voltage_adc);
		const uint32_t diff_uV = sub32(voltage_set_uV, adc_uV);
		if (is_rising && (diff_uV > (volt_step_uV << 1u)))
		{
			is_rising = 0u;
			voltage_set_uV = sub32(adc_uV, volt_step_uV);
		}

		/* check boundaries */
		if (voltage_set_uV >= cfg->voltage_max_uV)
		{
			voltage_set_uV = cfg->voltage_max_uV;
			is_rising = 0u;
			volt_step_uV = cfg->voltage_step_uV;
		}
		if (voltage_set_uV <= cfg->voltage_min_uV)
		{
			voltage_set_uV = cfg->voltage_min_uV;
			is_rising = 1u;
			volt_step_uV = cfg->voltage_step_uV;
		}

		/* write setpoint voltage */
		const uint32_t voltage_raw = cal_conv_uV_to_dac_raw(voltage_set_uV);
		dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | voltage_raw);
	}
	buffer->values_current[sample_idx] = current_adc;
	buffer->values_voltage[sample_idx] = voltage_adc;
}

// TODO: add ISC&VOC-Harvest-Recorder (higher sampling-rate for solar-cells)
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
	/* abs(step_size) -> for detecting reset of sawtooth */
	const uint32_t step_size_now = (*p_voltage_uV > voltage_last) ? (*p_voltage_uV - voltage_last) : (voltage_last - *p_voltage_uV);
	/* voltage_set_uV can change outside of loop, so algo has to keep track */
	const uint32_t distance_now = (*p_voltage_uV > voltage_set_uV) ? (*p_voltage_uV - voltage_set_uV) : (voltage_set_uV - *p_voltage_uV);
	const uint32_t distance_last = (voltage_last > voltage_set_uV) ? (voltage_last - voltage_set_uV) : (voltage_set_uV - voltage_last);

	if ((compare_now != compare_last) && (step_size_now < voltage_step_x4_uV))
	{
		/* a fresh ConstVoltage was found in stream, choose the closer value
		 * TODO: could also be interpolated if sampling-routine has time to spare */
		if ((distance_now < distance_last) && (distance_now < voltage_step_x4_uV))
		{
			voltage_hold = *p_voltage_uV;
			current_hold = *p_current_nA;
		}
		else if ((distance_last < distance_now) && (distance_last < voltage_step_x4_uV))
		{
			voltage_hold = voltage_last;
			current_hold = current_last;
		}
	}
	voltage_last = *p_voltage_uV;
	current_last = *p_current_nA;
	compare_last = compare_now;

	/* manipulate the values of the parameter-pointers ("return values") */
	*p_voltage_uV = voltage_hold;
	*p_current_nA = current_hold;
}

static void harvest_iv_mppt_voc(uint32_t * const p_voltage_uV, uint32_t * const p_current_nA)
{
	/* VOC - working on an iv-curve-stream, without complete curve-memory
	 * NOTE with no memory, there is a time-gap before CV gets picked up by harvest_iv_cv()
	 *  - influencing parameters: interval_n, duration_n, current_limit_nA, voltage_min_uV, voltage_max_uV, setpoint_n8, window_size
	 * 		   from init: (wait_cycles_n), voltage_uV (for cv())
	 */
	static uint32_t age_now = 0u, voc_now = 0u;
	static uint32_t age_nxt = 0u, voc_nxt = 0u;

	/* keep track of time, do  step = mod(step + 1, n) */
	if (++interval_step >= cfg->interval_n)	interval_step = 0u;
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
	if ((age_now > cfg->window_size) || (voc_nxt <= voc_now))
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
	/* Perturbe & Observe
	 * NOTE with no memory, there is a time-gap before CV gets picked up by harvest_iv_cv()
	 * - influencing parameters: interval_n, voltage_step_uV, voltage_max_uV, voltage_min_uV
	 */
	static uint32_t power_last = 0u;

	/* keep track of time, do  step = mod(step + 1, n) */
	if (++interval_step >= cfg->interval_n)	interval_step = 0u;

	/* underlying cv-algo is updating the current harvest-power */
	harvest_iv_cv(p_voltage_uV, p_current_nA);
	/* p_voltage_uV and p_current_nA are changed now! */

	if (interval_step == 0u)
	{
		const uint32_t power_now = mul32(*p_voltage_uV, *p_current_nA);
		if (power_now > power_last)
		{
			/* got higher power -> keep direction, move further, speed up */
			if (is_rising)
				voltage_set_uV = add32(voltage_set_uV, volt_step_uV);
			else
				voltage_set_uV = sub32(voltage_set_uV, volt_step_uV);
			volt_step_uV = mul32(2u, volt_step_uV);
		}
		else
		{
			/* got less power -> reverse direction */
			is_rising ^= 1u;
			volt_step_uV = cfg->voltage_step_uV;
			if (is_rising)
				voltage_set_uV = add32(voltage_set_uV, volt_step_uV);
			else
				voltage_set_uV = sub32(voltage_set_uV, volt_step_uV);
		}
		power_last = power_now;

		/* check boundaries */
		if (voltage_set_uV >= cfg->voltage_max_uV)
		{
			voltage_set_uV = cfg->voltage_max_uV;
			is_rising = 0u;
			volt_step_uV = cfg->voltage_step_uV;
		}
		if (voltage_set_uV <= cfg->voltage_min_uV)
		{
			voltage_set_uV = cfg->voltage_min_uV;
			is_rising = 1u;
			volt_step_uV = cfg->voltage_step_uV;
		}
	}
}

static void harvest_iv_mppt_opt(uint32_t * const p_voltage_uV, uint32_t * const p_current_nA)
{
	/* Derivate of VOC -> selects highest power directly
	 * - influencing parameters: window_size, voltage_min_uV, voltage_max_uV,
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
	if ((age_now > cfg->window_size) || (power_nxt >= power_now))
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
