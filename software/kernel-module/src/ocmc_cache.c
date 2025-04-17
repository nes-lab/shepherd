#include <linux/delay.h>
#include <linux/hrtimer.h>
#include <linux/io.h>
#include <linux/ktime.h>
#include <linux/math64.h>

#include "_commons.h"
#include "_shared_mem.h"
#include "ocmc_cache.h"

#define OCMC_BASE_ADDR         (0x40300000ul)
#define OCMC_SIZE              (0xFFFFu)
#define CLEAR_DISCARDED_BLOCKS (true)

extern uint32_t             __cache_fits_[1 / (OCMC_SIZE >= (1u << CACHE_SIZE_LOG2) - 1u)];

void __iomem               *cache_io             = NULL;
void __iomem               *buffr_io             = NULL;
static u8                   init_done            = 0u;
static u8                   error_detected       = 0u;
struct SharedMem           *shared_mem           = NULL;
struct IVTraceInp          *buffr_mem            = NULL;
uint32_t                    cache_block_idx_head = IDX_OUT_OF_BOUND >> CACHE_BLOCK_SAMPLES_LOG2;
uint32_t                    cache_block_idx_tail = IDX_OUT_OF_BOUND >> CACHE_BLOCK_SAMPLES_LOG2;
uint32_t                    cache_block_fill_lvl = 0u;
uint32_t                    flags_local[CACHE_U32_FLAGS_N];

/* Timer-system for cache-updates */
static enum hrtimer_restart update_callback(struct hrtimer *timer_for_restart);
struct hrtimer              update_timer;
#define DELAY_TIMER ns_to_ktime(CACHE_BLOCK_SAMPLES_N *SAMPLE_INTERVAL_NS - 1000000u)


void ocmc_cache_init(void)
{
    const uint64_t ts_now = ktime_get_real();
    if (init_done)
    {
        printk(KERN_ERR "shprd.cache: ocmc-cache init requested -> can't init twice!");
        return;
    }
    if (pru_shared_mem_io == NULL)
    {
        printk(KERN_ERR "shprd.cache: cache needs shared-mem of PRU but got NULL");
        return;
    }
    shared_mem = (struct SharedMem *) pru_shared_mem_io;

    /* Maps the memory in OCMC, used as cache for PRU */
    cache_io   = ioremap_nocache(OCMC_BASE_ADDR, OCMC_SIZE);
    if (cache_io == NULL)
    {
        printk(KERN_ERR "shprd.cache: OCMC not properly mapped");
        return;
    }

    /* map physical RAM address (special case that fails with ioremap()) */
    buffr_io = memremap((uint32_t) shared_mem->buffer_iv_inp_ptr, sizeof(struct IVTraceInp),
                        MEMREMAP_WB);
    if (buffr_io == NULL)
    {
        printk(KERN_ERR "shprd.cache: BUF_IV_INP not properly mapped");
        return;
    }
    buffr_mem = (struct IVTraceInp *) buffr_io;

    ocmc_cache_reset();

    printk(KERN_INFO "shprd.cache: OCMC initialized @ 0x%x, size = %d bytes",
           (uint32_t) OCMC_BASE_ADDR, OCMC_SIZE);
    printk(KERN_INFO "shprd.cache:     input-buffer @ 0x%x, size = %d bytes",
           (uint32_t) shared_mem->buffer_iv_inp_ptr, sizeof(struct IVTraceInp));

    /* timer for updates */
    hrtimer_init(&update_timer, CLOCK_REALTIME, HRTIMER_MODE_ABS);
    update_timer.function = &update_callback;
    hrtimer_start(&update_timer, ts_now + DELAY_TIMER, HRTIMER_MODE_ABS);

    init_done = 1u;
    printk(KERN_INFO "shprd.cache: -> %u cache-blocks with %u ivsamples each for %u us",
           CACHE_BLOCKS_N, CACHE_BLOCK_SAMPLES_N,
           CACHE_BLOCK_SAMPLES_N * SAMPLE_INTERVAL_NS / 1000u);
}

