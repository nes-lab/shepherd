#include <linux/hrtimer.h>
#include <linux/ktime.h>
#include <linux/math64.h>
#include <linux/slab.h>

#include <asm/io.h>  // as long as gpio0-hack is active

#include "pru_mem_interface.h"
#include "pru_sync_control.h"

static uint32_t sys_ts_over_timer_wrap_ns = 0;
static uint64_t next_timestamp_ns         = 0;
static uint64_t prev_timestamp_ns         = 0; /* for plausibility-check */

void            reset_prev_timestamp(
                   void) // TODO: not needed anymore^, // TODO: there was this reset when a string-message came in per rpmsg
{
    prev_timestamp_ns = 0;
}

static enum hrtimer_restart trigger_loop_callback(struct hrtimer *timer_for_restart);
static enum hrtimer_restart sync_loop_callback(struct hrtimer *timer_for_restart);
static uint32_t           trigger_loop_period_ns = 100000000; /* just initial value to avoid div0 */
/*
* add pre-trigger, because design previously aimed directly for busy pru_timer_wrap
* (50% chance that pru takes a less meaningful counter-reading after wrap)
* 1 ms + 5 us, this should be enough time for the ping-pong-messaging to complete before timer_wrap
*/
static const uint32_t     ns_pre_trigger         = 1005000;

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

static void __iomem        *gpio0set         = NULL;
static void __iomem        *gpio0clear       = NULL;


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

void                sync_exit(void)
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

    gpio0clear = ioremap(0x44E07000 + 0x190, 4);
    gpio0set = ioremap(0x44E07000 + 0x194, 4);

    /* timer for trigger, TODO: this needs better naming, make clear what it does */
    trigger_loop_period_ns = timer_period_ns; /* 100 ms */
    //printk(KERN_INFO "shprd.k: new timer_period_ns = %u", trigger_loop_period_ns);

    hrtimer_init(&trigger_loop_timer, CLOCK_REALTIME, HRTIMER_MODE_ABS);
    trigger_loop_timer.function = &trigger_loop_callback;

    /* timer for Sync-Loop */
    hrtimer_init(&sync_loop_timer, CLOCK_REALTIME, HRTIMER_MODE_ABS);
    sync_loop_timer.function = &sync_loop_callback;
    // TODO: there is a .hrtimer_is_hres_enabled() and .hrtimer_switch_to_hres()

    init_done                = 1;
    printk(KERN_INFO "shprd.k: pru-sync-system initialized");

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
    uint64_t       ns_now_until_trigger;
    /* Timestamp system clock */
    const uint64_t now_ns_system = ktime_get_real_ns();

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

    div_u64_rem(now_ns_system, trigger_loop_period_ns, &ns_over_wrap);
    if (ns_over_wrap > (trigger_loop_period_ns / 2))
    {
        /* target timer-wrap one ahead */
        ns_now_until_trigger = 2 * trigger_loop_period_ns - ns_over_wrap - ns_pre_trigger;
    }
    else
    {
        /* target next timer-wrap */
        ns_now_until_trigger = trigger_loop_period_ns - ns_over_wrap - ns_pre_trigger;
    }

    hrtimer_start(&trigger_loop_timer, ns_to_ktime(now_ns_system + ns_now_until_trigger),
                  HRTIMER_MODE_ABS);

    hrtimer_start(&sync_loop_timer, ns_to_ktime(now_ns_system + 1000000), HRTIMER_MODE_ABS);
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
    ktime_t         kt_now;
    uint64_t        ts_now_system_ns;
    uint64_t        ns_now_until_trigger;
    static uint64_t ns_now_fire = 0;

    if (1) /* TODO: just a test */
    {
        /* high-res busy-wait */
        writel(0b1u << 22u, gpio0clear);
        preempt_disable();
        // TODO: another option: spinlocks, GFP_ATOMIC ?
        ns_now_fire += 50000u;
        while (ktime_get_real_ns() < ns_now_fire) {};
        // trigger /sys/bus/gpio/devices/gpiochip0/gpio/gpio22/value, TODO: dirty hack, but quick
        writel(0b1u << 22u, gpio0set);
    }

    /* Raise Interrupt on PRU, telling it to timestamp IEP */
    mem_interface_trigger(HOST_PRU_EVT_TIMESTAMP);
    preempt_enable();

    /* Timestamp system clock */
    kt_now           = ktime_get_real(); // TODO: try ktime_get() / monotonic instead of real clock
    ts_now_system_ns = ktime_to_ns(kt_now);

    if (!timers_active) return HRTIMER_NORESTART;
    /*
     * Get distance of system clock from timer wrap.
     * Is negative, when interrupt happened before wrap, positive when after
     */ // TODO: there is something wrong here!
    div_u64_rem(ts_now_system_ns, trigger_loop_period_ns, &sys_ts_over_timer_wrap_ns);
    next_timestamp_ns = ts_now_system_ns + trigger_loop_period_ns - sys_ts_over_timer_wrap_ns;

    if (sys_ts_over_timer_wrap_ns > (trigger_loop_period_ns / 2))
    {
        /* normal use case (with pre-trigger) */
        /* self-regulating formula that results in ~ trigger_loop_period_ns */
        ns_now_until_trigger =
                2 * trigger_loop_period_ns - sys_ts_over_timer_wrap_ns - ns_pre_trigger;
    }
    else
    {
        printk(KERN_ERR "shprd.k: module missed a sync-trigger! -> last timestamp is "
                        "now probably used twice by PRU");
        ns_now_until_trigger = trigger_loop_period_ns - sys_ts_over_timer_wrap_ns - ns_pre_trigger;
        sys_ts_over_timer_wrap_ns = 0u; /* invalidate this measurement */
    }
    // TODO: minor optimization
    //  - write next_timestamp_ns directly into shared mem, as well as the other values in sync_loop
    //  - the reply-message is not needed anymore (current pru-code has nothing to calculate beforehand and would just use prev values if no new message arrives

    hrtimer_forward(timer_for_restart, kt_now, ns_to_ktime(ns_now_until_trigger));

    ns_now_fire = ts_now_system_ns + ns_now_until_trigger;
    return HRTIMER_RESTART;
}

