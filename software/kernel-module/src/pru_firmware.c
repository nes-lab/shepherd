//
//
//
#include <linux/delay.h>
#include <linux/remoteproc.h>
#include <linux/string.h>
#include <linux/types.h>

#include "pru_comm.h"
#include "pru_mem_msg_sys.h"
#include "sync_ctrl.h"

#include "pru_firmware.h"

struct shepherd_platform_data *shp_pdata = NULL;

int                            load_pru_firmware(u8 pru_num, const char *file_name)
{
    int ret = 0;

    if (shp_pdata == NULL) { return 1; }

    if (shp_pdata->rproc_prus[pru_num]->state == RPROC_RUNNING)
    {
        rproc_shutdown(shp_pdata->rproc_prus[pru_num]);
    }

    sprintf(shp_pdata->rproc_prus[pru_num]->firmware, file_name);

    if ((ret = rproc_boot(shp_pdata->rproc_prus[pru_num])))
    {
        printk(KERN_ERR "shprd.k: Couldn't boot PRU%d", pru_num);
    }
    return ret;
}

int swap_pru_firmware(const char *pru0_file_name, const char *pru1_file_name)
{
    int      ret = 0;
    const u8 pru0_default =
            (strncmp(pru0_file_name, PRU0_FW_DEFAULT, strlen(PRU0_FW_DEFAULT)) == 0);
    const u8 pru1_default =
            (strncmp(pru1_file_name, PRU1_FW_DEFAULT, strlen(PRU1_FW_DEFAULT)) == 0);

    /* pause sub-services */
    mem_msg_sys_pause();
    sync_pause();

    if (shp_pdata == NULL) { return 1; }

    /* swap firmware */
    if (strlen(pru0_file_name) > 0)
    {
        ret = load_pru_firmware(0, pru0_file_name);
        if (ret) return ret;
    }

    if (strlen(pru1_file_name) > 0)
    {
        ret = load_pru_firmware(1, pru1_file_name);
        if (ret) return ret;
    }

    /* Allow some time for the PRUs to initialize. This is critical! */
    msleep(300);

    /* restart sub-services */
    pru_comm_reset();
    mem_msg_sys_start();

    /* Initialize synchronization mechanism between PRU1 and our clock */
    if (fwncmp(0, PRU0_FW_DEFAULT) && fwncmp(1, PRU1_FW_DEFAULT)) { sync_start(); }

    return ret;
}

void read_pru0_firmware(char *file_name) { sprintf(file_name, shp_pdata->rproc_prus[0]->firmware); }

int  fwncmp(u8 pru_num, const char *file_name)
{
    if (pru_num > 1) return -1;
    return strncmp(shp_pdata->rproc_prus[pru_num]->firmware, file_name, strlen(file_name))
}
