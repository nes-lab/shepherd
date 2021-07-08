#include <stdint.h>

#include "gpio.h"
#include "hw_config.h"
#include "sampling.h"
#include "virtual_source.h"

/* DAC8562 Register Config */
#define DAC_CH_A_ADDR   (0U << 16U)
#define DAC_CH_B_ADDR   (1U << 16U)
#define DAC_CH_AB_ADDR  (7U << 16U)

#define DAC_CMD_OFFSET  (19U)
#define DAC_ADDR_OFFSET (16U)

#define DAC_MAX_mV	(5000u)
#define DAC_MAX_VAL	(0xFFFFu)
#define DAC_V_LSB	(76.2939e-6)

/* DAC Shift OPs */
#define DAC_V_LSB_nV	(76294u)
#define DAC_V_SHIFT 	(10u)
#define DAC_V_FACTOR 	(1000000u * (1u << DAC_V_SHIFT) / DAC_V_LSB_nV)
#define DAC_mV_2_raw(x)	((DAC_V_FACTOR * (x)) >> DAC_V_SHIFT)
// TODO: add calibration data
// Test range and conversion
ASSERT(dac_interm, (DAC_V_FACTOR * DAC_MAX_mV) < ((1ull << 32u) - 1u));
ASSERT(dac_convert, DAC_mV_2_raw(DAC_MAX_mV) <= DAC_MAX_VAL);

static bool_ft link_dac_channels = false;

/* ADS8691 Register Config */
#define REGISTER_WRITE	(0b11010000u << 24u)
#define REGISTER_READ	(0b01001000u << 24u)

#define ADDR_REG_PWRCTL	(0x04u << 16u)
#define WRITE_KEY	(0x69u << 8u)
#define PWRDOWN		(1u)
#define NOT_PWRDOWN	(0u)

#define ADDR_REG_RANGE	(0x14u << 16u)
#define RANGE_SEL_P125 	(0b00001011u)

#define ADC_V_LSB	(19.5313e-6)
#define ADC_C_LSB	(195.313e-9)

/* VIn = DOut * Gain * Vref  / 2^n */
/* VIn = DOut * 1.25 * 4.096 / 2^18 */
/* VIn = DOut * 19.5313 uV */
/* CIn = DOut * 195.313 nA */
extern uint32_t adc_readwrite(uint32_t cs_pin, uint32_t val);
extern uint32_t adc_fastread(uint32_t cs_pin);

/* VOut = (DIn / 2^n ) * VRef * Gain */
/* VOut = (DIn / 2^16) * 2.5  * 2 */
/* VOut = DIn * 76.2939 uV  */
extern void dac_write(uint32_t cs_pin, uint32_t val);

/* NOTE:
 * Changes in HW or ADC/DAC Config also change the calibration.data!
 * (ie. py-package/shepherd/calibration_default.py)
 */

// TODO: how to refresh adc reading before going into sampling (rising cs-edge)
static inline void sample_harvesting(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
	/* reference algorithm */

	static const uint8_ft SETTLE_INC = 5;
	/* NOTE: ADC sampled at last CS-Rising-Edge (new pretrigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
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


static inline void sample_harvesting_test(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
	/* empty playground for new algorithms to test in parallel with above reference algorithm */
	sample_harvesting(buffer, sample_idx);
}


static inline void sample_emulation(volatile struct SharedMem *const shared_mem, struct SampleBuffer *const buffer)
{
	// TODO: pru should trigger a new sample here, 2x CS-Toggle
	//  - acquisition takes 335 ns, conversion ~ 665 ns -> 1 us
	//  - to not waste time, getting both buffer-values takes 600 ns and P_in could be calculated upfront (1.4 us)

	/* Get input current/voltage from shared memory buffer */
	const uint32_t input_current_nA = buffer->values_current[shared_mem->analog_sample_counter];
	const uint32_t input_voltage_uV = buffer->values_voltage[shared_mem->analog_sample_counter];
	vsource_calc_inp_power(input_voltage_uV, input_current_nA);

	/* measure current flow */
	const uint32_t current_adc_raw = adc_fastread(SPI_CS_EMU_ADC_PIN);
	vsource_calc_out_power(current_adc_raw);

	vsource_update_capacitor();

	/* TODO: algo expects already "cleaned"/ calibrated value from buffer */
	const uint32_t voltage_dac = vsource_update_boostbuck(shared_mem);

	if (link_dac_channels)
	{
		/* set both channels with same voltage */
		dac_write(SPI_CS_EMU_DAC_PIN, DAC_CH_AB_ADDR | voltage_dac);
	}
	else
	{
		dac_write(SPI_CS_EMU_DAC_PIN, DAC_CH_B_ADDR | voltage_dac);
	}

	/* write back regulator-state into shared memory buffer */
	buffer->values_current[shared_mem->analog_sample_counter] = current_adc_raw;
	buffer->values_voltage[shared_mem->analog_sample_counter] = voltage_dac;
}


