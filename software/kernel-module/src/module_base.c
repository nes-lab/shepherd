#include <linux/delay.h>
#include <linux/errno.h>
#include <linux/init.h>
#include <linux/io.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_device.h>
#include <linux/of_irq.h>      // TODO: test
#include <linux/of_platform.h> // todo: test
#include <linux/platform_device.h>
//#include <linux/pruss.h> // todo: test
#include <linux/remoteproc.h>
#include <linux/types.h>

#include "ocmc_cache.h"
#include "pru_firmware.h"
#include "pru_mem_interface.h"
#include "pru_msg_sys.h"
#include "pru_sync_control.h"
#include "sysfs_interface.h"

#define MODULE_NAME "shepherd"
MODULE_SOFTDEP("pre: pruss");
MODULE_SOFTDEP("pre: pru_rproc");
MODULE_SOFTDEP("pre: remoteproc");

static const struct of_device_id shepherd_dt_ids[] = {{
                                                              .compatible = "nes,shepherd",
                                                      },
                                                      {/* sentinel */}};
MODULE_DEVICE_TABLE(of, shepherd_dt_ids);

/*
 * get the two prus from the pruss-device-tree-node and save the pointers for common use.
 * the pruss-device-tree-node must have a shepherd entry with a pointer to the prusses.
 */

static int shepherd_platform_data_init(struct platform_device *pdev)
{
    struct device_node *np = pdev->dev.of_node, *pruss_dn = NULL;
    struct device_node *child;
    struct rproc       *tmp_rproc;

    /*allocate mem for platform data*/
    shp_pdata = devm_kzalloc(&pdev->dev, sizeof(*shp_pdata), GFP_KERNEL);
    if (shp_pdata == NULL)
    {
        dev_err(&pdev->dev, "Unable to allocate platform data\n");
        return -1;
    }

    if (!of_match_device(shepherd_dt_ids, &pdev->dev))
    {
        pr_err("of_match_device failed\n");
        devm_kfree(&pdev->dev, shp_pdata);
        return -1;
    }

    pruss_dn = of_parse_phandle(np, "prusses", 0);
    if (!pruss_dn)
    {
        dev_err(&pdev->dev, "Unable to parse device node: prusses\n");
        devm_kfree(&pdev->dev, shp_pdata);
        return -1;
    }
    /* init values to known state */
    shp_pdata->rproc_prus[0] = NULL;
    shp_pdata->rproc_prus[1] = NULL;

    for_each_child_of_node(pruss_dn, child)
    {
        if (strncmp(child->name, "pru", 3) == 0)
        {
            tmp_rproc = rproc_get_by_phandle((phandle) child->phandle);

            if (tmp_rproc == NULL)
            {
                of_node_put(pruss_dn);
                dev_err(&pdev->dev, "Not yet able to parse %s device node\n", child->name);
                return -1;
            }

            if ((strncmp(tmp_rproc->name, "4a334000.pru", 12) == 0) &&
                (shp_pdata->rproc_prus[0] == NULL))
            {

                printk(KERN_INFO "shprd.k: Found PRU0 at phandle 0x%02X", child->phandle);
                shp_pdata->rproc_prus[0] = tmp_rproc;
            }

            else if ((strncmp(tmp_rproc->name, "4a338000.pru", 12) == 0) &&
                     (shp_pdata->rproc_prus[1] == NULL))
            {
                printk(KERN_INFO "shprd.k: Found PRU1 at phandle 0x%02X", child->phandle);
                shp_pdata->rproc_prus[1] = tmp_rproc;
            }
            else
            {
                /* not OUR handle or handle already acquired -> give it back immediately */
                rproc_put(tmp_rproc);
            }
        }
    }

    of_node_put(pruss_dn);
    return 1;
}

