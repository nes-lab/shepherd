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

/* private FNs */
static inline uint32_t conv_adc_raw_to_nA(uint32_t current_raw); // TODO: the first two could also be helpful for sampling
static inline uint32_t conv_uV_to_dac_raw(uint32_t voltage_uV);

static uint32_t get_input_efficiency_n8(uint32_t voltage_uV, uint32_t current_nA);
static uint32_t get_output_inv_efficiency_n4(uint32_t current_nA);

#ifdef __GNUC__
static uint8_t get_left_zero_count(const uint32_t value)
{
	/* there is an ASM-COMMAND for that, LMBD r2, r1, 1 */
	uint32_t _value = value;
	uint8_t	count = 32;
	for (; _value > 0; _value >>= 1) count--;
	return count;
}

static uint32_t max_value(uint32_t value1, uint32_t value2)
{
	if (value1 > value2) return value1;
	else return value2;
}

static uint32_t min_value(uint32_t value1, uint32_t value2)
{
	if (value1 < value2) return value1;
	else return value2;
}
#else
/* use from asm-file */
extern inline uint8_t get_left_zero_count(uint32_t value);
extern inline uint32_t max_value(uint32_t value1, uint32_t value2);
extern inline uint32_t min_value(uint32_t value1, uint32_t value2);
#endif

static uint64_t udiv(const uint64_t value1, const uint32_t value2)
{
	const uint8_t lzc2 = get_left_zero_count(value2) + 31u;
	uint64_t v2_sub = ((uint64_t)value2) << lzc2;
	uint64_t v2_add = ((uint64_t)1ull) << lzc2;
	uint64_t v1_rem = value1;
	uint64_t v3 = 0ull;
	//while (min_value(v2_sub, v1_rem))
	while (v2_sub >= 1)
	{
		if (v1_rem >= v2_sub)
		{
			v1_rem = v1_rem - v2_sub;
			v3 += v2_add;
		}
		v2_sub >>= 1u;
		v2_add >>= 1u;
	}
	return v3;
}

#define DIV_SHIFT 	(17u) // 2^17 as uV is ~ 131 mV
#define DIV_LUT_SIZE 	(39u)

/* LUT
 * Generation:
 * - entry[n] = (1u << 27) / (n * (1u << 17)) = (1u << 10) / n
 * - leave out first (div0)
 * - largest Entry[38] is 5.12 V
 */
static const uint32_t LUT_div_uV_n27[DIV_LUT_SIZE] =
	{1023, 512, 341, 256, 205, 171, 146, 128,
	  114, 102,  93,  85,  79,  73,  68,  64,
	   60,  57,  54,  51,  49,  47,  45,  43,
	   41,  39,  38,  37,  35,  34,  33,  32,
	   31,  30,  29,  28,  28,  27,  26};

static inline uint64_t div_uV_n4(const uint64_t power_fW_n4, const uint32_t voltage_uV)
{
	uint8_t lut_pos = (voltage_uV >> DIV_SHIFT) - 1u;
	if (lut_pos >= DIV_LUT_SIZE)
		lut_pos = DIV_LUT_SIZE - 1u;
	return ((power_fW_n4 >> 10u) * LUT_div_uV_n27[lut_pos]) >> 17u;
}


/* data-structure that hold the state - variables for direct use */
struct VirtSource_State {
	/* Boost converter */
	uint64_t P_inp_fW_n8;
	uint64_t P_out_fW_n4;
	uint32_t dt_us_per_C_nF_n28;
	uint64_t V_store_uV_n32;
	uint32_t interval_check_thrs_sample;
	/* Buck converter */
	bool_ft  has_buck;
	uint32_t V_out_dac_uV;
	uint32_t V_out_dac_raw;
	/* hysteresis */
	uint64_t output_enable_threshold_uV_n32;
	uint64_t output_disable_threshold_uV_n32;
	uint64_t dV_output_enable_uV_n32;
};

/* (local) global vars to access in update function */
static struct VirtSource_State vss;
static volatile struct VirtSource_Config * vs_cfg;
static volatile struct Calibration_Config * cal_cfg;
#define dt_us_const 	(SAMPLE_INTERVAL_NS / 1000u)  // = 10

