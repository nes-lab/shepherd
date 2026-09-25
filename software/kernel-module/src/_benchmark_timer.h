#include <linux/io.h> /* gpio0-access */
#include <linux/ktime.h>

/* Benchmark high-res busy-wait - RESULTS kernel 4.19:
 * - ktime_get                  99.6us   215n   463ns/call
 * - ktime_get_real             100.3us  302n   332ns/call -> current best performer (4.19.94-ti-r73)
 * - ktime_get_ns               100.2us  257n   389ns/call
 * - ktime_get_real_ns          131.5us  247n   532ns
 * - ktime_get_raw              99.3us   273n   364ns
 * - ktime_get_real_fast_ns     90.0us   308n   292ns
 * - increment-loop             825us    100k   8.25ns/iteration
 *
 * RESULTS kernel 6.12 (not verified by logic analyzer)
 * - ktime_get = 398 n / ~100us
 * - ktime_get_real = 399 n / ~100us
 * - ktime_get_ns = 399 n / ~100us
 * - ktime_get_real_ns = 398 n / ~100us
 * - ktime_get_raw = 170 n / ~100us
 * - ktime_get_real_fast_ns = 375 n / ~100us
 *
 * RESULTS kernel 6.18 (not verified by logic analyzer)
 * - ktime_get = 329 n / ~100us
 * - ktime_get_real = 320 n / ~100us
 * - ktime_get_ns = 331 n / ~100us
 * - ktime_get_real_ns = 322 n / ~100us
 * - ktime_get_raw = 330 n / ~100us
 * - ktime_get_real_fast_ns = 352 n / ~100us
 *
 * Src: https://github.com/nes-lab/shepherd/blob/Kernel510_test/software/kernel-module/src/pru_sync_control.c
 */

/* debug gpio - gpio0[22] - P8_19 - BUTTON_LED is suitable */
static volatile void __iomem *gpio0set   = NULL;
static volatile void __iomem *gpio0clear = NULL;

void                          timer_benchmark(void)
{
    uint32_t         counter;
    uint64_t         trigger_ns;
    ktime_t          trigger_kt;
    volatile int32_t counter_iv;
    int32_t          trigger_in;
    printk(KERN_INFO "shprd.k: Benchmark high-res busy-wait Variants");

    gpio0clear = ioremap(0x44E07000u + 0x190u, 4u); // BBB, GPIO0
    if (gpio0clear == NULL)
    {
        printk(KERN_ERR "shprd.k: sync-control mapping of GPIO0CLEAR failed!");
        return;
    }
    else
        printk(KERN_INFO "shprd.debug: Gpio0clear @ 0x%X virt, 0x%X phys, %d bytes",
               (uint32_t) gpio0clear, (uint32_t) (0x44E07000u + 0x190u), 4u);

    gpio0set = ioremap(0x44E07000u + 0x194u, 4u);
    if (gpio0set == NULL)
    {
        printk(KERN_ERR "shprd.k: sync-control mapping of GPIO0SET failed!");
        return;
    }
    else
        printk(KERN_INFO "shprd.debug: Gpio0set @ 0x%X virt, 0x%X phys, %d bytes",
               (uint32_t) gpio0set, (uint32_t) (0x44E07000u + 0x194u), 4u);

    counter    = 0;
    trigger_kt = ktime_get() + ns_to_ktime(100000u);
    preempt_disable();
    writel(0b1u << 22u, gpio0clear);
    while (ktime_get() < trigger_kt) { counter++; };
    writel(0b1u << 22u, gpio0set);
    preempt_enable();
    printk(KERN_INFO "shprd.k: ktime_get() = %u n / ~100us", counter);

    counter    = 0;
    trigger_kt = ktime_get_real() + ns_to_ktime(100000u);
    preempt_disable();
    writel(0b1u << 22u, gpio0clear);
    while (ktime_get_real() < trigger_kt) { counter++; };
    writel(0b1u << 22u, gpio0set);
    preempt_enable();
    printk(KERN_INFO "shprd.k: ktime_get_real() = %u n / ~100us", counter);

    counter    = 0;
    trigger_ns = ktime_get_ns() + 100000u;
    preempt_disable();
    writel(0b1u << 22u, gpio0clear);
    while (ktime_get_ns() < trigger_ns) { counter++; };
    writel(0b1u << 22u, gpio0set);
    preempt_enable();
    printk(KERN_INFO "shprd.k: ktime_get_ns() = %u n / ~100us", counter);

    counter    = 0;
    trigger_ns = ktime_get_real_ns() + 100000u;
    preempt_disable();
    writel(0b1u << 22u, gpio0clear);
    while (ktime_get_real_ns() < trigger_ns) { counter++; };
    writel(0b1u << 22u, gpio0set);
    preempt_enable();
    printk(KERN_INFO "shprd.k: ktime_get_real_ns() = %u n / ~100us", counter);

    counter    = 0;
    trigger_kt = ktime_get_raw() + ns_to_ktime(100000u);
    preempt_disable();
    writel(0b1u << 22u, gpio0clear);
    while (ktime_get_raw() < trigger_kt) { counter++; };
    writel(0b1u << 22u, gpio0set);
    preempt_enable();
    printk(KERN_INFO "shprd.k: ktime_get_raw() = %u n / ~100us", counter);

    counter    = 0;
    trigger_ns = ktime_get_real_fast_ns() + 100000u;
    preempt_disable();
    writel(0b1u << 22u, gpio0clear);
    while (ktime_get_real_fast_ns() < trigger_ns) { counter++; };
    writel(0b1u << 22u, gpio0set);
    preempt_enable();
    printk(KERN_INFO "shprd.k: ktime_get_real_fast_ns() = %u n / ~100us", counter);

    counter_iv = 0;
    trigger_in = 100000;
    preempt_disable();
    writel(0b1u << 22u, gpio0clear);
    while (counter_iv < trigger_in) { counter_iv++; };
    writel(0b1u << 22u, gpio0set);
    preempt_enable();
    printk(KERN_INFO "shprd.k: %d-increment-Loops -> measure-time", trigger_in);
}
