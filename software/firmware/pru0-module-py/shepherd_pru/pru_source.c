#include "commons.h"
#include "calibration.h"
#include "virtual_converter.h"
#include "virtual_harvester.h"
#include <stdint.h>

/*
ripped out parts from sample_emulator() in sampling.c
*/
uint32_t vsrc_iterate_sampling(uint32_t input_voltage_uV, uint32_t input_current_nA, const uint32_t current_adc_raw)
{
    static struct SharedMem shared_mem;

    sample_ivcurve_harvester(&input_voltage_uV, &input_current_nA);

    converter_calc_inp_power(input_voltage_uV, input_current_nA);

    converter_calc_out_power(current_adc_raw);

    converter_update_cap_storage();

    converter_update_states_and_output(&shared_mem);

    return get_V_output_uV();
}