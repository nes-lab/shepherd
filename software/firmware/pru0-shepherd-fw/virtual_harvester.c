#include <stdint.h>
#include "virtual_harvester.h"

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