static inline void sample_emulation_test(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
	/* empty playground for new algorithms to test in parallel with above reference algorithm */
	const uint32_t current_adc_raw = adc_fastread(SPI_CS_EMU_ADC_PIN);
	const uint32_t voltage_dac = 5000;
	dac_write(SPI_CS_EMU_DAC_PIN, DAC_CH_B_ADDR | voltage_dac);
	buffer->values_current[sample_idx] = current_adc_raw;
	buffer->values_voltage[sample_idx] = voltage_dac;
}


void sample(volatile struct SharedMem *const shared_mem, struct SampleBuffer *const current_buffer_far,
	    const enum ShepherdMode mode)
{ // ->analog_sample_counter
	switch (mode) // reordered to prioritize longer routines
	{
	case MODE_EMULATE: // ~ ## ns
		sample_emulation(shared_mem, current_buffer_far);
		break;
	case MODE_EMULATE_TEST: // ~ ## ns, TODO: test timing for new revision
		sample_emulation_test(current_buffer_far, shared_mem->analog_sample_counter);
		break;
	case MODE_HARVEST: // ~ ## ns
		sample_harvesting(current_buffer_far, shared_mem->analog_sample_counter);
		break;
	case MODE_HARVEST_TEST: // ~ ## ns
		sample_harvesting_test(current_buffer_far, shared_mem->analog_sample_counter);
		break;
	default:
	    break;
	}
}


uint32_t sample_dbg_adc(const uint32_t channel_num)
{
	uint32_t result;
	/* NOTE: ADC sampled at last CS-Rising-Edge (new pretrigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	__delay_cycles(1000 / 5);

	switch (channel_num)
	{
	case 0:
		result = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
		break;
	case 1:
		result = adc_fastread(SPI_CS_HRV_V_ADC_PIN);
		break;
	default:
		result = adc_fastread(SPI_CS_EMU_ADC_PIN);
		break;
	}
	return result;
}


void sample_dbg_dac(const uint32_t value)
{
	if (value & (1u << 20u)) dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_A_ADDR | (value & 0xFFFF));
	if (value & (1u << 21u)) dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | (value & 0xFFFF));
	if (value & (1u << 22u)) dac_write(SPI_CS_EMU_DAC_PIN, DAC_CH_A_ADDR | (value & 0xFFFF));
	if (value & (1u << 23u)) dac_write(SPI_CS_EMU_DAC_PIN, DAC_CH_B_ADDR | (value & 0xFFFF));
}


static void dac8562_init(const uint32_t cs_pin, const bool_ft activate)
{
	if (activate == 0)
	{
		/* power down both channels if not needed, 1 kOhm to GND */
		dac_write(cs_pin, (0x4u << DAC_CMD_OFFSET) | ((8U + 3U) << 0U));
		__delay_cycles(12);
		return;
	}

	/* Reset all registers -> DAC8562 clears to zero scale (see DAC8562T datasheet Table 17) */
	dac_write(cs_pin, (0x5u << DAC_CMD_OFFSET) | (1U << 0U));
	__delay_cycles(12);

	/* Enable internal 2.5V reference with gain=2 (see DAC8562T datasheet Table 17) */
	dac_write(cs_pin, (0x7u << DAC_CMD_OFFSET) | (1U << 0U));
	__delay_cycles(12);

	/* (redundant) GAIN=2 for DAC-B and GAIN=2 for DAC-A (see DAC8562T datasheet Table 17) */
	dac_write(cs_pin, (0x2u << DAC_ADDR_OFFSET) | (0U << 0U));
	__delay_cycles(12);

	/* LDAC pin inactive for DAC-B and DAC-A -> synchronous mode / update on 24th clk cycle (see DAC8562T datasheet Table 17) */
	dac_write(cs_pin, (0x6u << DAC_CMD_OFFSET) | (3U << 0U));
	__delay_cycles(12);

	/* activate both channels */
	dac_write(cs_pin, (0x4u << DAC_CMD_OFFSET) | (3U << 0U));
	__delay_cycles(12);
}


