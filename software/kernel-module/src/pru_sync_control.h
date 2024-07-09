#ifndef __PRU_SYNC_CONTROL_H_
#define __PRU_SYNC_CONTROL_H_

#include "commons.h"

/**
 * Initializes snychronization procedure between our Linux clock and PRU0
 *
 * This initializes and starts the timer that fires with a period corresponding
 * to the 'buffer period' and a phase aligned with the real time. This timer
 * triggers an interrupt on PRU0
 */
int  sync_init(uint32_t timer_period_ns);
void sync_exit(void);
void sync_reset(void);

void sync_pause(void);
void sync_start(void);

/**
 * Control loop
 *
 * The controller is best described as a Phase-Locked-Loop system: The kernel
 * module runs a reference clock with phase and frequency synchronized to the
 * network-wide time-coordinator. The frequency equals the 'buffer period' and the
 * phase should be aligned to the wrap of the real time. E.g. if we have a buffer
 * period of 100ms, the timer should fire at X.1s, X.2s, X.3s and so on.
 * Our task is to copy that clock to the PRU's IEP. For this purpose, we run
 * a Linux hrtimer, that expires on the corresponding wrap of the Linux
 * CLOCK_REALTIME and we immediately trigger an interrupt on the PRU. The PRU
 * sends us its own phase. The goal of this function is to calculate
 * a 'correction factor' that is added to the IEP's frequency, such that the
 * difference between the phase of our clock and the IEP's is minimized.
 *
 * @param sync_reply fresh values for next 100ms-window
 * @param sync_rqst timed iep-counter-value that was received from PRU0
 */
int  sync_loop(struct SyncMsg *sync_reply, const struct ProtoMsg *sync_rqst);

/**
 * Synchronization data structure
 *
 * Holds dynamic info about synchronization loop. Is exposed through sysfs to
 * allow users to track state.
 */
struct sync_data_s
{
    int64_t  error_now;
    int64_t  error_pre;
    int64_t  error_dif;
    int64_t  error_sum;
    int32_t  clock_corr;
    uint32_t previous_period;
};

extern struct sync_data_s *sync_data;

#endif /* __PRU_SYNC_CONTROL_H_ */
