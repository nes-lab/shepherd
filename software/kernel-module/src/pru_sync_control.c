#include <linux/hrtimer.h>
#include <linux/ktime.h>
#include <linux/math64.h>
#include <linux/slab.h>
//#include <time.h>

#include <asm/io.h> // as long as gpio0-hack is active

#include "pru_mem_interface.h"
#include "pru_sync_control.h"

static uint32_t sys_ts_over_timer_wrap_ns = 0;
static uint64_t ts_upcoming_ns            = 0;
static uint64_t ts_previous_ns            = 0; /* for plausibility-check */

void            reset_prev_timestamp(
                   void) // TODO: not needed anymore^, // TODO: there was this reset when a string-message came in per rpmsg
{
    ts_previous_ns = 0;
}

static enum hrtimer_restart trigger_loop_callback(struct hrtimer *timer_for_restart);
static enum hrtimer_restart sync_loop_callback(struct hrtimer *timer_for_restart);
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
struct hrtimer            sync_loop_timer;
static u8                 timers_active    = 0;

/* series of halving sleep cycles, sleep less coming slowly near a total of 100ms of sleep */
static const unsigned int timer_steps_ns[] = {20000000u, 20000000u, 20000000u, 20000000u, 10000000u,
                                              5000000u,  2000000u,  1000000u,  500000u,   200000u,
                                              100000u,   50000u,    20000u};
/* TODO: sleep 100ms - 20 us
* TODO: above halvings sum up to 98870 us */
static const size_t       timer_steps_ns_size = sizeof(timer_steps_ns) / sizeof(timer_steps_ns[0]);
//static unsigned int step_pos = 0;

static void __iomem      *gpio0set            = NULL;
static void __iomem      *gpio0clear          = NULL;


// Sync-Routine - TODO: take these from pru-sharedmem
#define BUFFER_PERIOD_NS       (100000000U) // TODO: there is already: trigger_loop_period_ns
#define ADC_SAMPLES_PER_BUFFER (10000U)
#define TIMER_TICK_NS          (5U)
#define TIMER_BASE_PERIOD      (BUFFER_PERIOD_NS / TIMER_TICK_NS)
#define SAMPLE_INTERVAL_NS     (BUFFER_PERIOD_NS / ADC_SAMPLES_PER_BUFFER)
#define SAMPLE_PERIOD          (TIMER_BASE_PERIOD / ADC_SAMPLES_PER_BUFFER)
static uint32_t     info_count = 6666; /* >6k triggers explanation-message once */
struct sync_data_s *sync_data  = NULL;
static u8           init_done  = 0;

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
    hrtimer_cancel(&sync_loop_timer);
    if (sync_data != NULL)
    {
        kfree(sync_data);
        sync_data = NULL;
    }
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
    init_done = 0;
    printk(KERN_INFO "shprd.k: pru-sync-system exited");
}

int sync_init(uint32_t timer_period_ns)
{
    if (init_done)
    {
        printk(KERN_ERR "shprd.k: pru-sync-system init requested -> can't init twice!");
        return -1;
    }

    sync_data = kmalloc(sizeof(struct sync_data_s), GFP_KERNEL);
    if (!sync_data)
    {
        printk(KERN_ERR "shprd.k: pru-sync-system kmalloc failed!");
        return -2;
    }
    sync_reset();

    gpio0clear             = ioremap(0x44E07000 + 0x190, 4);
    gpio0set               = ioremap(0x44E07000 + 0x194, 4);

    /* timer for trigger, TODO: this needs better naming, make clear what it does */
    trigger_loop_period_ns = timer_period_ns; /* 100 ms */
    trigger_loop_period_kt = ns_to_ktime(trigger_loop_period_ns);
    //printk(KERN_INFO "shprd.k: new timer_period_ns = %u", trigger_loop_period_ns);

    hrtimer_init(&trigger_loop_timer, CLOCK_REALTIME, HRTIMER_MODE_ABS_HARD);
    trigger_loop_timer.function = &trigger_loop_callback;

    /* timer for Sync-Loop */
    hrtimer_init(&sync_loop_timer, CLOCK_REALTIME, HRTIMER_MODE_ABS);
    sync_loop_timer.function = &sync_loop_callback;

    init_done                = 1;
    printk(KERN_INFO "shprd.k: pru-sync-system initialized");

    printk(KERN_INFO "shprd.k: trigger_hrtimer.hres    = %d", hrtimer_is_hres_active(&trigger_loop_timer));
    printk(KERN_INFO "shprd.k: trigger_hrtimer.is_rel  = %d", trigger_loop_timer.is_rel);
    printk(KERN_INFO "shprd.k: trigger_hrtimer.is_soft = %d", trigger_loop_timer.is_soft);
    //printk(KERN_INFO "shprd.k: trigger_hrtimer.is_hard = %d", trigger_loop_timer.is_hard); // needs kernel 5.4+

    //sync_benchmark();
    sync_start();
    return 0;
}

