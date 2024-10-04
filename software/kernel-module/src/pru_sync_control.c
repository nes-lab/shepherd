#include <linux/hrtimer.h>
#include <linux/ktime.h>
#include <linux/math64.h>
#include <linux/slab.h>

#include "_shepherd_config.h"
#include "pru_mem_interface.h"
#include "pru_sync_control.h"

static uint32_t             sys_ts_over_timer_wrap_ns = 0;
static uint64_t             ts_upcoming_ns            = 0;
static uint64_t             ts_previous_ns            = 0; /* for plausibility-check */

static enum hrtimer_restart trigger_loop_callback(struct hrtimer *timer_for_restart);
static enum hrtimer_restart sync_loop_callback(struct hrtimer *timer_for_restart);
static uint32_t trigger_loop_interval_ns = SYNC_INTERVAL_NS; /* just initial value to avoid div0 */

/*
* add pre-trigger, because design previously aimed directly for busy pru_timer_wrap
* (50% chance that pru takes a less meaningful counter-reading after wrap)
* 1 ms + 5 us, this should be enough time for the ping-pong-messaging to complete before timer_wrap
*/
static const uint32_t     ns_pre_trigger = 1005000u;

/* Timer to trigger fast sync_loop */
struct hrtimer            trigger_loop_timer;
struct hrtimer            sync_loop_timer;
static u8                 timers_active    = 0u;

/* series of halving sleep cycles, sleep less coming slowly near a total of 100ms of sleep */
static const unsigned int timer_steps_ns[] = {20000000u, 20000000u, 20000000u, 20000000u, 10000000u,
                                              5000000u,  2000000u,  1000000u,  500000u,   200000u,
                                              100000u,   50000u,    20000u};
/* TODO: sleep 100ms - 20 us
* TODO: above halvings sum up to 98870 us */
static const size_t       timer_steps_ns_size = sizeof(timer_steps_ns) / sizeof(timer_steps_ns[0]);
//static unsigned int step_pos = 0;

static uint32_t           info_count          = 6666; /* >6k triggers explanation-message once */
struct sync_data_s       *sync_data           = NULL;
static u8                 init_done           = 0;

/* Benchmark high-res busy-wait - RESULTS:
 * - ktime_get                  99.6us   215n   463ns/call
 * - ktime_get_real             100.3us  302n   332ns/call -> current best performer (4.19.94-ti-r73)
 * - ktime_get_ns               100.2us  257n   389ns/call
 * - ktime_get_real_ns          131.5us  247n   532ns
 * - ktime_get_raw              99.3us   273n   364ns
 * - ktime_get_real_fast_ns     90.0us   308n   292ns
 * - increment-loop             825us    100k   8.25ns/iteration
 */

void                      sync_exit(void)
{
    hrtimer_cancel(&trigger_loop_timer);
    hrtimer_cancel(&sync_loop_timer);
    if (sync_data != NULL)
    {
        kfree(sync_data);
        sync_data = NULL;
    }
    init_done = 0;
    printk(KERN_INFO "shprd.k: pru-sync-system exited");
}

int sync_init(void)
{
    uint32_t ret_value;

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

    /* timer for trigger, TODO: this needs better naming, make clear what it does
*                      sync_interval_ns */
    trigger_loop_interval_ns = SYNC_INTERVAL_NS; /* should be 100 ms */

    hrtimer_init(&trigger_loop_timer, CLOCK_REALTIME, HRTIMER_MODE_ABS);
    // TODO: HRTIMER_MODE_ABS_HARD wanted, but _HARD not defined in 4.19 (without -RT)
    trigger_loop_timer.function = &trigger_loop_callback;

    /* timer for Sync-Loop */
    hrtimer_init(&sync_loop_timer, CLOCK_REALTIME, HRTIMER_MODE_ABS);
    sync_loop_timer.function = &sync_loop_callback;

    init_done                = 1;
    printk(KERN_INFO "shprd.k: pru-sync-system initialized (wanted: hres, abs, hard)");

    ret_value = hrtimer_is_hres_active(&trigger_loop_timer);
    printk("%sshprd.k: trigger_hrtimer.hres    = %d", ret_value == 1 ? KERN_INFO : KERN_ERR,
           ret_value);
    ret_value = trigger_loop_timer.is_rel;
    printk("%sshprd.k: trigger_hrtimer.is_rel  = %d", ret_value == 0 ? KERN_INFO : KERN_ERR,
           ret_value);
    ret_value = trigger_loop_timer.is_soft;
    printk("%sshprd.k: trigger_hrtimer.is_soft = %d", ret_value == 0 ? KERN_INFO : KERN_ERR,
           ret_value);
    //printk(KERN_INFO "shprd.k: trigger_hrtimer.is_hard = %d", trigger_loop_timer.is_hard); // needs kernel 5.4+
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
    const uint64_t ts_now_ns = ktime_get_real_ns();

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

    div_u64_rem(ts_now_ns, trigger_loop_interval_ns, &ns_over_wrap);
    if (ns_over_wrap > (trigger_loop_interval_ns / 2))
    {
        /* target timer-wrap one ahead */
        ns_to_next_trigger = 2 * trigger_loop_interval_ns - ns_over_wrap - ns_pre_trigger;
    }
    else
    {
        /* target next timer-wrap */
        ns_to_next_trigger = trigger_loop_interval_ns - ns_over_wrap - ns_pre_trigger;
    }

    hrtimer_start(&trigger_loop_timer, ns_to_ktime(ts_now_ns + ns_to_next_trigger),
                  HRTIMER_MODE_ABS); // was: HRTIMER_MODE_ABS_HARD for -rt Kernel

    hrtimer_start(&sync_loop_timer, ns_to_ktime(ts_now_ns + 1000000u), HRTIMER_MODE_ABS);
    printk(KERN_INFO "shprd.k: pru-sync-system started");
    timers_active = 1;
}

