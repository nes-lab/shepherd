#include <stdint.h>

#include "gpio.h"
#include "hw_config.h"
#include "sampling.h"
#include "virtual_converter.h"
#include "calibration.h"
#include "spi_transfer_pru.h"
#include "virtual_harvester.h"

static bool_ft dac_aux_link_to_main = false;
static bool_ft dac_aux_link_to_mid = false;

/* NOTE:
 * Changes in HW or ADC/DAC Config also change the calibration.data!
 * (ie. py-package/shepherd/calibration_default.py)
 */

static inline uint32_t sample_emulator(volatile struct SharedMem *const shared_mem, struct SampleBuffer *const buffer)
{
	/* NOTE: ADC-Sample probably not ready -> Trigger at timer_cmp -> ads8691 needs 1us to acquire and convert */
	//__delay_cycles(200 / 5); // current design takes ~1500 ns between CS-Lows

	/* Get input current/voltage from pru1 (these 2 far mem-reads can take from 420 to 300 us -> destroyer of real time) */
	while (shared_mem->analog_value_index != shared_mem->analog_sample_counter);
	uint32_t input_current_nA = shared_mem->analog_value_current;
	uint32_t input_voltage_uV = shared_mem->analog_value_voltage;
	shared_mem->analog_sample_counter++;

	sample_iv_harvester(&input_voltage_uV, &input_current_nA);

	converter_calc_inp_power(input_voltage_uV, input_current_nA);

	/* measure current */
	const uint32_t current_adc_raw = adc_fastread(SPI_CS_EMU_ADC_PIN);

	converter_calc_out_power(current_adc_raw);

	converter_update_cap_storage();

	const uint32_t voltage_dac = converter_update_states_and_output(shared_mem);

	if (dac_aux_link_to_main) /* set both channels with same voltage */
	{
		dac_write(SPI_CS_EMU_DAC_PIN, DAC_CH_AB_ADDR | voltage_dac);
	}
	else	/* only set main channel */
	{
		dac_write(SPI_CS_EMU_DAC_PIN, DAC_CH_A_ADDR | voltage_dac);
	}

	if (dac_aux_link_to_mid)
	{
		// USAGE NOT RECOMMENDED! as it takes ~800 ns and might break realtime
		dac_write(SPI_CS_EMU_DAC_PIN, DAC_CH_A_ADDR | get_V_intermediate_raw());
	}

	/* write back converter-state into shared memory buffer */
	if (get_state_log_intermediate())
	{
		buffer->values_current[shared_mem->analog_sample_counter] = get_I_mid_out_nA();
		buffer->values_voltage[shared_mem->analog_sample_counter] = get_V_intermediate_uV();
	}
	else
	{
		buffer->values_current[shared_mem->analog_sample_counter] = current_adc_raw;
		buffer->values_voltage[shared_mem->analog_sample_counter] = voltage_dac;
	}
	return 1u; // because we already incremented
}


static inline uint32_t sample_emu_ADCs(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
	__delay_cycles(1000 / TIMER_TICK_NS); // fill up to 1000 ns since adc-trigger (if needed)
	buffer->values_current[sample_idx] = adc_fastread(SPI_CS_EMU_ADC_PIN);
	buffer->values_voltage[sample_idx] = 0u;
	return 0u;
}

static inline uint32_t sample_hrv_ADCs(struct SampleBuffer *const buffer, const uint32_t sample_idx)
{
	__delay_cycles(1000 / TIMER_TICK_NS); // fill up to 1000 ns since adc-trigger (if needed)
	buffer->values_current[sample_idx] = adc_fastread(SPI_CS_HRV_C_ADC_PIN);
	buffer->values_voltage[sample_idx] = adc_fastread(SPI_CS_HRV_V_ADC_PIN);
	return 0u;
}