void sync_pause(void)
{
    if (!timers_active)
    {
        printk(KERN_ERR "shprd.k: pru-sync-system pause requested -> but wasn't running!");
        return;
    }
    timers_active = 0;
    printk(KERN_INFO "shprd.k: pru-sync-system paused");
}

void sync_start(void)
{
    uint32_t       ns_over_wrap;
    uint64_t       ns_to_next_trigger;
    /* Timestamp system clock */
    const ktime_t  ts_now_kt = ktime_get_real();
    const uint64_t ts_now_ns = ktime_to_ns(ts_now_kt);

    if (!init_done)
    {
        printk(KERN_ERR "shprd.k: pru-sync-system start requested without prior init!");
        return;
    }
    if (timers_active)
    {
        printk(KERN_ERR "shprd.k: pru-sync-system start requested -> but already running!");
        return;
    }

    sync_reset();

    div_u64_rem(ts_now_ns, trigger_loop_period_ns, &ns_over_wrap);
    if (ns_over_wrap > (trigger_loop_period_ns / 2))
    {
        /* target timer-wrap one ahead */
        ns_to_next_trigger = 2 * trigger_loop_period_ns - ns_over_wrap - ns_pre_trigger;
    }
    else
    {
        /* target next timer-wrap */
        ns_to_next_trigger = trigger_loop_period_ns - ns_over_wrap - ns_pre_trigger;
    }

    hrtimer_start(&trigger_loop_timer, ts_now_kt + ns_to_ktime(ns_to_next_trigger),
                  HRTIMER_MODE_ABS_HARD);

    hrtimer_start(&sync_loop_timer, ts_now_kt + ns_to_ktime(1000000), HRTIMER_MODE_ABS);
    printk(KERN_INFO "shprd.k: pru-sync-system started");
    timers_active = 1;
}

void sync_reset(void)
{
    sync_data->error_now       = 0;
    sync_data->error_pre       = 0;
    sync_data->error_dif       = 0;
    sync_data->error_sum       = 0;
    sync_data->clock_corr      = 0;
    sync_data->previous_period = TIMER_BASE_PERIOD;
}

enum hrtimer_restart trigger_loop_callback(struct hrtimer *timer_for_restart)
{
    ktime_t          ts_now_kt;
    uint64_t         ts_now_ns;
    static ktime_t   ts_next_kt = 0;
    ktime_t          ts_next_busy_kt = 0;
    static uint32_t  singleton = 0;

    if (!timers_active) return HRTIMER_NORESTART;

    preempt_disable();
    writel(0b1u << 22u, gpio0clear);

    /* Timestamp system clock */
    ts_now_kt = ktime_get_real();

    if ((ts_now_kt > ts_next_kt + trigger_loop_period_kt) || (ts_now_kt < ts_next_kt))
    {
        writel(0b1u << 22u, gpio0set);
        preempt_enable();

        /* out of bounds -> reset timer */
        if (singleton) printk(KERN_ERR "shprd.k: reset sync-trigger!");
        else singleton = 1u;

        ts_now_ns = ktime_get_real_ns();
        div_u64_rem(ts_now_ns, trigger_loop_period_ns, &sys_ts_over_timer_wrap_ns);
        ts_upcoming_ns = ts_now_ns + trigger_loop_period_ns - sys_ts_over_timer_wrap_ns;
        ts_next_kt = ns_to_ktime(ts_upcoming_ns);
        hrtimer_forward(timer_for_restart, ts_next_kt, 0);

        /* update global vars */
        sys_ts_over_timer_wrap_ns = 0u; /* invalidate this measurement */

        return HRTIMER_RESTART;
    }

    if (1)
    {
        /* high-res busy-wait, ~300ns resolution */
        ts_next_busy_kt = ts_next_kt + ns_to_ktime(40000u);
        while (ts_now_kt<ts_next_busy_kt)  ts_now_kt = ktime_get_real();
    }

