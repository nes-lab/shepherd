#ifndef SHEPHERD_CONFIG_H
#define SHEPHERD_CONFIG_H

/* The IEP of the PRUs is clocked with 200 MHz -> 5 nanoseconds per tick */
#define TICK_INTERVAL_NS                (5U)
#define SAMPLE_INTERVAL_NS              (10000u)
#define SAMPLE_INTERVAL_TICKS           (SAMPLE_INTERVAL_NS / TICK_INTERVAL_NS)
#define SYNC_INTERVAL_NS                (100000000u) // ~ 100ms
#define SYNC_INTERVAL_TICKS             (SYNC_INTERVAL_NS / TICK_INTERVAL_NS)
#define SAMPLES_PER_SYNC                (SYNC_INTERVAL_NS / SAMPLE_INTERVAL_NS)

/**
 * Length of buffer for storing harvest & emulation data
 */
#define BUFFER_IV_SIZE                  (1u << 20u) // 1M for ~10s
#define BUFFER_GPIO_SIZE                (1u << 20u) // 1M - similar to sum of segments before
#define BUFFER_UTIL_SIZE                (1u << 8u)  // 256
#define IDX_OUT_OF_BOUND                (0xFFFFFFFFu)

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

#endif //SHEPHERD_CONFIG_H
