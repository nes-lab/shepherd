#include <asm/io.h>
#include <linux/hrtimer.h>
#include <linux/ktime.h>

#include "commons.h"
#include "commons_inits.h"
#include "pru_comm.h"

#define PRU_BASE_ADDR        0x4A300000
#define PRU_INTC_OFFSET      0x00020000
#define PRU_INTC_SIZE        0x400
#define PRU_INTC_SISR_OFFSET 0x20

static void __iomem        *pru_intc_io       = NULL;
void __iomem               *pru_shared_mem_io = NULL;

/* This timer is used to schedule a delayed start of the actual sampling on the PRU */
struct hrtimer              delayed_start_timer;
static u8                   init_done = 0;

static enum hrtimer_restart delayed_start_callback(struct hrtimer *timer_for_restart);

void                        pru_comm_init(void)
{
    if (init_done) return;
    /* Maps the control registers of the PRU's interrupt controller */
    pru_intc_io = ioremap(PRU_BASE_ADDR + PRU_INTC_OFFSET, PRU_INTC_SIZE);
    /* Maps the shared memory in the shared DDR, used to exchange info/control between PRU cores and kernel */
    pru_shared_mem_io =
            ioremap(PRU_BASE_ADDR + PRU_SHARED_MEM_STRUCT_OFFSET, sizeof(struct SharedMem));

    hrtimer_init(&delayed_start_timer, CLOCK_REALTIME, HRTIMER_MODE_ABS);
    delayed_start_timer.function = &delayed_start_callback;

    init_done                    = 1;
    printk(KERN_INFO "shprd.k: mem-interface initialized, shared mem @ 0x%p", pru_shared_mem_io);

    pru_comm_reset();
}

void pru_comm_exit(void)
{
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
    hrtimer_cancel(&delayed_start_timer);
    init_done = 0;
}

void pru_comm_reset(void)
{
    struct SharedMem *shared_mem = (struct SharedMem *) pru_shared_mem_io;

    if (!init_done) return;

    shared_mem->calibration_settings = CalibrationConfig_default;
    shared_mem->converter_settings   = ConverterConfig_default;
    shared_mem->harvester_settings   = HarvesterConfig_default;

    shared_mem->programmer_ctrl      = ProgrammerCtrl_default;

    shared_mem->pru0_msg_inbox       = ProtoMsg_default;
    shared_mem->pru0_msg_outbox      = ProtoMsg_default;
    shared_mem->pru0_msg_error       = ProtoMsg_default;

    shared_mem->pru1_sync_inbox      = SyncMsg_default;
    shared_mem->pru1_sync_outbox     = ProtoMsg_default;
    shared_mem->pru1_msg_error       = ProtoMsg_default;
    printk(KERN_INFO "shprd.k: mem-interface reset to default");
}


static enum hrtimer_restart delayed_start_callback(struct hrtimer *timer_for_restart)
{
    struct timespec ts_now;
    uint64_t        now_ns_system;

    pru_comm_set_state(STATE_RUNNING);

    /* Timestamp system clock */
    getnstimeofday(&ts_now);

    now_ns_system = (uint64_t) timespec_to_ns(&ts_now);

    printk(KERN_INFO "shprd.k: Triggered delayed start  @ %llu (now)", now_ns_system);
    return HRTIMER_NORESTART;
}

int pru_comm_schedule_delayed_start(unsigned int start_time_second)
{
    ktime_t  trigger_timer_time;
    uint64_t trigger_timer_time_ns;

    trigger_timer_time = ktime_set((const s64) start_time_second, 0);

    /**
     * The timer should fire in the middle of the interval before we want to
     * start. This allows the PRU enough time to receive the interrupt and
     * prepare itself to start at exactly the right time.
     */
    trigger_timer_time = ktime_sub_ns(trigger_timer_time, 3 * pru_comm_get_buffer_period_ns() / 4);

    trigger_timer_time_ns = ktime_to_ns(trigger_timer_time);

    printk(KERN_INFO "shprd.k: Delayed start timer set to %llu", trigger_timer_time_ns);

    hrtimer_start(&delayed_start_timer, trigger_timer_time, HRTIMER_MODE_ABS);

    return 0;
}

int  pru_comm_cancel_delayed_start(void) { return hrtimer_cancel(&delayed_start_timer); }

void pru_comm_trigger(unsigned int system_event)
{
    /* Raise Interrupt on PRU INTC*/
    writel(system_event, pru_intc_io + PRU_INTC_SISR_OFFSET);
}

enum ShepherdState pru_comm_get_state(void)
{
    return (enum ShepherdState) readl(pru_shared_mem_io +
                                      offsetof(struct SharedMem, shepherd_state));
}

void pru_comm_set_state(enum ShepherdState state)
{
    writel(state, pru_shared_mem_io + offsetof(struct SharedMem, shepherd_state));
}

unsigned int pru_comm_get_buffer_period_ns(void)
{
    return readl(pru_shared_mem_io + offsetof(struct SharedMem, buffer_period_ns));
}