void vsource_struct_init_testable(volatile struct VirtSource_Config *const vsc_arg)
{
	/* this init is nonsense, but testable for byteorder and proper values */
	uint32_t i32 = 0u;
	vsc_arg->converter_mode = i32++;

	vsc_arg->C_output_nF = i32++;
	vsc_arg->V_inp_boost_threshold_uV = i32++;
	vsc_arg->C_storage_nF = i32++;
	vsc_arg->V_storage_init_uV = i32++;
	vsc_arg->V_storage_max_uV = i32++;
	vsc_arg->I_storage_leak_nA = i32++;
	vsc_arg->V_storage_enable_threshold_uV = i32++;
	vsc_arg->V_storage_disable_threshold_uV = i32++;
	vsc_arg->interval_check_thresholds_ns = i32++;
	vsc_arg->V_pwr_good_disable_threshold_uV = i32++;
	vsc_arg->V_pwr_good_enable_threshold_uV = i32++;
	vsc_arg->dV_stor_en_thrs_uV = i32++;

	vsc_arg->V_output_uV = i32++;
	vsc_arg->dV_stor_low_uV = i32++;

	uint8_t i8A = 0u;
	uint8_t i8B = 0u;
	for (uint32_t outer = 0u; outer < LUT_SIZE; outer++)
	{
		for (uint32_t inner = 0u; inner < LUT_SIZE; inner++)
		{
			vsc_arg->LUT_inp_efficiency_n8[outer][inner] = i8A++;
		}
		vsc_arg->LUT_out_inv_efficiency_n4[outer] = i8B++;
	}
}


void vsource_init(volatile struct VirtSource_Config *const vsc_arg, volatile struct Calibration_Config *const cal_arg)
{
	/* Initialize state */
	cal_cfg = cal_arg;
	vs_cfg = vsc_arg; // TODO: can be changed to pointer again, has same performance

	/* Boost Reg */
	vss.dt_us_per_C_nF_n28 = (dt_us_const << 28u) / vs_cfg->C_storage_nF;  // TODO: put that in python

	/* Power-flow in and out of system */
	vss.P_inp_fW_n8 = 0u;
	vss.P_out_fW_n4 = 0u;
	/* container for the stored energy: */
	vss.V_store_uV_n32 = ((uint64_t)vs_cfg->V_storage_init_uV) << 32u;

	/* Check Output-Limits every n Samples: */
	vss.interval_check_thrs_sample = vs_cfg->interval_check_thresholds_ns / SAMPLE_INTERVAL_NS;

	/* Buck Boost */
	vss.has_buck = vs_cfg->converter_mode & 0b10;
	// TODO: make boost also optional

	vss.V_out_dac_uV = vs_cfg->V_output_uV;

	vss.V_out_dac_raw = conv_uV_to_dac_raw(vs_cfg->V_output_uV);

	/* hysteresis-thresholds */
	if (vss.has_buck)
	{
		if (vs_cfg->V_storage_enable_threshold_uV > vs_cfg->V_output_uV)
		{
			vss.output_enable_threshold_uV_n32 = ((uint64_t)vs_cfg->V_storage_enable_threshold_uV) << 32u;
			vss.dV_output_enable_uV_n32 = ((uint64_t)vs_cfg->dV_stor_en_thrs_uV) << 32u;
		}
		else
		{
			vss.dV_output_enable_uV_n32 = ((uint64_t)vs_cfg->dV_stor_low_uV) << 32u;
			vss.output_enable_threshold_uV_n32 = (((uint64_t)vs_cfg->V_output_uV) << 32u) + vss.dV_output_enable_uV_n32;
		}

		if (vs_cfg->V_storage_disable_threshold_uV > vs_cfg->V_output_uV)
		{
			vss.output_disable_threshold_uV_n32 = ((uint64_t)vs_cfg->V_storage_disable_threshold_uV) << 32u;
		}
		else
		{
			vss.output_disable_threshold_uV_n32 = ((uint64_t)vs_cfg->V_output_uV) << 32u;
		}
	}
	else
	{
		vss.output_enable_threshold_uV_n32 = ((uint64_t)vs_cfg->V_storage_enable_threshold_uV) << 32u;
		vss.output_disable_threshold_uV_n32 = ((uint64_t)vs_cfg->V_storage_disable_threshold_uV) << 32u;
		vss.dV_output_enable_uV_n32 = ((uint64_t)vs_cfg->dV_stor_en_thrs_uV) << 32u;
	}

	/* compensate for (hard to detect) current-surge of real capacitors when converter gets turned on
	 * -> this can be const value, because the converter always turns on with "V_storage_enable_threshold_uV"
	 * TODO: currently neglecting: delay after disabling converter, boost only has simpler formula, second enabling when VCap >= V_out
	 * TODO: this can be done in python, even both enable-cases
	 * Math behind this calculation:
	 * Energy-Change in Storage Cap -> 	E_new = E_old - E_output
	 * with Energy of a Cap 	-> 	E_x = C_x * V_x^2 / 2
	 * combine formulas 		-> 	C_store * V_store_new^2 / 2 = C_store * V_store_old^2 / 2 - C_out * V_out^2 / 2
	 * convert formula to V_new 	->	V_store_new^2 = V_store_old^2 - (C_out / C_store) * V_out^2
	 * convert into dV	 	->	dV = V_store_new - V_store_old
	 * in case of V_cap = V_out 	-> 	dV = V_store_old * (sqrt(1 - C_out / C_store) - 1)
	 */
	/*
	const ufloat V_old_sq_uV = mul0(vs_cfg.V_storage_enable_threshold_uV, 0, vs_cfg.V_storage_enable_threshold_uV, 0);
	const ufloat V_out_sq_uV = mul2(vss.V_out_dac_uV, vss.V_out_dac_uV);
	const ufloat cap_ratio   = div0(vs_cfg.C_output_nF, 0, vs_cfg.C_storage_nF, 0);
	const ufloat V_new_sq_uV = sub2(V_old_sq_uV, mul2(cap_ratio, V_out_sq_uV));
	GPIO_ON(DEBUG_PIN1_MASK);
	vss.dV_stor_en_uV = sub1r(vs_cfg.V_storage_enable_threshold_uV, 0, sqrt_rounded(V_new_sq_uV)); // reversed, because new voltage is lower then old
	*/
	// TODO: add tests for valid ranges
}

