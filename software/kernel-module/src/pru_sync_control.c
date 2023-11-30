#include <linux/hrtimer.h>
#include <linux/ktime.h>
#include <linux/math64.h>
#include <linux/slab.h>

#include <asm/io.h> // as long as gpio0-hack is active

static uint32_t sys_ts_over_timer_wrap_ns = 0;

static enum hrtimer_restart trigger_loop_callback(struct hrtimer *timer_for_restart);

static uint32_t       trigger_loop_period_ns = 100000000u; /* just initial value to avoid div0 */
static ktime_t        trigger_loop_period_kt = 100000000u;

/*
* add pre-trigger, because design previously aimed directly for busy pru_timer_wrap
* (50% chance that pru takes a less meaningful counter-reading after wrap)
* 1 ms + 5 us, this should be enough time for the ping-pong-messaging to complete before timer_wrap
*/
static const uint32_t     ns_pre_trigger         = 1005000u;

/* Timer to trigger fast sync_loop */
struct hrtimer            trigger_loop_timer;

static void __iomem      *gpio0set            = NULL;
static void __iomem      *gpio0clear          = NULL;

void                sync_benchmark(void)
{
    uint32_t         counter;
    uint64_t         trigger_ns;
    ktime_t          trigger_kt;
    volatile int32_t counter_iv;
    int32_t          trigger_in;
    printk(KERN_INFO "shprd.k: Benchmark high-res busy-wait Variants");
    /* Benchmark high-res busy-wait - RESULTS:
     * - ktime_get                  99.6us   215n   463ns/call
     * - ktime_get_real             100.3us  302n   332ns/call -> current best performer (4.19.94-ti-r73)
     * - ktime_get_ns               100.2us  257n   389ns/call
     * - ktime_get_real_ns          131.5us  247n   532ns
     * - ktime_get_raw              99.3us   273n   364ns
     * - ktime_get_real_fast_ns     90.0us   308n   292ns
     * - increment-loop             825us    100k   8.25ns/iteration
     */
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


void sync_exit(void)
{
    hrtimer_cancel(&trigger_loop_timer);

    if (gpio0clear != NULL)
    {
        iounmap(gpio0clear);
        gpio0clear = NULL;
    }
    if (gpio0set != NULL)
    {
        iounmap(gpio0set);
        gpio0set = NULL;
    }
    printk(KERN_INFO "shprd.k: pru-sync-system exited");
}

int sync_init(uint32_t timer_period_ns)
{
    const ktime_t  ts_now_kt = ktime_get_real();
    uint64_t       ts_now_ns = ktime_to_ns(ts_now_kt);
    uint64_t         ns_to_next_trigger;

    div_u64_rem(ts_now_ns, trigger_loop_period_ns, &sys_ts_over_timer_wrap_ns);
    ns_to_next_trigger = trigger_loop_period_ns - sys_ts_over_timer_wrap_ns - ns_pre_trigger;

    gpio0clear             = ioremap(0x44E07000 + 0x190, 4);
    gpio0set               = ioremap(0x44E07000 + 0x194, 4);

    /* timer for trigger, TODO: this needs better naming, make clear what it does */
    trigger_loop_period_ns = timer_period_ns; /* 100 ms */
    trigger_loop_period_kt = ns_to_ktime(trigger_loop_period_ns);

    hrtimer_init(&trigger_loop_timer, CLOCK_REALTIME, HRTIMER_MODE_ABS);
    trigger_loop_timer.function = &trigger_loop_callback;
    // TODO: there is a .hrtimer_is_hres_enabled() and .hrtimer_switch_to_hres()
    printk(KERN_INFO "shprd.k: pru-sync-system initialized");

    //printk(KERN_INFO "shprd.k: hres-mode: %d -> turning on now", hrtimer_is_hres_enabled());
    //hrtimer_switch_to_hres();
    //printk(KERN_INFO "shprd.k: hres-mode: %d", hrtimer_is_hres_enabled());
    //printk(KERN_INFO "shprd.k: hres-mode: %d", hrtimer_hres_active());
    printk(KERN_INFO "shprd.k: hres-mode: %d", hrtimer_is_hres_active(&trigger_loop_timer));


    sync_benchmark();

    hrtimer_start(&trigger_loop_timer, ts_now_kt + ns_to_ktime(ns_to_next_trigger),
                  HRTIMER_MODE_ABS);
    // TODO: try: HRTIMER_MODE_ABS_HARD, HRTIMER_MODE_ABS_PINNED_HARD

    printk(KERN_INFO "shprd.k: timer.is_rel = %d", trigger_loop_timer.is_rel);
    printk(KERN_INFO "shprd.k: timer.is_soft = %d", trigger_loop_timer.is_soft);
    printk(KERN_INFO "shprd.k: timer.is_hard = %d", trigger_loop_timer.is_hard);

    printk(KERN_INFO "shprd.k: pru-sync-system started");
    return 0;
}


enum hrtimer_restart trigger_loop_callback(struct hrtimer *timer_for_restart)
{
    ktime_t          ts_now_kt;
    uint64_t         ts_now_ns;
    uint64_t         ns_to_next_trigger;
    static ktime_t   ts_next_kt = 0;
    ktime_t          ts_next_busy_kt = 0;

    preempt_disable();
    writel(0b1u << 22u, gpio0clear);

    /* Timestamp system clock */
    ts_now_kt = ktime_get_real();

    if ((ts_now_kt > ts_next_kt + trigger_loop_period_kt) || (ts_now_kt < ts_next_kt))
    {
        writel(0b1u << 22u, gpio0set);
        preempt_enable();
        /* out of bounds -> reset timer */
        printk(KERN_ERR "shprd.k: reset sync-trigger!");

        ts_now_ns = ktime_to_ns(ts_now_kt);
        div_u64_rem(ts_now_ns, trigger_loop_period_ns, &sys_ts_over_timer_wrap_ns);
        ns_to_next_trigger = trigger_loop_period_ns - sys_ts_over_timer_wrap_ns - ns_pre_trigger;

        ts_next_kt = ts_now_kt + ns_to_ktime(ns_to_next_trigger);
        hrtimer_forward(timer_for_restart, ts_next_kt, 0);

        /* update global vars */
        sys_ts_over_timer_wrap_ns = 0u; /* invalidate this measurement */

        return HRTIMER_RESTART;
    }

    if (1)
    {
        /* high-res busy-wait */
        ts_next_busy_kt = ts_next_kt + ns_to_ktime(40000u);
        /* Coarse Loop, ~300ns resolution */
        while (ts_now_kt<ts_next_busy_kt)
        {
            ts_now_kt = ktime_get_real();
        };
    }

    writel(0b1u << 22u, gpio0set);
    preempt_enable();

    /*
     * Get distance of system clock from timer wrap.
     * Is negative, when interrupt happened before wrap, positive when after
     */
    ts_now_ns = ktime_to_ns(ts_now_kt);
    /* update global vars */
    div_u64_rem(ts_now_ns, trigger_loop_period_ns, &sys_ts_over_timer_wrap_ns);
    ns_to_next_trigger =
            2 * trigger_loop_period_ns - sys_ts_over_timer_wrap_ns - ns_pre_trigger;

    ts_next_kt = ts_now_kt + ns_to_ktime(ns_to_next_trigger);
    hrtimer_forward(timer_for_restart, ts_next_kt, 0);

    return HRTIMER_RESTART;
}
