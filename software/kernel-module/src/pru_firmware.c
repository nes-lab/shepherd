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

    /* halt PRUs */
    // NOTE: code is intertwined for simultaneous startup and clean states
    if (shp_pdata->rproc_prus[0]->state == RPROC_RUNNING)
    {
        rproc_shutdown(shp_pdata->rproc_prus[0]);
    }
    if (shp_pdata->rproc_prus[1]->state == RPROC_RUNNING)
    {
        rproc_shutdown(shp_pdata->rproc_prus[1]);
    }

    /* swap firmware (only reboot if no name is supplied) */
    if (strlen(pru0_file_name) > 0) { sprintf(shp_pdata->rproc_prus[0]->firmware, pru0_file_name); }
    if (strlen(pru1_file_name) > 0) { sprintf(shp_pdata->rproc_prus[1]->firmware, pru1_file_name); }

    /* (re)start PRUs */
    if ((ret = rproc_boot(shp_pdata->rproc_prus[0])))
    {
        printk(KERN_ERR "shprd.k: Couldn't boot PRU0");
        return ret;
    }
    if ((ret = rproc_boot(shp_pdata->rproc_prus[1])))
    {
        printk(KERN_ERR "shprd.k: Couldn't boot PRU1");
        return ret;
    }

    /* Allow some time for the PRUs to initialize. This is critical!
	   - 300 ms worked fine
	   - logic analyzer shows that 55 ms should suffice (time between pru-bootups)
	   - reduce 300 to 100 ms (for testing)
		 - 300 ms sleep causes pru1 to wait for 400 ms for sync-reset
		 - 100 ms sleep reduces busy wait to 200 ms (and also directly speeds up reloading the kMod)
		 - 50 ms sleep -> 154 ms busy wait
		 - 10 ms sleep -> 114 ms busy wait, TODO: observe stability
	*/
    msleep(10);

    if (init_done)
    {
        /* restart sub-services */
        mem_interface_reset();
        msg_sys_start();

        /* Initialize synchronization mechanism between PRU1 and our clock */
        //if ((fwncmp(0, PRU0_FW_DEFAULT) == 0) && (fwncmp(1, PRU1_FW_DEFAULT) == 0))
        if ((fwncmp(0, PRU0_FW_EMU) == 0) || (fwncmp(0, PRU0_FW_HRV) == 0)) { sync_start(); }
        else printk(KERN_INFO "shprd.k: pru-sync-system NOT (re)started (only for shepherd-fw)");
    }
    init_done = 1;
    return ret;
}

void read_pru_firmware(u8 pru_num, char *file_name)
{ sprintf(file_name, shp_pdata->rproc_prus[pru_num]->firmware); }

int fwncmp(u8 pru_num, const char *file_name)
{
    if (pru_num > 1) return -1;
    return strncmp(shp_pdata->rproc_prus[pru_num]->firmware, file_name, strlen(file_name));
}