void ocmc_cache_exit(void)
{
    if (update_timer.base != NULL) hrtimer_cancel(&update_timer);

    if (cache_io != NULL)
    {
        iounmap(cache_io);
        cache_io = NULL;
    }
    if (buffr_io != NULL)
    {
        memunmap(buffr_io);
        buffr_io = NULL;
    }
    init_done = 0u;
    printk(KERN_INFO "shprd.cache: ocmc-cache exited");
}

void ocmc_cache_reset(void)
{
    /* what is done: invalidate indizes, empty fill-level, clear cache, */
    cache_block_idx_head = IDX_OUT_OF_BOUND >> CACHE_BLOCK_SAMPLES_LOG2;
    cache_block_idx_tail = IDX_OUT_OF_BOUND >> CACHE_BLOCK_SAMPLES_LOG2;
    cache_block_fill_lvl = 0u;
    memset_io(cache_io, 0u, OCMC_SIZE); // u8-based operation
    shared_mem->buffer_iv_inp_sys_idx = IDX_OUT_OF_BOUND;
    memset(&flags_local[0], 0u, 4 * CACHE_U32_FLAGS_N);
    memset_io(&shared_mem->cache_flags[0], 0u, 4 * CACHE_U32_FLAGS_N);
    error_detected = 0u;
}

uint32_t ocmc_cache_add(uint32_t block_idx)
{
    /* refill one block if there is space for in cache */
    const uint32_t flag_idx  = block_idx >> 5u;
    const uint32_t flag_mask = 1u << (block_idx & 0x1Fu);
    uint32_t       cache_offset;
    uint32_t       buffer_offset;

    if (block_idx >= BUFFER_BLOCKS_N) return 0u;
    // printk(KERN_INFO "shprd.cache: mk %d, flag i%d m%d", block_idx, flag_idx, flag_mask);
    /* copy from buffer to cache */
    cache_offset = (block_idx & CACHE_BLOCK_IDX_MASK)
                   << (CACHE_BLOCK_SAMPLES_LOG2 + IV_SAMPLE_SIZE_LOG2);
    buffer_offset = block_idx << (CACHE_BLOCK_SAMPLES_LOG2 + IV_SAMPLE_SIZE_LOG2);
    // note: no mask applied for buffer as first return-check handles range
    memcpy_toio(((uint8_t *) cache_io) + cache_offset,
                ((uint8_t *) buffr_mem->sample) + buffer_offset, CACHE_BLOCK_SIZE);

    /* update cache-flags */
    flags_local[flag_idx] |= flag_mask;
    shared_mem->cache_flags[flag_idx] = flags_local[flag_idx];

    return 1u;
}

uint32_t ocmc_cache_remove(uint32_t block_idx)
{
    /* discard a cached block */
    const uint32_t flag_idx  = block_idx >> 5u;
    const uint32_t flag_mask = 1u << (block_idx & 0x1Fu);
    uint32_t       cache_offset;

    if (block_idx >= BUFFER_BLOCKS_N) return 0u;
    //printk(KERN_INFO "shprd.cache: rm %d, flag i%d m%d", block_idx, flag_idx, flag_mask);
    /* update cache-flags */
    flags_local[flag_idx] &= ~flag_mask;
    shared_mem->cache_flags[flag_idx] = flags_local[flag_idx];

    /* zero cache-block, optional in theory */
    if (CLEAR_DISCARDED_BLOCKS)
    {
        cache_offset = (block_idx & CACHE_BLOCK_IDX_MASK)
                       << (CACHE_BLOCK_SAMPLES_LOG2 + IV_SAMPLE_SIZE_LOG2);
        memset_io(((uint8_t *) cache_io) + cache_offset, 0u, CACHE_BLOCK_SIZE);
    }

    return 1u;
}


