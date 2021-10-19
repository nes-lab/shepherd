#include <stdint.h>
#include "virtual_harvester.h"

static const volatile struct VirtHarvester_Config * vha_cfg;
static const volatile struct Calibration_Config * cal_cfg;

void harvest_struct_init_testable(volatile struct VirtHarvester_Config *const config)
{
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

void harvest_initialize(const volatile struct VirtHarvester_Config *const config, const volatile struct Calibration_Config *const cal)
{
	vha_cfg = config;
	cal_cfg = cal;

}


void harvest()
{
	// TODO: guide in sub-harvester here, based on algo-value

}
