#include <linux/init.h>
#include <linux/module.h>
#include <linux/types.h>

#include "pru_sync_control.h"

static int __init shepherd_init(void)
{
    printk(KERN_INFO "shprd.k: found shepherd device!!!");
    sync_init(100000000);
    return 0;
}

static void __exit shepherd_exit(void)
{
    sync_exit();
    printk(KERN_INFO "shprd.k: module exited from kernel!!!");
}

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Kai Geissdoerfer");
MODULE_DESCRIPTION("Shepherd kernel module for time synchronization and data exchange to PRUs");
MODULE_VERSION("0.7.1");

module_init(shepherd_init);
module_exit(shepherd_exit);