    writel(0b1u << 22u, gpio0set);
    /* Raise Interrupt on PRU, telling it to timestamp IEP */
    mem_interface_trigger(HOST_PRU_EVT_TIMESTAMP);
    preempt_enable();

    /*
     * Get distance of system clock from timer wrap.
     * Is negative, when interrupt happened before wrap, positive when after
     */
    ts_now_ns = ktime_to_ns(ts_now_kt);
    /* update global vars */
    div_u64_rem(ts_now_ns, trigger_loop_period_ns, &sys_ts_over_timer_wrap_ns);

    // TODO: minor optimization
    //  - write ts_upcoming_ns directly into shared mem, as well as the other values in sync_loop
    //  - the reply-message is not needed anymore (current pru-code has nothing to calculate beforehand and would just use prev values if no new message arrives
    ts_upcoming_ns += trigger_loop_period_ns;
    ts_next_kt = ns_to_ktime(ts_upcoming_ns);
    hrtimer_forward(timer_for_restart, ts_next_kt, 0);

    return HRTIMER_RESTART;
}

/* Handler for sync-requests from PRU1 */
enum hrtimer_restart sync_loop_callback(struct hrtimer *timer_for_restart)
{
    struct ProtoMsg       sync_rqst;
    struct SyncMsg        sync_reply;
    static uint64_t       ts_last_error_ns = 0;
    static const uint64_t quiet_time_ns    = 10000000000; // 10 s
    static unsigned int   step_pos         = 0;
    /* Timestamp system clock */
    const ktime_t         ts_now_kt        = ktime_get_real();
    const uint64_t        ts_now_ns        = ktime_to_ns(ts_now_kt);

    if (!timers_active) return HRTIMER_NORESTART;

    if (pru1_comm_receive_sync_request(&sync_rqst))
    {
        sync_loop(&sync_reply, &sync_rqst);

        if (!pru1_comm_send_sync_reply(&sync_reply))
        {
            /* Error occurs if PRU was not able to handle previous message in time */
            printk(KERN_WARNING "shprd.k: Send_SyncResponse -> back-pressure / did "
                                "overwrite old msg");
        }

        /* resetting to the longest sleep period */
        step_pos = 0;
    }
    else if ((ts_last_error_ns + quiet_time_ns < ts_now_ns) &&
             (ts_previous_ns + 2 * trigger_loop_period_ns < ts_now_ns) && (ts_previous_ns > 0))
    {
        // TODO: not working as expected, this should alarm when PRUs are offline
        ts_last_error_ns = ts_now_ns;
        printk(KERN_ERR "shprd.k: Faulty behavior - PRU did not answer to "
                        "trigger-request in time!");
    }
    /* variable sleep cycle */
    hrtimer_forward(timer_for_restart, ts_now_kt + ns_to_ktime(timer_steps_ns[step_pos]), 0);
    if (step_pos < timer_steps_ns_size - 1) step_pos++;

    return HRTIMER_RESTART;
}


