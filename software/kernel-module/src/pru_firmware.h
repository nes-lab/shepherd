#ifndef KERNELMODULE_PRU_FIRMWARE_H
#define KERNELMODULE_PRU_FIRMWARE_H

struct shepherd_platform_data
{
    struct rproc *rproc_prus[2];
};

extern struct shepherd_platform_data *shp_pdata;

int                                   load_pru_firmware(u8 pru_num, const char *file_name);

int swap_pru_firmware(const char *pru0_file_name, const char *pru1_file_name);

#endif //KERNELMODULE_PRU_FIRMWARE_H
