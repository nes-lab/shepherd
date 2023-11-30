#include <linux/init.h>
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/types.h>

#include "pru_sync_control.h"

#define MODULE_NAME "shepherd"

//static const struct of_device_id shepherd_dt_ids[] = {{
//                                                              .compatible = "nes,shepherd",
//                                                      },
//                                                      {/* sentinel */}};
//MODULE_DEVICE_TABLE(of, shepherd_dt_ids);

static int shepherd_drv_probe(struct platform_device *pdev)
{
    printk(KERN_INFO "shprd.k: found shepherd device!!!");

    /* Initialize synchronization mechanism between PRU1 and our clock */
    sync_init(100000000);

    return 0;
}

static int shepherd_drv_remove(struct platform_device *pdev)
{
    sync_exit();

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
                        //.of_match_table = of_match_ptr(shepherd_dt_ids),
                },
};
/**************/

module_platform_driver(shepherd_driver);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Kai Geissdoerfer");
MODULE_DESCRIPTION("Shepherd kernel module for time synchronization and data exchange to PRUs");
MODULE_VERSION("0.7.1");

// MODULE_ALIAS("rpmsg:rpmsg-shprd"); // TODO: is this still needed?