int sync_loop(struct SyncMsg *const sync_reply, const struct ProtoMsg *const sync_rqst)
{
    uint32_t iep_ts_over_timer_wrap_ns;
    uint64_t ns_per_tick_n30; /* n30 means a fixed point shift left by 30 bits */

    /*
     * Based on the previous IEP timer period and the nominal timer period
     * we can estimate the real nanoseconds passing per tick
     * We operate on fixed point arithmetic OPs by shifting by 30 bit
     */
    ns_per_tick_n30 =
            div_u64(((uint64_t) trigger_loop_period_ns << 30u), sync_data->previous_period);

    /* Get distance of IEP clock at interrupt from last timer wrap */
    if (sys_ts_over_timer_wrap_ns > 0u)
    {
        iep_ts_over_timer_wrap_ns =
                (uint32_t) ((((uint64_t) sync_rqst->value[0]) * ns_per_tick_n30) >> 30u);
    }
    else
    {
        /* (also) invalidate this measurement */
        iep_ts_over_timer_wrap_ns = 0u;
    }

    /* Difference between system clock and IEP clock phase */
    sync_data->error_pre = sync_data->error_now; // TODO: new D (of PID) is not in sysfs yet
    sync_data->error_now =
            (int64_t) iep_ts_over_timer_wrap_ns - (int64_t) sys_ts_over_timer_wrap_ns;
    sync_data->error_dif = sync_data->error_now - sync_data->error_pre;
    if (sync_data->error_now < -(int64_t) (trigger_loop_period_ns / 2))
    {
        /* Currently the correction is (almost) always headed in one direction
         * - the pre-trigger @ - 1 ms is the "almost" (1 % chance for the other direction)
         * - lets correct the imbalance to 50/50
         */
        sync_data->error_now += trigger_loop_period_ns;
    }
    sync_data->error_sum += sync_data->error_now;
    // integral should be behind controller, because current P-value is twice in calculation

    /* This is the actual PI controller equation
     * NOTE1: unit of clock_corr in pru is ticks, but input is based on nanosec
     * NOTE2: traces show, that quantization noise could be a problem. example: K-value of 127, divided by 128 will still be 0, ringing is around ~ +-150
     * previous parameters were:    P=1/32, I=1/128, correction settled at ~1340 with values from 1321 to 1359
     * current parameters:          P=1/100,I=1/300, correction settled at ~1332 with values from 1330 to 1335
     * */
    sync_data->clock_corr =
            (int32_t) (div_s64(sync_data->error_now, 128) + div_s64(sync_data->error_sum, 256));
    /* 0.4 % -> ~12s for phase lock */
    if (sync_data->clock_corr > +80000) sync_data->clock_corr = +80000;
    if (sync_data->clock_corr < -80000) sync_data->clock_corr = -80000;

    /* determine corrected loop_ticks for next buffer_block */
    sync_reply->type                 = MSG_SYNC;
    sync_reply->buffer_block_period  = TIMER_BASE_PERIOD + sync_data->clock_corr;
    sync_data->previous_period       = sync_reply->buffer_block_period;
    sync_reply->analog_sample_period = (sync_reply->buffer_block_period / ADC_SAMPLES_PER_BUFFER);
    sync_reply->compensation_steps   = sync_reply->buffer_block_period -
                                     (ADC_SAMPLES_PER_BUFFER * sync_reply->analog_sample_period);

    if (((sync_data->error_now > 500) || (sync_data->error_now < -500)) && (++info_count >= 100))
    {
        /* val = 200 prints every 20s when enabled */
        printk(KERN_INFO "shprd.sync: period=%u, n_comp=%u, er_pid=%lld/%lld/%lld, "
                         "ns_iep=%u, ns_sys=%u",
               sync_reply->analog_sample_period, // = upper part of buffer_block_period
               sync_reply->compensation_steps,   // = lower part of buffer_block_period
               sync_data->error_now, sync_data->error_sum, sync_data->error_dif,
               iep_ts_over_timer_wrap_ns, sys_ts_over_timer_wrap_ns);
        if (info_count > 6600)
            printk(KERN_INFO "shprd.sync: NOTE - previous message is shown every 10 s when "
                             "sync-error exceeds a threshold (normal mainly during startup)");
        info_count = 0;
    }

    /* plausibility-check, in case the sync-algo produces jumps */
    if (ts_previous_ns > 0)
    {
        int64_t diff_timestamp_ms = div_s64((int64_t) ts_upcoming_ns - ts_previous_ns, 1000000u);
        if (diff_timestamp_ms < 0)
            printk(KERN_ERR "shprd.k: backwards timestamp-jump detected (sync-loop, %lld ms)",
                   diff_timestamp_ms);
        else if (diff_timestamp_ms < 95)
            printk(KERN_ERR "shprd.k: too small timestamp-jump detected (sync-loop, %lld ms)",
                   diff_timestamp_ms);
        else if (diff_timestamp_ms > 105)
            printk(KERN_ERR "shprd.k: forwards timestamp-jump detected (sync-loop, %lld ms)",
                   diff_timestamp_ms);
        else if (ts_upcoming_ns == 0)
            printk(KERN_ERR "shprd.k: zero timestamp detected (sync-loop)");
    }
    ts_previous_ns                = ts_upcoming_ns;
    sync_reply->next_timestamp_ns = ts_upcoming_ns;

    if ((sync_reply->buffer_block_period > TIMER_BASE_PERIOD + 80000) ||
        (sync_reply->buffer_block_period < TIMER_BASE_PERIOD - 80000))
        printk(KERN_ERR "shprd.k: buffer_block_period out of limits (%u instead of ~20M)",
               sync_reply->buffer_block_period);
    if ((sync_reply->analog_sample_period > SAMPLE_PERIOD + 10) ||
        (sync_reply->analog_sample_period < SAMPLE_PERIOD - 10))
        printk(KERN_ERR "shprd.k: analog_sample_period out of limits (%u instead of ~2000)",
               sync_reply->analog_sample_period);

    return 0;
}