unsigned char pru1_comm_receive_sync_request(struct ProtoMsg *const msg)
{
    static const uint32_t offset_msg    = offsetof(struct SharedMem, pru1_sync_outbox);
    static const uint32_t offset_unread = offset_msg + offsetof(struct ProtoMsg, unread);

    /* testing for unread-msg-token */
    if (readb(pru_shared_mem_io + offset_unread) >= 1u)
    {
        /* if unread, then continue to copy request */
        memcpy_fromio(msg, pru_shared_mem_io + offset_msg, sizeof(struct ProtoMsg));
        /* mark as read */
        writeb(0u, pru_shared_mem_io + offset_unread);

        if (msg->id != MSG_TO_KERNEL) /* Error occurs if something writes over boundaries */
            printk(KERN_ERR "shprd.k: recv_sync_req from pru1 -> mem corruption? id=%u (!=%u)",
                   msg->id, MSG_TO_KERNEL);

        return 1;
    }
    return 0;
}


unsigned char pru1_comm_send_sync_reply(struct SyncMsg *const msg)
{
    static const uint32_t offset_msg    = offsetof(struct SharedMem, pru1_sync_inbox);
    static const uint32_t offset_unread = offset_msg + offsetof(struct SyncMsg, unread);
    const unsigned char   status        = readb(pru_shared_mem_io + offset_unread) == 0u;

    /* first update payload in memory */
    msg->id                             = MSG_TO_PRU;
    msg->unread                         = 0u;
    memcpy_toio(pru_shared_mem_io + offset_msg, msg, sizeof(struct SyncMsg));

    /* activate message with unread-token */
    writeb(1u, pru_shared_mem_io + offset_unread);
    return status;
}


unsigned char pru0_comm_receive_error(struct ProtoMsg *const msg)
{
    static const uint32_t offset_msg    = offsetof(struct SharedMem, pru0_msg_error);
    static const uint32_t offset_unread = offset_msg + offsetof(struct ProtoMsg, unread);

    /* testing for unread-msg-token */
    if (readb(pru_shared_mem_io + offset_unread) >= 1u)
    {
        /* if unread, then continue to copy request */
        memcpy_fromio(msg, pru_shared_mem_io + offset_msg, sizeof(struct ProtoMsg));
        /* mark as read */
        writeb(0u, pru_shared_mem_io + offset_unread);

        if (msg->id != MSG_TO_KERNEL) /* Error occurs if something writes over boundaries */
            printk(KERN_ERR "shprd.k: recv_status from pru0 -> mem corruption? id=%u (!=%u)",
                   msg->id, MSG_TO_KERNEL);

        return 1;
    }
    return 0;
}


unsigned char pru1_comm_receive_error(struct ProtoMsg *const msg)
{
    static const uint32_t offset_msg    = offsetof(struct SharedMem, pru1_msg_error);
    static const uint32_t offset_unread = offset_msg + offsetof(struct ProtoMsg, unread);

    /* testing for unread-msg-token */
    if (readb(pru_shared_mem_io + offset_unread) >= 1u)
    {
        /* if unread, then continue to copy request */
        memcpy_fromio(msg, pru_shared_mem_io + offset_msg, sizeof(struct ProtoMsg));
        /* mark as read */
        writeb(0u, pru_shared_mem_io + offset_unread);

        if (msg->id != MSG_TO_KERNEL) /* Error occurs if something writes over boundaries */
            printk(KERN_ERR "shprd.k: recv_status from pru1 -> mem corruption? id=%u (!=%u)",
                   msg->id, MSG_TO_KERNEL);

        return 1;
    }
    return 0;
}


unsigned char pru0_comm_receive_msg(struct ProtoMsg *const msg)
{
    static const uint32_t offset_msg    = offsetof(struct SharedMem, pru0_msg_outbox);
    static const uint32_t offset_unread = offset_msg + offsetof(struct ProtoMsg, unread);

    /* testing for unread-msg-token */
    if (readb(pru_shared_mem_io + offset_unread) >= 1u)
    {
        /* if unread, then continue to copy request */
        memcpy_fromio(msg, pru_shared_mem_io + offset_msg, sizeof(struct ProtoMsg));
        /* mark as read */
        writeb(0u, pru_shared_mem_io + offset_unread);

        if (msg->id != MSG_TO_KERNEL) /* Error occurs if something writes over boundaries */
            printk(KERN_ERR "shprd.k: recv_msg from pru0 -> mem corruption? id=%u (!=%u)", msg->id,
                   MSG_TO_KERNEL);

        return 1;
    }
    return 0;
}


unsigned char pru0_comm_send_msg(struct ProtoMsg *const msg)
{
    static const uint32_t offset_msg    = offsetof(struct SharedMem, pru0_msg_inbox);
    static const uint32_t offset_unread = offset_msg + offsetof(struct ProtoMsg, unread);
    const unsigned char   status        = readb(pru_shared_mem_io + offset_unread) == 0u;

    /* first update payload in memory */
    msg->id                             = MSG_TO_PRU;
    msg->unread                         = 0u;
    memcpy_toio(pru_shared_mem_io + offset_msg, msg, sizeof(struct ProtoMsg));

    /* activate message with unread-token */
    writeb(1u, pru_shared_mem_io + offset_unread);
    return status;
}

unsigned char pru0_comm_check_send_status(void)
{
    static const uint32_t offset_unread =
            offsetof(struct SharedMem, pru0_msg_inbox) + offsetof(struct ProtoMsg, unread);
    return readb(pru_shared_mem_io + offset_unread) == 0u;
}
