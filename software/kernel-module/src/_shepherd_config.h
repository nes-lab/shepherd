#ifndef _SHEPHERD_CONFIG_H
#define _SHEPHERD_CONFIG_H

/**
* base: /lib/firmware/am335x-pru*
* sudo sh -c 'echo am335x-pru0-programmer-SWD-fw > /sys/class/remoteproc/remoteproc1/firmware'
* sudo sh -c 'echo prog-swd > /sys/shepherd/pru_firmware'
*/
#define PRU0_FW_EMU                ("am335x-pru0-shepherd-EMU-fw") /* 27 chars */
#define PRU0_FW_HRV                ("am335x-pru0-shepherd-HRV-fw")
#define PRU0_FW_PRG_SWD            ("am335x-pru0-programmer-SWD-fw") /* 29 chars */
#define PRU0_FW_PRG_SBW            ("am335x-pru0-programmer-SBW-fw")
#define PRU0_FW_SLEEP              ("am335x-pru0-fw.sleep")
#define PRU0_FW_DEFAULT            PRU0_FW_EMU
#define PRU1_FW_SLEEP              ("am335x-pru1-fw.sleep") // TODO: make use of it (for programming)
#define PRU1_FW_SHEPHERD           ("am335x-pru1-shepherd-fw")
#define PRU1_FW_DEFAULT            PRU1_FW_SHEPHERD

/**
 * Size of msg-fifo - unrelated to fifo-buffer of pru / shared mem that stores harvest & emulation data
 * this msg-fifo should be at least slightly larger though
 */
#define MSG_FIFO_SIZE              (128U)

/** *************************************************************************************
 * NOTE: below is a copy of shepherd_config.h for the pru-firmware (copy changes by hand)
 */

/* The IEP of the PRUs is clocked with 200 MHz -> 5 nanoseconds per tick */
#define TICK_INTERVAL_NS           (5U)
#define SAMPLE_INTERVAL_NS         (10000u)
#define SAMPLE_INTERVAL_TICKS      (SAMPLE_INTERVAL_NS / TICK_INTERVAL_NS)
#define SYNC_INTERVAL_NS           (100000000u) // ~ 100ms
#define SYNC_INTERVAL_TICKS        (SYNC_INTERVAL_NS / TICK_INTERVAL_NS)
#define SAMPLES_PER_SYNC           (SYNC_INTERVAL_NS / SAMPLE_INTERVAL_NS)

/**
 * Length of buffer for storing harvest & emulation data
 */
#define IV_SAMPLE_SIZE_LOG2        (3u) // 8 byte
#define BUFFER_IV_INP_SAMPLES_LOG2 (20u)

#define BUFFER_IV_INP_SAMPLES_N    (1u << BUFFER_IV_INP_SAMPLES_LOG2) // ~1M for ~10s
#define BUFFER_IV_OUT_SAMPLES_N    (1000000u)                         // 1M for ~10s
#define BUFFER_GPIO_SAMPLES_N      (2000000u)                         // ~ 2s @ 1 MHz
// -> 2M is working, >=3M fails, TODO: find sweetspot later, could reduce IV_OUT to 6s
#define BUFFER_UTIL_SAMPLES_N      (400u)
#define IDX_OUT_OF_BOUND           (0xFFFFFFFFu)

/*
 * Cache for Input-IV-Buffer
 */
#define CACHE_SIZE_LOG2            (16u)                                   // 64kByte
#define CACHE_SAMPLES_LOG2         (CACHE_SIZE_LOG2 - IV_SAMPLE_SIZE_LOG2) // 13
#define CACHE_SAMPLES_N            (1u << CACHE_SAMPLES_LOG2)              // 8192
#define CACHE_IDX_MASK             (CACHE_SAMPLES_N - 1u)

#define CACHE_BLOCKS_LOG2          (3u)                      // 8 segments
#define CACHE_BLOCKS_N             (1u << CACHE_BLOCKS_LOG2) // 8

#define CACHE_BLOCK_SAMPLES_LOG2   (CACHE_SAMPLES_LOG2 - CACHE_BLOCKS_LOG2)                 // 10
#define CACHE_BLOCK_SAMPLES_N      (1u << CACHE_BLOCK_SAMPLES_LOG2)                         // 1024
#define CACHE_BLOCK_SIZE           (1u << (CACHE_BLOCK_SAMPLES_LOG2 + IV_SAMPLE_SIZE_LOG2)) // 8192
#define CACHE_BLOCK_IDX_MASK       ((1u << CACHE_BLOCKS_LOG2) - 1u)                         // 0b111

#define BUFFER_BLOCKS_LOG2         (BUFFER_IV_INP_SAMPLES_LOG2 - CACHE_BLOCK_SAMPLES_LOG2) // 10
#define BUFFER_BLOCKS_N            (1u << BUFFER_BLOCKS_LOG2)                              // 1024
#define BUFFER_BLOCK_MASK          ((1u << BUFFER_BLOCKS_LOG2) - 1u) // 0b11_1111_1111

#define CACHE_U32_FLAGS_LOG2       (BUFFER_BLOCKS_LOG2 - 5u)    // 5
#define CACHE_U32_FLAGS_N          (1u << CACHE_U32_FLAGS_LOG2) // 32
#define CACHE_U32_FLAG_SIZE        (4u * CACHE_U32_FLAGS_N)     // 128

extern uint32_t
        __cache_fits_buffer[1 / ((1u << BUFFER_IV_INP_SAMPLES_LOG2) >= BUFFER_IV_INP_SAMPLES_N)];

/**
 * These are the system events that we use to signal events to the PRUs.
 * See the AM335x TRM Table 4-22 for a list of all events
 */
#define HOST_PRU_EVT_TIMESTAMP          (20u)

/* The SharedMem struct resides at the beginning of the PRUs shared memory */
#define PRU_SHARED_MEM_OFFSET           (0x10000u)


// Test data-containers and constants with pseudo-assertion with zero cost (if expression evaluates to 0 this causes a div0
// NOTE: name => alphanum without spaces and without ""
#define ASSERT(assert_name, expression) extern uint32_t assert_name[1 / (expression)]
#define CANARY_VALUE_U32                (0xdebac1e5ul) // read as '0-debacles'

#endif //_SHEPHERD_CONFIG_H