void ocmc_cache_update(void)
{
    /* Manages cache to shorten read-latency for PRU.

	-> cache should always be ahead of PRUs read-pointers

	pru_read_index A		SHARED_MEM.buffer_iv_inp_idx [PRU-INTERNAL]
	pru_read_index B		IVTraceInp.idx_pru	[public, written by PRU]
	python_write_index A	IVTraceInp.idx_sys	[written by Py]
	python_write_index B	SHARED_MEM.buffer_iv_inp_sys_idx [kMod to Pru]
	cache
		-> is IDX_OUT_OF_BOUND when empty
	TODO: there should only be one per access
    */

    uint32_t idx_read, idx_write, head_next;

    if (buffr_mem->idx_sys >= BUFFER_IV_INP_SAMPLES_N) return;

    /*  Read-path Shortcut for PRU */
    shared_mem->buffer_iv_inp_sys_idx = buffr_mem->idx_sys;

    // calculate current external positions
    idx_read                          = buffr_mem->idx_pru >> CACHE_BLOCK_SAMPLES_LOG2;
    idx_write                         = buffr_mem->idx_sys >> CACHE_BLOCK_SAMPLES_LOG2;

    /* Cache Cleanup */
    if ((idx_read != cache_block_idx_tail) && (cache_block_fill_lvl > 0u))
    {
        cache_block_fill_lvl -= ocmc_cache_remove(cache_block_idx_tail);
        if (cache_block_idx_tail++ >= BUFFER_BLOCKS_N) { cache_block_idx_tail = 0u; }
    }

    /* is cache full? */
    if (cache_block_fill_lvl >= CACHE_BLOCKS_N) return;

    /* Cache Fill */
    head_next = cache_block_idx_head + 1u;
    if (head_next >= BUFFER_BLOCKS_N) { head_next = 0u; }

    if (head_next != idx_write)
    {
        cache_block_fill_lvl += ocmc_cache_add(head_next);
        cache_block_idx_head = head_next;
    }

    /* report out-of-bound read-index ONCE */
    if ((error_detected == 0u) && (idx_read < BUFFER_BLOCKS_N) &&
        (cache_block_idx_tail < BUFFER_BLOCKS_N) && (cache_block_idx_head < BUFFER_BLOCKS_N))
    {
        if (cache_block_idx_head >= cache_block_idx_tail)
        {
            /* normal usecase, head in front of tail */
            if ((idx_read < cache_block_idx_tail) || (idx_read > cache_block_idx_head))
            {
                printk(KERN_ERR "shprd.cache: pru index (read block %d) outside of cache [%d, %d] ",
                       idx_read, cache_block_idx_tail, cache_block_idx_head);
                error_detected = 1u;
            }
        }
        else
        {
            /* head wrapped, tail not */
            if ((idx_read < cache_block_idx_tail) && (idx_read > cache_block_idx_head))
            {
                printk(KERN_ERR "shprd.cache: pru index (read block %d) outside of cache [%d, %d] ",
                       idx_read, cache_block_idx_tail, cache_block_idx_head);
                error_detected = 1u;
            }
        }
    }

    //printk(KERN_INFO "shprd.cache: idx [%d, %d] %d", cache_block_idx_tail, cache_block_idx_head, cache_block_fill_lvl);
}

enum hrtimer_restart update_callback(struct hrtimer *timer_for_restart)
{
    const uint64_t ts_now = ktime_get_real();

    ocmc_cache_update();
    hrtimer_forward(timer_for_restart, ts_now, DELAY_TIMER);

    return HRTIMER_RESTART;
}

/* TODO: replacec deprecated commands
ioread32(pru_shared_mem_io + offsetof(struct SharedMem, buffer_iv_inp_ptr))
iowrite32(mode, pru_shared_mem_io + kobj_attr_wrapped->val_offset);
memcpy_toio(pru_shared_mem_io + offset_msg, msg, sizeof(struct ProtoMsg));
memcpy_fromio(msg, pru_shared_mem_io + offset_msg, sizeof(struct ProtoMsg));

memset_io(address, value, count);
memcpy_fromio(dest, source, num);
memcpy_toio(dest, source, num);
*/