/* Handler for sync-requests from PRU1 */
enum hrtimer_restart sync_loop_callback(struct hrtimer *timer_for_restart)
{
    struct ProtoMsg       sync_rqst;
    struct SyncMsg        sync_reply;
    ktime_t               kt_now;
    uint64_t              ts_now_system_ns;
    static uint64_t       ts_last_error_ns = 0;
    static const uint64_t quiet_time_ns    = 10000000000; // 10 s
    static unsigned int   step_pos         = 0;
    /* Timestamp system clock */
    kt_now                                 = ktime_get_real();
    ts_now_system_ns                       = ktime_to_ns(kt_now);

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
    else if ((ts_last_error_ns + quiet_time_ns < ts_now_system_ns) &&
             (prev_timestamp_ns + 2 * trigger_loop_period_ns < ts_now_system_ns) &&
             (prev_timestamp_ns > 0))
    {
        // TODO: not working as expected, this should alarm when PRUs are offline
        ts_last_error_ns = ts_now_system_ns;
        printk(KERN_ERR "shprd.k: Faulty behavior - PRU did not answer to "
                        "trigger-request in time!");
    }

    hrtimer_forward(timer_for_restart, kt_now,
                    ns_to_ktime(timer_steps_ns[step_pos])); /* variable sleep cycle */

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
    sync_data->error_sum +=
            sync_data
                    ->error_now; // integral should be behind controller, because current P-value is twice in calculation

    /* This is the actual PI controller equation
     * NOTE1: unit of clock_corr in pru is ticks, but input is based on nanosec
     * NOTE2: traces show, that quantization noise could be a problem. example: K-value of 127, divided by 128 will still be 0, ringing is around ~ +-150
     * previous parameters were:    P=1/32, I=1/128, correction settled at ~1340 with values from 1321 to 1359
     * current parameters:          P=1/100,I=1/300, correction settled at ~1332 with values from 1330 to 1335
     * */
    sync_data->clock_corr =
            (int32_t) (div_s64(sync_data->error_now, 128) + div_s64(sync_data->error_sum, 256));
    if (sync_data->clock_corr > +80000)
        sync_data->clock_corr = +80000; /* 0.4 % -> ~12s for phase lock */
    if (sync_data->clock_corr < -80000) sync_data->clock_corr = -80000;

    /* determine corrected loop_ticks for next buffer_block */
    sync_reply->type                 = MSG_SYNC;
    sync_reply->buffer_block_period  = TIMER_BASE_PERIOD + sync_data->clock_corr;
    sync_data->previous_period       = sync_reply->buffer_block_period;
    sync_reply->analog_sample_period = (sync_reply->buffer_block_period / ADC_SAMPLES_PER_BUFFER);
    sync_reply->compensation_steps   = sync_reply->buffer_block_period -
                                     (ADC_SAMPLES_PER_BUFFER * sync_reply->analog_sample_period);

    if (((sync_data->error_now > 500) || (sync_data->error_now < -500)) &&
        (++info_count >= 100)) /* val = 200 prints every 20s when enabled */
    {
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
    if (prev_timestamp_ns > 0)
    {
        int64_t diff_timestamp_ms =
                div_s64((int64_t) next_timestamp_ns - prev_timestamp_ns, 1000000u);
        if (diff_timestamp_ms < 0)
            printk(KERN_ERR "shprd.k: backwards timestamp-jump detected (sync-loop, %lld ms)",
                   diff_timestamp_ms);
        else if (diff_timestamp_ms < 95)
            printk(KERN_ERR "shprd.k: too small timestamp-jump detected (sync-loop, %lld ms)",
                   diff_timestamp_ms);
        else if (diff_timestamp_ms > 105)
            printk(KERN_ERR "shprd.k: forwards timestamp-jump detected (sync-loop, %lld ms)",
                   diff_timestamp_ms);
        else if (next_timestamp_ns == 0)
            printk(KERN_ERR "shprd.k: zero timestamp detected (sync-loop)");
    }
    prev_timestamp_ns             = next_timestamp_ns;
    sync_reply->next_timestamp_ns = next_timestamp_ns;

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
