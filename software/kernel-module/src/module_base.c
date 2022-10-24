#include <asm/io.h>
#include <linux/delay.h>
#include <linux/errno.h>
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_device.h>
#include <linux/platform_device.h>
#include <linux/remoteproc.h>
#include <linux/types.h>

#include "pru_firmware.h"
#include "pru_comm.h"
#include "pru_mem_msg_sys.h"
#include "sync_ctrl.h"
#include "sysfs_interface.h"

#define MODULE_NAME "shepherd"
MODULE_SOFTDEP("pre: pruss");
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

static struct shepherd_platform_data *get_shepherd_platform_data(struct platform_device *pdev)
{
    struct device_node            *np = pdev->dev.of_node, *pruss_dn = NULL;
    struct device_node            *child;
    struct rproc                  *tmp_rproc;
    struct shepherd_platform_data *pdata;

    /*allocate mem for platform data*/
    pdata = devm_kzalloc(&pdev->dev, sizeof(*pdata), GFP_KERNEL);
    if (!pdata)
    {
        dev_err(&pdev->dev, "Unable to allocate platform data\n");
        return NULL;
    }

    if (!of_match_device(shepherd_dt_ids, &pdev->dev))
    {
        pr_err("of_match_device failed\n");
        devm_kfree(&pdev->dev, pdata);
        return NULL;
    }

    pruss_dn = of_parse_phandle(np, "prusses", 0);
    if (!pruss_dn)
    {
        dev_err(&pdev->dev, "Unable to parse device node: prusses\n");
        devm_kfree(&pdev->dev, pdata);
        return NULL;
    }

    for_each_child_of_node(pruss_dn, child)
    {
        if (strncmp(child->name, "pru", 3) == 0)
        {
            tmp_rproc = rproc_get_by_phandle((phandle) child->phandle);

            if (tmp_rproc == NULL)
            {
                of_node_put(pruss_dn);
                dev_err(&pdev->dev, "Unable to parse device node: %s \n", child->name);
                devm_kfree(&pdev->dev, pdata);
                return NULL;
            }

            if (strncmp(tmp_rproc->name, "4a334000.pru", 12) == 0)
            {
                printk(KERN_INFO "shprd.k: Found PRU0 at phandle 0x%02X", child->phandle);

                pdata->rproc_prus[0] = tmp_rproc;
            }

            else if (strncmp(tmp_rproc->name, "4a338000.pru", 12) == 0)
            {
                printk(KERN_INFO "shprd.k: Found PRU1 at phandle 0x%02X", child->phandle);

                pdata->rproc_prus[1] = tmp_rproc;
            }
        }
    }

    of_node_put(pruss_dn);
    remember_shepherd_platform_data(pdata);
    return pdata;
}

static int shepherd_drv_probe(struct platform_device *pdev)
{
    int  ret = 0;

    printk(KERN_INFO "shprd.k: found shepherd device!!!");

    get_shepherd_platform_data(pdev);

    /* swap also handles sub-services for PRU */
    ret = swap_pru_firmware(PRU0_FW_DEFAULT, PRU1_FW_DEFAULT);
    if (ret) return ret;

    /* Set up the sysfs interface for access from userspace */
    sysfs_interface_init();

    return ret;
}

static int shepherd_drv_remove(struct platform_device *pdev)
{
    struct shepherd_platform_data *pdata;

    pdata = pdev->dev.platform_data;
    sysfs_interface_exit();
    pru_comm_exit();
    mem_msg_sys_exit();
    sync_exit();

    if (pdata != NULL)
    {
        rproc_shutdown(pdata->rproc_prus[0]);
        rproc_put(pdata->rproc_prus[0]);
        rproc_shutdown(pdata->rproc_prus[1]);
        rproc_put(pdata->rproc_prus[1]);
        devm_kfree(&pdev->dev, pdev->dev.platform_data);
        pdev->dev.platform_data = NULL;
    }

    platform_set_drvdata(pdev, NULL);
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
MODULE_VERSION("0.4.3");
// MODULE_ALIAS("rpmsg:rpmsg-shprd"); // TODO: is this still needed?
