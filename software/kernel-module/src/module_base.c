#include <linux/init.h>             /* Needed for __init and __exit macros. */
#include <linux/module.h>           /* Needed by all kernel modules */
#include <linux/kernel.h>           /* Needed for loglevels (KERN_WARNING, KERN_EMERG, KERN_INFO, etc.) */
#include <linux/types.h>
#include <linux/slab.h>             /* kmalloc */

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Kai Geissdoerfer");
MODULE_DESCRIPTION("Shepherd kernel module for time synchronization and data exchange to PRUs");
MODULE_VERSION("0.7.1");

#include "pru_sync_control.h"

static int __init shepherd_init(void)
{
    printk(KERN_INFO "shprd.k: init shepherd module!!!");
    sync_init(100000000u);
    return 0;
}

static void __exit shepherd_exit(void)
{
    sync_exit();
    printk(KERN_INFO "shprd.k: exited shepherd module!!!");
}

module_init(shepherd_init);
module_exit(shepherd_exit);
