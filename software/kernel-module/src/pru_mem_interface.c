#include <linux/hrtimer.h>
#include <linux/io.h>
#include <linux/ktime.h>

#include "_commons.h"
#include "_commons_inits.h"
#include "_shared_mem.h"
#include "pru_mem_interface.h"

#define PRU_BASE_ADDR        (0x4A300000ul)
#define PRU_INTC_OFFSET      (0x00020000ul)
#define PRU_INTC_SIZE        (0x400)
#define PRU_INTC_SISR_OFFSET (0x20)

static void __iomem        *pru_intc_io       = NULL;
void __iomem               *pru_shared_mem_io = NULL;

/* This timer is used to schedule a delayed start of the actual sampling on the PRU */
static struct hrtimer       delayed_start_timer;
static struct hrtimer       delayed_stop_timer;
static u8                   init_done = 0;

static enum hrtimer_restart delayed_start_callback(struct hrtimer *timer_for_restart);
static enum hrtimer_restart delayed_stop_callback(struct hrtimer *timer_for_restart);

void                        mem_interface_init(void)
{
    if (init_done)
    {
        printk(KERN_ERR "shprd.k: mem-interface init requested -> can't init twice!");
        return;
    }
    /* Maps the control registers of the PRU's interrupt controller */
    pru_intc_io = ioremap_nocache(PRU_BASE_ADDR + PRU_INTC_OFFSET, PRU_INTC_SIZE);
    /* Maps the shared memory in the shared DDR, used to exchange info/control between PRU cores and kernel */
    pru_shared_mem_io =
            ioremap_nocache(PRU_BASE_ADDR + PRU_SHARED_MEM_OFFSET, sizeof(struct SharedMem));

    hrtimer_init(&delayed_start_timer, CLOCK_REALTIME, HRTIMER_MODE_ABS);
    delayed_start_timer.function = &delayed_start_callback;

    hrtimer_init(&delayed_stop_timer, CLOCK_REALTIME, HRTIMER_MODE_ABS);
    delayed_stop_timer.function = &delayed_stop_callback;

    init_done                   = 1;
    printk(KERN_INFO "shprd.k: mem-interface initialized, shared mem @ 0x%X, size = %d bytes",
           (uint32_t) PRU_BASE_ADDR + PRU_SHARED_MEM_OFFSET, sizeof(struct SharedMem));

    mem_interface_reset();
}

void mem_interface_exit(void)
{
    if (delayed_start_timer.base != NULL) hrtimer_cancel(&delayed_start_timer);
    if (delayed_stop_timer.base != NULL) hrtimer_cancel(&delayed_stop_timer);

    if (pru_intc_io != NULL)
    {
        iounmap(pru_intc_io);
        pru_intc_io = NULL;
    }
    if (pru_shared_mem_io != NULL)
    {
        iounmap(pru_shared_mem_io);
        pru_shared_mem_io = NULL;
    }
    init_done = 0;
    printk(KERN_INFO "shprd.k: mem-interface exited");
}

void mem_interface_reset(void)
{
    struct SharedMem *const shared_mem = (struct SharedMem *const) pru_shared_mem_io;
    // TODO: why not use this as default interface?

    if (!init_done)
    {
        printk(KERN_ERR "shprd.k: mem-interface reset requested without prior init");
        return;
    }

    shared_mem->buffer_iv_inp_sys_idx = IDX_OUT_OF_BOUND;
    memset_io(&shared_mem->cache_flags[0], 0u, 4 * CACHE_U32_FLAGS_N);

    shared_mem->calibration_settings = CalibrationConfig_default;
    shared_mem->converter_settings   = ConverterConfig_default;
    shared_mem->battery_settings     = BatteryConfig_default;
    shared_mem->harvester_settings   = HarvesterConfig_default;

    shared_mem->programmer_ctrl      = ProgrammerCtrl_default;

    shared_mem->pru0_msg_inbox       = ProtoMsg_default;
    //shared_mem->pru0_msg_outbox      = ProtoMsg_default;  // Owned by PRU
    //shared_mem->pru0_msg_error       = ProtoMsg_default;

    shared_mem->pru1_msg_inbox       = ProtoMsg_default;
    //shared_mem->pru1_msg_outbox      = ProtoMsg_default; // Owned by PRU
    //shared_mem->pru1_msg_error       = ProtoMsg_default;
    //shared_mem->canary1               = CANARY_VALUE_U32;  // Owned by PRU
    //shared_mem->canary2               = CANARY_VALUE_U32;
    //shared_mem->canary3               = CANARY_VALUE_U32;
    printk(KERN_INFO "shprd.k: mem-interface reset to default");
}