uint32_t sample(volatile struct SharedMem *const shared_mem, struct SampleBuffer *const current_buffer_far,
	    const enum ShepherdMode mode)
{
	switch (mode) // reordered to prioritize longer routines
	{
	case MODE_EMULATOR: // ~ ## ns, TODO: test timing for new revision
		return sample_emulator(shared_mem, current_buffer_far);
	case MODE_HARVESTER: // ~ ## ns
		return sample_adc_harvester(current_buffer_far, shared_mem->analog_sample_counter);
	case MODE_EMU_ADC_READ:
		return sample_emu_ADCs(current_buffer_far, shared_mem->analog_sample_counter);
	case MODE_HRV_ADC_READ:
		return sample_hrv_ADCs(current_buffer_far, shared_mem->analog_sample_counter);
	default:
		return 0u;
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
		adc_readwrite(cs_pin, REGISTER_WRITE | ADDR_REG_PWRCTL | NOT_PWRDOWN | NAP_EN);
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

// harvester-init takes 	32'800 ns ATM
// emulator-init takes
void sample_init(const volatile struct SharedMem *const shared_mem)
{
	/* Chip-Select signals are active low */
	GPIO_ON(SPI_CS_HRV_DAC_MASK | SPI_CS_HRV_C_ADC_MASK | SPI_CS_HRV_V_ADC_MASK);
	GPIO_ON(SPI_CS_EMU_DAC_MASK | SPI_CS_EMU_ADC_MASK);
	GPIO_OFF(SPI_SCLK_MASK | SPI_MOSI_MASK);

	const enum ShepherdMode mode = (enum ShepherdMode)shared_mem->shepherd_mode;
	const uint32_t dac_ch_a_voltage_raw = shared_mem->dac_auxiliary_voltage_raw & 0xFFFF;
	/* switch to set behaviour of aux-channel (dac A) */
	dac_aux_link_to_main = ((shared_mem->dac_auxiliary_voltage_raw >> 20u) & 3u) == 1u;
	dac_aux_link_to_mid = ((shared_mem->dac_auxiliary_voltage_raw >> 20u) & 3u) == 2u;

	/* deactivate hw-units when not needed, initialize the other */
	const bool_ft use_harvester = (mode == MODE_HARVESTER) || (mode == MODE_HRV_ADC_READ) || (mode == MODE_DEBUG);
	const bool_ft use_emulator = (mode == MODE_EMULATOR) || (mode == MODE_EMU_ADC_READ) || (mode == MODE_DEBUG);

	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	dac8562_init(SPI_CS_HRV_DAC_PIN, use_harvester);
	// TODO: init more efficient, can be done all same ICs at the same time (common cs_low)
	// just init-emulator takes 10.5 us, 5x DAC * 750 ns, 4x ADC x 1440 ns

	if (use_harvester)
	{
		/* after DAC-Reset the output is at Zero, fast return CH B to Max to not drain the power-source */
		/* NOTE: if harvester is not used, dac is currently shut down -> connects power source with 1 Ohm to GND */
		if (dac_aux_link_to_main)
			dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | dac_ch_a_voltage_raw);
		else
			dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_B_ADDR | DAC_MAX_VAL);
		dac_write(SPI_CS_HRV_DAC_PIN, DAC_CH_A_ADDR | dac_ch_a_voltage_raw); // TODO: write aux more often if needed
	}

	ads8691_init(SPI_CS_HRV_C_ADC_PIN, use_harvester); // TODO: when asm-spi-code would take pin-mask, the init could be done in parallel
	ads8691_init(SPI_CS_HRV_V_ADC_PIN, use_harvester);

	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	dac8562_init(SPI_CS_EMU_DAC_PIN, use_emulator);
	ads8691_init(SPI_CS_EMU_ADC_PIN, use_emulator);

	if (use_emulator)
	{
		const uint32_t address = dac_aux_link_to_main ? DAC_CH_AB_ADDR : DAC_CH_A_ADDR;
		dac_write(SPI_CS_EMU_DAC_PIN, address | dac_ch_a_voltage_raw);
		// TODO: we also need to make sure, that this fn returns voltages to same, zero or similar
		//  (init is called after sampling, but is the mode correct?)
	}

	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	if (mode == MODE_EMULATOR)
	{
		calibration_initialize(&shared_mem->calibration_settings);
		converter_initialize(&shared_mem->converter_settings);
		harvester_initialize(&shared_mem->harvester_settings);
	}
	else if (mode == MODE_HARVESTER)
	{
		calibration_initialize(&shared_mem->calibration_settings);
		harvester_initialize(&shared_mem->harvester_settings);
	}
}
