#ifndef PRU_FIRMWARE_PRU0_SHEPHERD_FW_CAL_CONVERTER_H
#define PRU_FIRMWARE_PRU0_SHEPHERD_FW_CAL_CONVERTER_H

#include "commons.h"

void calibration_struct_init(volatile struct CalibrationConfig *);
void calibration_initialize(const volatile struct CalibrationConfig *);

inline uint32_t cal_conv_adc_raw_to_nA(uint32_t current_raw);
inline uint32_t cal_conv_uV_to_dac_raw(uint32_t voltage_uV);

#endif //PRU_FIRMWARE_PRU0_SHEPHERD_FW_CAL_CONVERTER_H