// TODO: explain design goals and limitations... why does the code looks that way
/* Math behind this Converter
 * Individual drains / sources -> 	P_x = I_x * V_x
 * Efficiency 				eta_x = P_out_x / P_in_x  -> P_out_x = P_in_x * eta_x
 * Power in and out of Converter -> 	P = P_in - P_out
 * Current in storage cap -> 		I = P / V_cap
 * voltage change for Cap -> 		dV = I * dt / C
 * voltage of storage cap -> 		V += dV
 *
 */

void vsource_calc_inp_power(const uint32_t input_voltage_uV, const uint32_t input_current_nA)
{
	// info input: voltage is max 5V => 23 bit, current is max 50 mA => 26 bit
	// info output: with eta beeing 8 bit in size, there is 56 bit headroom for P = U*I = ~ 72 W
	// TODO: p_inp_fW could be calculated in python, even with efficiency-interpolation -> hand voltage and power to pru
	/* BOOST, Calculate current flowing into the storage capacitor */
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	uint32_t V_input_uV = 0u;

	/* disable boost if input voltage too low for boost to work, TODO: is this also in 65ms interval? */
	if (input_voltage_uV >= vs_cfg->V_inp_boost_threshold_uV) {
		V_input_uV = input_voltage_uV;
	}

	/* limit input voltage when higher than voltage of storage cap */
	if (V_input_uV > (vss.V_store_uV_n32 >> 32u)) {
		V_input_uV = (uint32_t)(vss.V_store_uV_n32 >> 32u);
	}

	const uint32_t eta_inp_n8 = get_input_efficiency_n8(V_input_uV, input_current_nA);
	vss.P_inp_fW_n8 = (uint64_t)(eta_inp_n8 * V_input_uV) * input_current_nA;
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
}