/* verify the 13 canaries that are placed in shared-mem */
uint32_t mem_interface_check_canaries(void)
{
    uint32_t                ret        = 0u;
    struct SharedMem *const shared_mem = (struct SharedMem *) pru_shared_mem_io;
    if (pru_shared_mem_io == NULL) return 0u;

    if (shared_mem->calibration_settings.canary != CANARY_VALUE_U32)
    {
        printk(KERN_ERR "shprd.k: canary of calibration_settings was harmed!");
        ret |= 1u << 0u;
    }

    if (shared_mem->converter_settings.canary != CANARY_VALUE_U32)
    {
        printk(KERN_ERR "shprd.k: canary of converter_settings was harmed!");
        ret |= 1u << 1u;
    }
    if (shared_mem->harvester_settings.canary != CANARY_VALUE_U32)
    {
        printk(KERN_ERR "shprd.k: canary of harvester_settings was harmed!");
        ret |= 1u << 2u;
    }
    if (shared_mem->programmer_ctrl.canary != CANARY_VALUE_U32)
    {
        printk(KERN_ERR "shprd.k: canary of programmer_ctrl was harmed!");
        ret |= 1u << 3u;
    }
    if (shared_mem->pru0_msg_inbox.canary != CANARY_VALUE_U32)
    {
        printk(KERN_ERR "shprd.k: canary of pru0_msg_inbox was harmed!");
        ret |= 1u << 4u;
    }
    if (shared_mem->pru0_msg_outbox.canary != CANARY_VALUE_U32)
    {
        printk(KERN_ERR "shprd.k: canary of pru0_msg_outbox was harmed!");
        ret |= 1u << 5u;
    }
    if (shared_mem->pru0_msg_error.canary != CANARY_VALUE_U32)
    {
        printk(KERN_ERR "shprd.k: canary of pru0_msg_error was harmed!");
        ret |= 1u << 6u;
    }
    if (shared_mem->pru1_msg_inbox.canary != CANARY_VALUE_U32)
    {
        printk(KERN_ERR "shprd.k: canary of pru1_msg_inbox was harmed!");
        ret |= 1u << 7u;
    }
    if (shared_mem->pru1_msg_outbox.canary != CANARY_VALUE_U32)
    {
        printk(KERN_ERR "shprd.k: canary of pru1_msg_outbox was harmed!");
        ret |= 1u << 8u;
    }
    if (shared_mem->pru1_msg_error.canary != CANARY_VALUE_U32)
    {
        printk(KERN_ERR "shprd.k: canary of pru1_msg_error was harmed!");
        ret |= 1u << 9u;
    }
    if (shared_mem->canary1 != CANARY_VALUE_U32)
    {
        printk(KERN_ERR "shprd.k: canary1 of shared_mem was harmed!");
        ret |= 1u << 10u;
    }
    if (shared_mem->canary2 != CANARY_VALUE_U32)
    {
        printk(KERN_ERR "shprd.k: canary2 of shared_mem was harmed!");
        ret |= 1u << 11u;
    }
    if (shared_mem->canary3 != CANARY_VALUE_U32)
    {
        printk(KERN_ERR "shprd.k: canary3 of shared_mem was harmed!");
        ret |= 1u << 12u;
    }
    return ret;
}


static enum hrtimer_restart delayed_start_callback(struct hrtimer *timer_for_restart)
{
    /* Timestamp system clock */
    const uint64_t now_ns_system = ktime_get_real_ns();

    mem_interface_set_state(STATE_STARTING);

    printk(KERN_INFO "shprd.k: Triggered delayed start  @ %llu (now)", now_ns_system);
    return HRTIMER_NORESTART;
}

static enum hrtimer_restart delayed_stop_callback(struct hrtimer *timer_for_restart)
{
    /* Timestamp system clock */
    const uint64_t now_ns_system = ktime_get_real_ns();

    mem_interface_set_state(STATE_STOPPED);

    printk(KERN_INFO "shprd.k: Triggered delayed stop  @ %llu (now)", now_ns_system);
    return HRTIMER_NORESTART;
}

