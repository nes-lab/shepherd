#include "calibration.h"
#include "commons.h"
#include "shared_mem.h"
#include "virtual_converter.h"
#include "virtual_harvester.h"
#include <stdint.h>

volatile struct SharedMem shared_mem;

void msgsys_send_status(enum MsgType type, const uint32_t value1, const uint32_t value2)
{
    // just a mockup to avoid including more sources -> harvester uses this FN
    if (type == MSG_NONE)
    {
        shared_mem.canary1 = value1;
        shared_mem.canary2 = value2;
    }
}

void set_harvester_config(const volatile struct HarvesterConfig *const config)
{
    shared_mem.harvester_settings = *config;
}

void set_storage_config(const volatile struct StorageConfig *const config)
{
    shared_mem.storage_settings = *config;
}

void set_calibration_config(const volatile struct CalibrationConfig *const config)
{
    shared_mem.calibration_settings = *config;
}

void set_converter_config(const volatile struct ConverterConfig *const config)
{
    shared_mem.converter_settings = *config;
}

uint8_ft get_vsource_power_good_pins_state(void)
{
    return shared_mem.vsource_power_good_pins_state;
}

bool_ft  get_vsource_skip_gpio_logging(void) { return shared_mem.vsource_skip_gpio_logging; }

/*
ripped out parts from sample_emulator() in sampling.c
*/
uint32_t vsrc_iterate_sampling(uint32_t input_voltage_uV, uint32_t input_current_nA,
                               const uint32_t current_adc_raw)
{
    sample_ivcurve_harvester(&input_voltage_uV, &input_current_nA);

    converter_calc_inp_power(input_voltage_uV, input_current_nA);

    converter_calc_out_power(current_adc_raw);

    converter_update_storage();

    converter_update_states_and_output();

    /* feedback path - important for boost-less circuits */
    if (feedback_to_hrv) { voltage_set_uV = V_input_request_uV; }

    return get_V_output_uV();
}
