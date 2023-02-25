//
//
//
#include <linux/delay.h>
#include <linux/remoteproc.h>
#include <linux/string.h>
#include <linux/types.h>

#include "pru_mem_interface.h"
#include "pru_msg_sys.h"
#include "pru_sync_control.h"

#include "pru_firmware.h"

struct shepherd_platform_data *shp_pdata = NULL;

int                            load_pru_firmware(u8 pru_num, const char *file_name)
{
    int ret = 0;

    if (shp_pdata == NULL) return 1;
    if (pru_num > 1) return 2;

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
    int       ret       = 0;
    static u8 init_done = 0;

    /* pause sub-services */
    if (init_done)
    {
        msg_sys_pause();
        sync_pause();
    }

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

    if (init_done)
    {
        /* restart sub-services */
        mem_interface_reset();
        msg_sys_start();

        /* Initialize synchronization mechanism between PRU1 and our clock */
        if ((fwncmp(0, PRU0_FW_DEFAULT) == 0) && (fwncmp(1, PRU1_FW_DEFAULT) == 0))
        {
            sync_start();
        }
        else printk(KERN_INFO "shprd.k: pru-sync-system NOT (re)started (only for shepherd-fw)");
    }
    init_done = 1;
    return ret;
}

void read_pru_firmware(u8 pru_num, char *file_name)
{
    sprintf(file_name, shp_pdata->rproc_prus[pru_num]->firmware);
}

int fwncmp(u8 pru_num, const char *file_name)
{
    if (pru_num > 1) return -1;
    return strncmp(shp_pdata->rproc_prus[pru_num]->firmware, file_name, strlen(file_name));
}