void vsource_calc_out_power(const uint32_t current_adc_raw)
{
	// info input: current is max 50 mA => 26 bit
	// info output: with eta beeing 14 bit in size, there is 50 bit headroom for P = U*I = ~ 1 W
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	/* BUCK, Calculate current flowing out of the storage capacitor*/
	const uint64_t dP_leak_fW_n4 = (vss.V_store_uV_n32 >> 28u) * vs_cfg->I_storage_leak_nA;
	const uint32_t I_out_nA = conv_adc_raw_to_nA(current_adc_raw);
	const uint32_t eta_inv_out_n4 = get_output_inv_efficiency_n4(I_out_nA) ? (vss.has_buck) : 1u << 4u;
	vss.P_out_fW_n4 = ((uint64_t)(eta_inv_out_n4 * vss.V_out_dac_uV) * I_out_nA ) + dP_leak_fW_n4;
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
}

void vsource_update_capacitor(void)
{
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	/* Sum up Power and calculate new Capacitor Voltage
	 */
	const uint32_t V_store_uV = vss.V_store_uV_n32 >> 32u;
	const uint64_t P_inp_fW_n4 = vss.P_inp_fW_n8 >> 4u;
	if (P_inp_fW_n4 > vss.P_out_fW_n4) {
		//const uint64_t I_cStor_nA_n4 = (P_inp_fW_n4 - vss.P_out_fW_n4) / V_store_uV;
		//const uint64_t I_cStor_nA_n4 = div_uV_n4((P_inp_fW_n4 - vss.P_out_fW_n4), V_store_uV);
		//vss.V_store_uV_n32 += (vss.dt_us_per_C_nF_n28 * I_cStor_nA_n4); // = dV_cStor_uV_n32

		uint8_ft lut_pos = (V_store_uV >> DIV_SHIFT) - 1u;
		if (lut_pos >= DIV_LUT_SIZE) lut_pos = DIV_LUT_SIZE - 1u;
		vss.V_store_uV_n32 +=  vss.dt_us_per_C_nF_n28 * ((((P_inp_fW_n4 - vss.P_out_fW_n4) >> 10u) * LUT_div_uV_n27[lut_pos]) >> 17u);

		// Make sure the voltage stays in it's boundaries, TODO: is this also in 65ms interval?
		if ((uint32_t)(vss.V_store_uV_n32 >> 32u) > vs_cfg->V_storage_max_uV)
		{
			vss.V_store_uV_n32 = ((uint64_t)vs_cfg->V_storage_max_uV) << 32u;
		}
	} else {
		//const uint64_t I_cStor_nA_n4 = (vss.P_out_fW_n4 - P_inp_fW_n4) / V_store_uV;
		const uint64_t I_cStor_nA_n4 = div_uV_n4((vss.P_out_fW_n4 - P_inp_fW_n4), V_store_uV);
		vss.V_store_uV_n32 -= (vss.dt_us_per_C_nF_n28 * I_cStor_nA_n4); // = dV_cStor_uV_n32
		// check for underflow and possible div0
		if ((V_store_uV < (vss.V_store_uV_n32 >> 32u)) || (vss.V_store_uV_n32 <= 0xFFFFFFFFu))
		{
			vss.V_store_uV_n32 = ((uint64_t)1u) << 32u;
		}
	}
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
}