int mem_interface_schedule_delayed_start(unsigned int start_time_second)
{
    ktime_t  kt_trigger;
    uint64_t ts_trigger_ns;

    kt_trigger    = ktime_set((const s64) start_time_second, 0);

    /**
     * The timer should fire in the middle of the interval before we want to
     * start. This allows the PRU enough time to receive the interrupt and
     * prepare itself to start at exactly the right time.
     */
    kt_trigger    = ktime_sub_ns(kt_trigger, 15 * SYNC_INTERVAL_NS / 16);

    ts_trigger_ns = ktime_to_ns(kt_trigger);

    printk(KERN_INFO "shprd.k: Delayed start timer set to %llu", ts_trigger_ns);

    hrtimer_start(&delayed_start_timer, kt_trigger, HRTIMER_MODE_ABS);

    return 0;
}

int mem_interface_schedule_delayed_stop(unsigned int stop_time_second)
{
    ktime_t  kt_trigger;
    uint64_t ts_trigger_ns;

    kt_trigger    = ktime_set((const s64) stop_time_second, 0);

    /**
     * The timer should fire in the middle of the interval after we want to
     * stop.
     */
    kt_trigger    = ktime_add_ns(kt_trigger, 1 * SYNC_INTERVAL_NS / 16);

    ts_trigger_ns = ktime_to_ns(kt_trigger);

    printk(KERN_INFO "shprd.k: Delayed stop timer set to %llu", ts_trigger_ns);

    hrtimer_start(&delayed_stop_timer, kt_trigger, HRTIMER_MODE_ABS);

    return 0;
}

int  mem_interface_cancel_delayed_start(void) { return hrtimer_cancel(&delayed_start_timer); }
int  mem_interface_cancel_delayed_stop(void) { return hrtimer_cancel(&delayed_stop_timer); }

void mem_interface_trigger(unsigned int system_event)
{
    /* Raise Interrupt on PRU INTC*/
    iowrite32(system_event, pru_intc_io + PRU_INTC_SISR_OFFSET);
}

enum ShepherdState mem_interface_get_state(void)
{
    return (enum ShepherdState) ioread32(pru_shared_mem_io +
                                         offsetof(struct SharedMem, shp_pru_state));
}

void mem_interface_set_state(enum ShepherdState state)
{
    iowrite32(state, pru_shared_mem_io + offsetof(struct SharedMem, shp_pru_state));
}

// TODO: unify send/receive functions a lot of duplication
unsigned char pru1_comm_receive_sync_request(struct ProtoMsg *const msg)
{
    static const uint32_t offset_msg    = offsetof(struct SharedMem, pru1_msg_outbox);
    static const uint32_t offset_unread = offset_msg + offsetof(struct ProtoMsg, unread);

    /* testing for unread-msg-token */
    if (ioread8(pru_shared_mem_io + offset_unread) >= 1u)
    {
        /* if unread, then continue to copy request */
        memcpy_fromio(msg, pru_shared_mem_io + offset_msg, sizeof(struct ProtoMsg));
        /* mark as read */
        iowrite32(0u, pru_shared_mem_io + offset_unread);

        if (msg->id != MSG_TO_KERNEL) /* Error occurs if something writes over boundaries */
            printk(KERN_ERR "shprd.k: recv_sync_req from pru1 -> mem corruption? id=%u (!=%u)",
                   msg->id, MSG_TO_KERNEL);
        if (msg->canary != CANARY_VALUE_U32)
            printk(KERN_ERR "shprd.k: recv_sync_req from PRU1 -> canary was harmed");
        return 1;
    }
    return 0;
}


unsigned char pru1_comm_send_sync_reply(struct ProtoMsg *const msg)
{
    static const uint32_t offset_msg    = offsetof(struct SharedMem, pru1_msg_inbox);
    static const uint32_t offset_unread = offset_msg + offsetof(struct ProtoMsg, unread);
    const unsigned char   status        = ioread8(pru_shared_mem_io + offset_unread) == 0u;

    /* first update payload in memory */
    msg->id                             = MSG_TO_PRU;
    msg->unread                         = 0u;
    msg->canary                         = CANARY_VALUE_U32;
    memcpy_toio(pru_shared_mem_io + offset_msg, msg, sizeof(struct ProtoMsg));

    /* activate message with unread-token */
    iowrite8(1u, pru_shared_mem_io + offset_unread);
    return status;
}