static int shepherd_platform_data_exit(struct platform_device *pdev)
{
    if (shp_pdata != NULL)
    {
        if (shp_pdata->rproc_prus[1] != NULL)
        {
            if (shp_pdata->rproc_prus[1]->state != RPROC_OFFLINE)
            {
                rproc_shutdown(shp_pdata->rproc_prus[1]);
                printk(KERN_INFO "shprd.k: PRU1 shut down");
            }
            rproc_put(shp_pdata->rproc_prus[1]);
            shp_pdata->rproc_prus[1] = NULL;
            printk(KERN_INFO "shprd.k: ref/handle for PRU1 was returned");
        }

        if (shp_pdata->rproc_prus[0] != NULL)
        {
            if (shp_pdata->rproc_prus[0]->state != RPROC_OFFLINE)
            {
                rproc_shutdown(shp_pdata->rproc_prus[0]);
                printk(KERN_INFO "shprd.k: PRU0 shut down");
            }
            rproc_put(shp_pdata->rproc_prus[0]);
            shp_pdata->rproc_prus[0] = NULL;
            printk(KERN_INFO "shprd.k: ref/handle for PRU0 was returned");
        }

        //devm_kfree(&pdev->dev, shp_pdata);
        //printk(KERN_INFO "shprd.k: platform-data 1 freed");
        shp_pdata = NULL;
        //pdev->dev.platform_data = NULL;
        printk(KERN_INFO "shprd.k: platform-data 2 nulled");
    }
    return 0;
}


static int shepherd_drv_probe(struct platform_device *pdev)
{
    int ret = 0;

    printk(KERN_INFO "shprd.k: found shepherd device!!!");

    if (shepherd_platform_data_init(pdev) < 0)
    {
        /*pru device are not ready yet so kernel should retry the probe function later again*/
        shepherd_platform_data_exit(pdev);
        return -EPROBE_DEFER;
    }

    /* swap FW -> also handles sub-services for PRU */
    ret = swap_pru_firmware(PRU0_FW_DEFAULT, PRU1_FW_DEFAULT);
    if (ret) goto failure_1_pru;

    /* Initialize shared memory and PRU interrupt controller */
    ret = mem_interface_init();
    if (ret) goto failure_2_memif;
    ret = msg_sys_init();
    if (ret) goto failure_3_msg;

    /* Initialize synchronization mechanism between PRU1 and our clock */
    ret = sync_init();
    if (ret) goto failure_4_sync;

    /* Set up the sysfs interface for access from userspace */
    ret = sysfs_interface_init(); // TODO: this can fail! add & eval retval
    if (ret) goto failure_5_sysfs;

    /* cache for the input buffer */
    ret = ocmc_cache_init();
    if (ret) goto failure_6_ocmc;

    return 0;

failure_6_ocmc:
    ocmc_cache_exit();
failure_5_sysfs:
    sysfs_interface_exit();
failure_4_sync:
    sync_exit();
failure_3_msg:
    msg_sys_exit();
failure_2_memif:
    mem_interface_exit();
failure_1_pru:
    shepherd_platform_data_exit(pdev);
    printk(KERN_ERR
           "shprd.k: Error during initialization of subsystems in kMod.probe -> will exit now!");
    return ret;
}

static int shepherd_drv_remove(struct platform_device *pdev)
{
    ocmc_cache_exit();
    sysfs_interface_exit();
    sync_exit();
    msg_sys_exit();
    mem_interface_exit();
    /* last active components get cleaned */
    shepherd_platform_data_exit(pdev);
    //platform_set_drvdata(pdev, NULL);
    printk(KERN_INFO "shprd.k: module exited from kernel!!!");
    return 0;
}

static struct platform_driver shepherd_driver = {
        .probe  = shepherd_drv_probe,
        .remove = shepherd_drv_remove,
        .driver =
                {
                        .name           = MODULE_NAME,
                        .owner          = THIS_MODULE,
                        .of_match_table = of_match_ptr(shepherd_dt_ids),
                },
};
/**************/

module_platform_driver(shepherd_driver);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Kai Geissdoerfer");
MODULE_DESCRIPTION("Shepherd kernel module for time synchronization and data exchange to PRUs");
MODULE_VERSION("2026.07.1");
// MODULE_ALIAS("rpmsg:rpmsg-shprd"); // TODO: is this still needed?
