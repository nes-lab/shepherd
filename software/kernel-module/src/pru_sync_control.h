#ifndef __PRU_SYNC_CONTROL_H_
#define __PRU_SYNC_CONTROL_H_

/**
 * Initializes snychronization procedure between our Linux clock and PRU0
 *
 * This initializes and starts the timer that fires with a period corresponding
 * to the 'buffer period' and a phase aligned with the real time. This timer
 * triggers an interrupt on PRU0
 */
int  sync_init(uint32_t timer_period_ns);
void sync_exit(void);

#endif /* __PRU_SYNC_CONTROL_H_ */