unsigned char pru0_comm_receive_error(struct ProtoMsg *const msg)
{
    static const uint32_t offset_msg    = offsetof(struct SharedMem, pru0_msg_error);
    static const uint32_t offset_unread = offset_msg + offsetof(struct ProtoMsg, unread);

    /* testing for unread-msg-token */
    if (ioread8(pru_shared_mem_io + offset_unread) >= 1u)
    {
        /* if unread, then continue to copy request */
        memcpy_fromio(msg, pru_shared_mem_io + offset_msg, sizeof(struct ProtoMsg));
        /* mark as read */
        iowrite8(0u, pru_shared_mem_io + offset_unread);

        if (msg->id != MSG_TO_KERNEL) /* Error occurs if something writes over boundaries */
            printk(KERN_ERR "shprd.k: recv_status from pru0 -> mem corruption? id=%u (!=%u)",
                   msg->id, MSG_TO_KERNEL);
        if (msg->canary != CANARY_VALUE_U32)
            printk(KERN_ERR "shprd.k: recv_error from PRU0 -> canary was harmed");
        return 1;
    }
    return 0;
}


unsigned char pru1_comm_receive_error(struct ProtoMsg *const msg)
{
    static const uint32_t offset_msg    = offsetof(struct SharedMem, pru1_msg_error);
    static const uint32_t offset_unread = offset_msg + offsetof(struct ProtoMsg, unread);

    /* testing for unread-msg-token */
    if (ioread8(pru_shared_mem_io + offset_unread) >= 1u)
    {
        /* if unread, then continue to copy request */
        memcpy_fromio(msg, pru_shared_mem_io + offset_msg, sizeof(struct ProtoMsg));
        /* mark as read */
        iowrite8(0u, pru_shared_mem_io + offset_unread);

        if (msg->id != MSG_TO_KERNEL) /* Error occurs if something writes over boundaries */
            printk(KERN_ERR "shprd.k: recv_status from pru1 -> mem corruption? id=%u (!=%u)",
                   msg->id, MSG_TO_KERNEL);
        if (msg->canary != CANARY_VALUE_U32)
            printk(KERN_ERR "shprd.k: recv_error from PRU1 -> canary was harmed");
        return 1;
    }
    return 0;
}


unsigned char pru0_comm_receive_msg(struct ProtoMsg *const msg)
{
    static const uint32_t offset_msg    = offsetof(struct SharedMem, pru0_msg_outbox);
    static const uint32_t offset_unread = offset_msg + offsetof(struct ProtoMsg, unread);

    /* testing for unread-msg-token */
    if (ioread8(pru_shared_mem_io + offset_unread) >= 1u)
    {
        /* if unread, then continue to copy request */
        memcpy_fromio(msg, pru_shared_mem_io + offset_msg, sizeof(struct ProtoMsg));
        /* mark as read */
        iowrite8(0u, pru_shared_mem_io + offset_unread);

        if (msg->id != MSG_TO_KERNEL) /* Error occurs if something writes over boundaries */
            printk(KERN_ERR "shprd.k: recv_msg from pru0 -> mem corruption? id=%u (!=%u)", msg->id,
                   MSG_TO_KERNEL);
        if (msg->canary != CANARY_VALUE_U32)
            printk(KERN_ERR "shprd.k: recv_msg from PRU1 -> canary was harmed");
        return 1;
    }
    return 0;
}


unsigned char pru0_comm_send_msg(struct ProtoMsg *const msg)
{
    static const uint32_t offset_msg    = offsetof(struct SharedMem, pru0_msg_inbox);
    static const uint32_t offset_unread = offset_msg + offsetof(struct ProtoMsg, unread);
    const unsigned char   status        = ioread8(pru_shared_mem_io + offset_unread) == 0u;

    /* first update payload in memory */
    msg->id                             = MSG_TO_PRU;
    msg->unread                         = 0u;
    msg->canary                         = CANARY_VALUE_U32;
    memcpy_toio(pru_shared_mem_io + offset_msg, msg, sizeof(struct ProtoMsg));

    /* activate message with unread-token */
    iowrite8(1u, pru_shared_mem_io + offset_unread);
    return status;
}

unsigned char pru0_comm_check_send_status(void)
{
    static const uint32_t offset_unread =
            offsetof(struct SharedMem, pru0_msg_inbox) + offsetof(struct ProtoMsg, unread);
    return ioread8(pru_shared_mem_io + offset_unread) == 0u;
}