static void ads8691_init(const uint32_t cs_pin, const bool_ft activate)
{
	if (activate)
	{
		adc_readwrite(cs_pin, REGISTER_WRITE | ADDR_REG_PWRCTL | NOT_PWRDOWN);
	}
	else
	{
		adc_readwrite(cs_pin, REGISTER_WRITE | ADDR_REG_PWRCTL | WRITE_KEY);
		adc_readwrite(cs_pin, REGISTER_WRITE | ADDR_REG_PWRCTL | WRITE_KEY | PWRDOWN);
		return;
	}

	/* set Input Range = 1.25 * Vref, with Vref = 4.096 V, -> LSB = 19.53 uV */
	adc_readwrite(cs_pin, REGISTER_WRITE | ADDR_REG_RANGE | RANGE_SEL_P125);

/*	adc_readwrite(cs_pin, REGISTER_READ | ADDR_REG_RANGE);
	const uint32_t  response = adc_readwrite(cs_pin, 0u);
	if (response != RANGE_SEL_P125)
	{
		// TODO: Alert kernel module that this hw-unit seems to be not present
	}*/ // TODO: checkup disabled for now, doubles adc-init-speed
}

// harvest-init takes 	32'800 ns ATM
// emulator-init takes
void sample_init(const volatile struct SharedMem *const shared_mem)
{
	/* Chip-Select signals are active low */
	GPIO_ON(SPI_CS_HRV_DAC_MASK | SPI_CS_HRV_C_ADC_MASK | SPI_CS_HRV_V_ADC_MASK);
	GPIO_ON(SPI_CS_EMU_DAC_MASK | SPI_CS_EMU_ADC_MASK);
	GPIO_OFF(SPI_SCLK_MASK | SPI_MOSI_MASK);

	const enum ShepherdMode mode = (enum ShepherdMode)shared_mem->shepherd_mode;
	const uint32_t dac_ch_a_voltage_raw = shared_mem->dac_auxiliary_voltage_raw & 0xFFFF;

	/* deactivate hw-units when not needed, initialize the other */
	const bool_ft use_harvester = (mode == MODE_HARVEST) || (mode == MODE_HARVEST_TEST) || (mode == MODE_DEBUG);
	const bool_ft use_emulator = (mode == MODE_EMULATE) || (mode == MODE_EMULATE_TEST) || (mode == MODE_DEBUG);

	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	dac8562_init(SPI_CS_HRV_DAC_PIN, use_harvester);
	// TODO: init more efficient, can be done all same ICs at the same time (common cs_low)
	// just init-emulator takes 10.5 us, 5x DAC * 750 ns, 4x ADC x 1440 ns

	if (use_harvester)
	{
		/* after DAC-Reset the output is at Zero, fast return CH B to Max to not drain the power-source */
		/* NOTE: if harvester is not used, dac is currently shut down -> connects power source with 1 Ohm to GND */
		dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | DAC_MAX_VAL);
		dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_A_ADDR | dac_ch_a_voltage_raw); // TODO: write aux more often if needed
	}

	ads8691_init(SPI_CS_HRV_C_ADC_PIN, use_harvester); // TODO: when asm-spi-code would take pin-mask, the init could be done in parallel
	ads8691_init(SPI_CS_HRV_V_ADC_PIN, use_harvester);

	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	dac8562_init(SPI_CS_EMU_DAC_PIN, use_emulator);
	ads8691_init(SPI_CS_EMU_ADC_PIN, use_emulator);

	/* switch to set both channels with same voltage during sampling, when condition is met (value > 16bit) */
	link_dac_channels = (shared_mem->dac_auxiliary_voltage_raw > 0xFFFF);

	if (use_emulator)
	{
		dac_write(SPI_CS_EMU_DAC_PIN, DAC_CH_A_ADDR | dac_ch_a_voltage_raw);
		// TODO: we also need to make sure, that this fn returns voltages to same, zero or similar
		//  (init is called after sampling, but is the mode correct?)
	}

	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	if (mode == MODE_EMULATE)
	{
		vsource_init(&shared_mem->virtsource_settings, &shared_mem->calibration_settings);
	}
}