// TODO: not optimized
uint32_t vsource_update_boostbuck(void)
{
	GPIO_TOGGLE(DEBUG_PIN1_MASK);

	/* connect or disconnect output on certain events */
	static uint32_t sample_count = 0xFFFFFFF0;
	static bool_ft is_outputting = true;
	static bool_ft power_good = true;

	if (++sample_count >= vss.interval_check_thrs_sample)
	{
		sample_count = 0;
		if (is_outputting)
		{
			if (vss.V_store_uV_n32 < vss.output_disable_threshold_uV_n32)
			{
				is_outputting = false;
			}
		}
		else
		{
			if (vss.V_store_uV_n32 >= vss.output_enable_threshold_uV_n32)
			{
				is_outputting = true;
				/* fast charge external virtual output-cap */
				vss.V_store_uV_n32 -= vss.dV_output_enable_uV_n32;
			}
		}

		/* emulate power-good-signal */
		if (power_good)
		{
			if ((vss.V_store_uV_n32 >> 32u) <= vs_cfg->V_pwr_good_disable_threshold_uV)
			{
				power_good = false;
			}
		}
		else
		{
			if ((vss.V_store_uV_n32 >> 32u) >= vs_cfg->V_pwr_good_enable_threshold_uV)
			{
				power_good = true;
			}
		}
		/* TODO: pin is on other PRU */
	}

	if (is_outputting)
	{
		if (!vss.has_buck || ((vss.V_store_uV_n32 >> 32u) < vss.V_out_dac_uV))
		{
			vss.V_out_dac_uV = vss.V_store_uV_n32 >> 32u;
		}
		else
		{
			vss.V_out_dac_uV = vs_cfg->V_output_uV;
		}
		vss.V_out_dac_raw = conv_uV_to_dac_raw(vss.V_out_dac_uV);
	}
	else
	{
		vss.V_out_dac_uV = 0u;
		vss.V_out_dac_raw = 0u;
	}

	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	/* output proper voltage to dac */
	return vss.V_out_dac_raw;
}


/* bring values into adc domain with -> voltage_uV = adc_value * gain_factor + offset
 * original definition in: https://github.com/geissdoerfer/shepherd/blob/master/docs/user/data_format.rst */

// (previous) TODO: unsafe conversion -> n8 can overflow uint32, 50mA are 16 bit as uA, 26 bit as nA, 34 bit as nA_n8-factor
static inline uint32_t conv_adc_raw_to_nA(const uint32_t current_raw)
{
	return ((uint32_t)(((uint64_t)current_raw * cal_cfg->adc_current_factor_nA_n8) >> 8u) - cal_cfg->adc_current_offset_nA);
}

// safe conversion - 5 V is 13 bit as mV, 23 bit as uV, 31 bit as uV_n8
static inline uint32_t conv_uV_to_dac_raw(const uint32_t voltage_uV)
{
	return (((uint64_t)(voltage_uV - cal_cfg->dac_voltage_offset_uV) * cal_cfg->dac_voltage_inv_factor_uV_n20) >> 20u);
}

// TODO: global /nonstatic for tests
uint32_t get_input_efficiency_n8(const uint32_t voltage_uV, const uint32_t current_nA)
{
	uint8_t pos_v = 32u - get_left_zero_count(voltage_uV >> 0u);  // TODO: determine working-range
	uint8_t pos_c = 32u - get_left_zero_count(current_nA >> 0u);
	if (pos_v >= LUT_SIZE) pos_v = LUT_SIZE - 1;
	if (pos_c >= LUT_SIZE) pos_c = LUT_SIZE - 1;
	/* TODO: could interpolate here between 4 values, if there is time for overhead */
        return (uint32_t)vs_cfg->LUT_inp_efficiency_n8[pos_v][pos_c];
}

// TODO: fix input to take SI-units
uint32_t get_output_inv_efficiency_n4(const uint32_t current_nA)
{
	uint8_t pos_c = 32u - get_left_zero_count(current_nA >> 0u);
	if (pos_c >= LUT_SIZE) pos_c = LUT_SIZE - 1u;
	/* TODO: could interpolate here between 2 values, if there is space for overhead */
	return vs_cfg->LUT_out_inv_efficiency_n4[pos_c];
}

void set_input_power_fW(const uint32_t P_fW)
{
	vss.P_inp_fW_n8 = ((uint64_t)P_fW) << 8u;
}

void set_output_power_fW(const uint32_t P_fW)
{
	vss.P_out_fW_n4 = ((uint64_t)P_fW) << 4u;
}

void set_storage_Capacitor_uV(const uint32_t C_uV)
{
	vss.V_store_uV_n32 = ((uint64_t)C_uV) << 32u;
}

uint64_t get_input_power_fW(void)
{
	return (vss.P_inp_fW_n8 >> 8u);
}

uint64_t get_output_power_fW(void)
{
	return (vss.P_out_fW_n4 >> 4u);
}

uint32_t get_storage_Capacitor_uV(void)
{
	return (uint32_t)(vss.V_store_uV_n32 >> 32u);
}