void sync_reset(void)
{
    sync_data->error_now         = 0;
    sync_data->error_pre         = 0;
    sync_data->error_dif         = 0;
    sync_data->error_sum         = 0;
    sync_data->clock_corr        = 0;
    sync_data->previous_interval = SYNC_INTERVAL_TICKS;
}

enum hrtimer_restart trigger_loop_callback(struct hrtimer *timer_for_restart)
{
    uint64_t ns_to_next_trigger;
    uint64_t ts_now_ns;

    /* Raise Interrupt on PRU, telling it to timestamp IEP */
    mem_interface_trigger(HOST_PRU_EVT_TIMESTAMP);

    /* Timestamp system clock */
    ts_now_ns = ktime_get_real_ns();

    if (!timers_active) return HRTIMER_NORESTART;
    /*
     * Get distance of system clock from timer wrap.
     * Is negative, when interrupt happened before wrap, positive when after
     */
    div_u64_rem(ts_now_ns, trigger_loop_interval_ns, &sys_ts_over_timer_wrap_ns);
    ts_upcoming_ns = ts_now_ns + trigger_loop_interval_ns - sys_ts_over_timer_wrap_ns;
    // TODO: test! was 'ts_upcoming_ns += trigger_loop_interval_ns' before

    if (sys_ts_over_timer_wrap_ns > (trigger_loop_interval_ns / 2))
    {
        /* normal use case (with pre-trigger) */
        /* self regulating formula that results in ~ trigger_loop_interval_ns */
        ns_to_next_trigger =
                2 * trigger_loop_interval_ns - sys_ts_over_timer_wrap_ns - ns_pre_trigger;
    }
    else
    {
        printk(KERN_ERR "shprd.k: module missed a sync-trigger! -> last timestamp is "
                        "now probably used twice by PRU");
        ns_to_next_trigger = trigger_loop_interval_ns - sys_ts_over_timer_wrap_ns - ns_pre_trigger;
        sys_ts_over_timer_wrap_ns = 0u; /* invalidate this measurement */
    }
    // TODO: minor optimization
    //  - write ts_upcoming_ns directly into shared mem, as well as the other values in sync_loop
    //  - the reply-message is not needed anymore (current pru-code has nothing to calculate beforehand and would just use prev values if no new message arrives

    hrtimer_forward(timer_for_restart, ns_to_ktime(ts_now_ns), ns_to_ktime(ns_to_next_trigger));

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
    const uint64_t        ts_now_ns        = ktime_get_real_ns();

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
             (ts_previous_ns + 2 * trigger_loop_interval_ns < ts_now_ns) && (ts_previous_ns > 0))
    {
        // TODO: not working as expected, this routine should get notified when PRUs are offline
        ts_last_error_ns = ts_now_ns;
        printk(KERN_ERR "shprd.k: Faulty behavior - PRU did not answer to "
                        "trigger-request in time!");
    }
    else if ((ts_previous_ns + 2 * trigger_loop_interval_ns < ts_now_ns) && (ts_previous_ns > 0))
    {
        // try to reduce CPU-Usage (ktimersoftd/0 has 50%) when PRUs are halting during operation
        step_pos = 0;
    }

    /* variable sleep cycle */
    hrtimer_forward(timer_for_restart, ns_to_ktime(ts_now_ns),
                    ns_to_ktime(timer_steps_ns[step_pos]));

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
            div_u64(((uint64_t) trigger_loop_interval_ns << 30u), sync_data->previous_interval);

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
    if (sync_data->error_now < -(int64_t) (trigger_loop_interval_ns / 2))
    {
        /* Currently the correction is (almost) always headed in one direction
         * - the pre-trigger @ - 1 ms is the "almost" (1 % chance for the other direction)
         * - correct the imbalance to 50/50
         */
        sync_data->error_now += trigger_loop_interval_ns;
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
    sync_reply->type                  = MSG_SYNC_ROUTINE;
    sync_reply->sync_interval_ticks   = SYNC_INTERVAL_TICKS + sync_data->clock_corr;
    sync_data->previous_interval      = sync_reply->sync_interval_ticks;
    sync_reply->sample_interval_ticks = (sync_reply->sync_interval_ticks / SAMPLES_PER_SYNC);
    sync_reply->compensation_steps    = sync_reply->sync_interval_ticks -
                                     (SAMPLES_PER_SYNC * sync_reply->sample_interval_ticks);

    if (((sync_data->error_now > 500) || (sync_data->error_now < -500)) && (++info_count >= 100))
    {
        /* val = 200 prints every 20s when enabled */
        printk(KERN_INFO "shprd.sync: period=%u, n_comp=%u, er_pid=%lld/%lld/%lld, "
                         "ns_iep=%u, ns_sys=%u",
               sync_reply->sample_interval_ticks, // = upper part of sync_interval_ticks
               sync_reply->compensation_steps,    // = lower part of sync_interval_ticks
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

    if ((sync_reply->sync_interval_ticks > SYNC_INTERVAL_TICKS + 80000) ||
        (sync_reply->sync_interval_ticks < SYNC_INTERVAL_TICKS - 80000))
        printk(KERN_ERR "shprd.k: sync_interval_ticks out of limits (%u instead of ~20M)",
               sync_reply->sync_interval_ticks);
    if ((sync_reply->sample_interval_ticks > SAMPLE_INTERVAL_TICKS + 10) ||
        (sync_reply->sample_interval_ticks < SAMPLE_INTERVAL_TICKS - 10))
        printk(KERN_ERR "shprd.k: sample_interval_ticks out of limits (%u instead of ~2000)",
               sync_reply->sample_interval_ticks);

    return 0;
}
