#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <pru_cfg.h>
#include <pru_intc.h>
#include <pru_iep.h>
#include <gpio.h>

#include "iep.h"
#include "intc.h"

#include "resource_table.h"
#include "commons.h"
#include "shepherd_config.h"
#include "stdint_fast.h"
#include "debug_routines.h"

/* The Arm to Host interrupt for the timestamp event is mapped to Host interrupt 0 -> Bit 30 (see resource_table.h) */
#define HOST_INT_TIMESTAMP_MASK (1U << 30U)
// TODO: is bit r31.31 still important?

// both pins have a LED
#define DEBUG_PIN0_MASK 	BIT_SHIFT(P8_28)
#define DEBUG_PIN1_MASK 	BIT_SHIFT(P8_30)

#define GPIO_BATOK 		BIT_SHIFT(P8_29)
#define GPIO_BATOK_POS		(9u)

#define GPIO_MASK		(0x03FF)

#define SANITY_CHECKS		(0)	// warning: costs performance, but is helpful for dev / debugging

/* overview for pin-mirroring - HW-Rev2.3

pru_reg     name            BB_pin	sys_pin
r31_00      TARGET_GPIO0    P8_45	P8_14, g0[14]
r31_01      TARGET_GPIO1    P8_46	P8_17, g0[27]
r31_02      TARGET_GPIO2    P8_43	P8_16, g1[14]
r31_03      TARGET_GPIO3    P8_44	P8_15, g1[15]
r31_04      TARGET_GPIO4    P8_41	P8_26, g1[29]
r31_05      TARGET_GPIO5    P8_42	P8_36, g2[16]
r31_06      TARGET_GPIO6    P8_39	P8_34, g2[17]
r31_07      TARGET_UART_RX  P8_40	P9_26, g0[14]
r31_08      TARGET_UART_TX  P8_27	P9_24, g0[15]
r30_09/out  TARGET_BAT_OK   P8_29	-

Note: this table is copied (for hdf5-reference) in commons.py
*/

enum SyncState {
	IDLE,
	REPLY_PENDING
};

// alternative message channel specially dedicated for errors
static void send_status(volatile struct SharedMem *const shared_mem, enum MsgType type, const uint32_t value)
{
	// do not care for sent-status, newest error wins IF different from previous
	if (!((shared_mem->pru1_msg_error.type == type) && (shared_mem->pru1_msg_error.value[0] == value)))
	{
		shared_mem->pru1_msg_error.unread = 0u;
		shared_mem->pru1_msg_error.type = type;
		shared_mem->pru1_msg_error.value[0] = value;
		shared_mem->pru1_msg_error.id = MSG_TO_KERNEL;
		// NOTE: always make sure that the unread-flag is activated AFTER payload is copied
		shared_mem->pru1_msg_error.unread = 1u;
	}
	if (type >= 0xE0) __delay_cycles(200u/TIMER_TICK_NS); // 200 ns
}


static inline bool_ft receive_sync_reply(volatile struct SharedMem *const shared_mem, struct SyncMsg *const msg)
{
	if (shared_mem->pru1_sync_inbox.unread >= 1)
	{
		if (shared_mem->pru1_sync_inbox.id != MSG_TO_PRU)
		{
			/* Error occurs if something writes over boundaries */
			send_status(shared_mem, MSG_ERR_MEMCORRUPTION, 0);
			return 0;
		}
		if (shared_mem->pru1_sync_inbox.type == MSG_TEST)
		{
			// pipeline-test for msg-system
			shared_mem->pru1_sync_inbox.unread = 0;
			send_status(shared_mem, MSG_TEST, shared_mem->pru1_sync_inbox.buffer_block_period);
			return 0;
		}
		// NOTE: do not overwrite external msg without thinking twice! sync-routine relies on that content
		*msg = shared_mem->pru1_sync_inbox; // TODO: faster to copy only the needed payload
		shared_mem->pru1_sync_inbox.unread = 0;

#if (SANITY_CHECKS > 0)
		// TODO: move this to kernel
		if (msg->buffer_block_period > TIMER_BASE_PERIOD + (TIMER_BASE_PERIOD >> 3)) {
			send_status(shared_mem, MSG_ERR_VALUE, 11); //"Recv_CtrlReply -> buffer_block_period too high");
		}
		if (msg->buffer_block_period < TIMER_BASE_PERIOD - (TIMER_BASE_PERIOD >> 3)) {
			send_status(shared_mem, MSG_ERR_VALUE, 12); //"Recv_CtrlReply -> buffer_block_period too low");
		}
		if (msg->analog_sample_period > SAMPLE_PERIOD + 100) {
			send_status(shared_mem, MSG_ERR_VALUE, 13); //"Recv_CtrlReply -> analog_sample_period too high");
		}
		if (msg->analog_sample_period < SAMPLE_PERIOD - 100) {
			send_status(shared_mem, MSG_ERR_VALUE, 14); //"Recv_CtrlReply -> analog_sample_period too low");
		}
		if (msg->compensation_steps > ADC_SAMPLES_PER_BUFFER) {
			send_status(shared_mem, MSG_ERR_VALUE, 15); //"Recv_CtrlReply -> compensation_steps too high");
		}

		static uint64_t prev_timestamp_ns = 0;
		const uint64_t time_diff = msg->next_timestamp_ns - prev_timestamp_ns;
		prev_timestamp_ns = msg->next_timestamp_ns;
		if ((time_diff != BUFFER_PERIOD_NS) && (prev_timestamp_ns > 0)) {
			if (msg->next_timestamp_ns == 0)
				send_status(shared_mem, MSG_ERR_VALUE, 16); // "Recv_CtrlReply -> next_timestamp_ns is zero");
			else if (time_diff > BUFFER_PERIOD_NS + 5000000)
				send_status(shared_mem, MSG_ERR_VALUE, 17); // "Recv_CtrlReply -> next_timestamp_ns is > 105 ms");
			else if (time_diff < BUFFER_PERIOD_NS - 5000000)
				send_status(shared_mem, MSG_ERR_VALUE, 18); // "Recv_CtrlReply -> next_timestamp_ns is < 95 ms");
			else
				send_status(shared_mem, MSG_ERR_VALUE, 19); // "Recv_CtrlReply -> timestamp-jump was not 100 ms");
		}
#endif
		return 1;
	}
	return 0;
}

// emits a 1 on success
// pru1_sync_outbox: (future opt.) needs to have special config set: identifier=MSG_TO_KERNEL and unread=1
static inline bool_ft send_sync_request(volatile struct SharedMem *const shared_mem, const struct ProtoMsg *const msg)
{
	if (shared_mem->pru1_sync_outbox.unread == 0)
	{
		shared_mem->pru1_sync_outbox = *msg;
		shared_mem->pru1_sync_outbox.id = MSG_TO_KERNEL;
		// NOTE: always make sure that the unread-flag is activated AFTER payload is copied
		shared_mem->pru1_sync_outbox.unread = 1u;
		return 1;
	}
	/* Error occurs if PRU was not able to handle previous message in time */
	send_status(shared_mem, MSG_ERR_BACKPRESSURE, 0);
	return 0;
}

/*
 * Here, we sample the the GPIO pins from a connected sensor node. We repeatedly
 * poll the state via the R31 register and keep the last state in a static
 * variable. Once we detect a change, the new value (V1=4bit, V2=10bit) is written to the
 * corresponding buffer (which is managed by PRU0). The tricky part is the
 * synchronization between the PRUs to avoid inconsistent state, while
 * minimizing sampling delay
 */
static inline void check_gpio(volatile struct SharedMem *const shared_mem, const uint32_t last_sample_ticks)
{
	static uint32_t prev_gpio_status = 0x00;

	/*
	* Only continue if shepherd is running and PRU0 actually provides a buffer
	* to write to.
	*/
	if ((shared_mem->shepherd_state != STATE_RUNNING) ||
	    (shared_mem->gpio_edges == NULL)) {
		prev_gpio_status = 0x00;
		shared_mem->gpio_pin_state = read_r31() & GPIO_MASK;
		return;
	}
	else if (shared_mem->vsource_skip_gpio_logging)
	{
		return;
	}

	// batOK is on r30 (output), but that does not mean it is in R31
	// -> workaround: splice in shared_mem->vsource_batok_pin_value
	const uint32_t gpio_status = (read_r31() | (shared_mem->vsource_batok_pin_value << GPIO_BATOK_POS)) & GPIO_MASK;
	const uint32_t gpio_diff = gpio_status ^ prev_gpio_status;

	prev_gpio_status = gpio_status;

	if (gpio_diff > 0)
	{
		DEBUG_GPIO_STATE_3;
		// local copy reduces reads to far-ram to current minimum
		const uint32_t cIDX = shared_mem->gpio_edges->idx;

		/* Each buffer can only store a limited number of events */
		if (cIDX >= MAX_GPIO_EVT_PER_BUFFER) return;

		/* Ticks since we've taken the last sample */
		const uint32_t ticks_since_last_sample = CT_IEP.TMR_CNT - last_sample_ticks;
		/* Calculate final timestamp of gpio event */
		const uint64_t gpio_timestamp_ns = shared_mem->last_sample_timestamp_ns + TIMER_TICK_NS * ticks_since_last_sample;

		simple_mutex_enter(&shared_mem->gpio_edges_mutex);
		shared_mem->gpio_edges->timestamp_ns[cIDX] = gpio_timestamp_ns;
		shared_mem->gpio_edges->bitmask[cIDX] = (uint16_t)gpio_status;
		shared_mem->gpio_edges->idx = cIDX + 1;
		simple_mutex_exit(&shared_mem->gpio_edges_mutex);
	}
}


/* TODO: update comments, seem outdated
 * The firmware for synchronization/sample timing is based on a simple
 * event loop. There are three events: 1) Interrupt from Linux kernel module
 * 2) Local IEP timer wrapped 3) Local IEP timer compare for sampling
 *
 * Event 1:
 * The kernel module periodically timestamps its own clock and immediately
 * triggers an interrupt to PRU1. On reception of that interrupt we have
 * to timestamp our local IEP clock. We then send the local timestamp to the
 * kernel module as an RPMSG message. The kernel module runs a PI control loop
 * that minimizes the phase shift (and frequency deviation) by calculating a
 * correction factor that we apply to the base period of the IEP clock. This
 * resembles a Phase-Locked-Loop system. The kernel module sends the resulting
 * correction factor to us as an RPMSG. Ideally, Event 1 happens at the same
 * time as Event 2, i.e. our local clock should wrap at exactly the same time
 * as the Linux host clock. However, due to phase shifts and kernel timer
 * jitter, the two events typically happen with a small delay and in arbitrary
 * order. However, we would
 *
 * Event 2:
 *
 * Event 3:
 * This is the main sample trigger that is used to trigger the actual sampling
 * on PRU0 by raising an interrupt. After every sample, we have to forward
 * the compare value, taking into account the current sampling period
 * (dynamically adapted by PLL). Also, we will only check for the controller
 * reply directly following this event in order to avoid sampling jitter that
 * could result from being busy with RPMSG and delaying response to the next
 * Event 3
 */

int32_t event_loop(volatile struct SharedMem *const shared_mem)
{
	uint32_t last_analog_sample_ticks = 0;

	/* Prepare message that will be received and sent to Linux kernel module */
	struct ProtoMsg sync_rqst = { .id = MSG_TO_KERNEL, .type = MSG_NONE, .unread = 0u };
	struct SyncMsg sync_repl = {
		.buffer_block_period = TIMER_BASE_PERIOD,
		.analog_sample_period = TIMER_BASE_PERIOD / ADC_SAMPLES_PER_BUFFER,
		.compensation_steps = 0u,
	};

	/* This tracks our local state, allowing to execute actions at the right time */
	enum SyncState sync_state = IDLE;

	/*
	* This holds the number of 'compensation' periods, where the sampling
	* period is increased by 1 in order to compensate for the remainder of the
	* integer udiv used to calculate the sampling period.
	*/
	uint32_t compensation_steps = sync_repl.compensation_steps;
	/*
	 * holds distribution of the compensation periods (every x samples the period is increased by 1)
	 */
	uint32_t compensation_counter = 0u;
	uint32_t compensation_increment = 0u;

	/* pru0 util monitor */
	uint32_t pru0_max_ticks_per_sample = 0u;
	uint32_t pru0_sum_ticks_for_buffer = 0u;

	/* Our initial guess of the sampling period based on nominal timer period */
	uint32_t analog_sample_period = sync_repl.analog_sample_period;
	uint32_t buffer_block_period = sync_repl.buffer_block_period;

	/* These are our initial guesses for buffer sample period */
	iep_set_cmp_val(IEP_CMP0, buffer_block_period);  // 20 MTicks -> 100 ms
	iep_set_cmp_val(IEP_CMP1, analog_sample_period); //  2 kTicks -> 10 us

	iep_enable_evt_cmp(IEP_CMP1);
	iep_clear_evt_cmp(IEP_CMP0);

	/* Clear raw interrupt status from ARM host */
	INTC_CLEAR_EVENT(HOST_PRU_EVT_TIMESTAMP);
	/* Wait for first timer interrupt from Linux host */
	while (!(read_r31() & HOST_INT_TIMESTAMP_MASK)) {};

	if (INTC_CHECK_EVENT(HOST_PRU_EVT_TIMESTAMP)) INTC_CLEAR_EVENT(HOST_PRU_EVT_TIMESTAMP);

	iep_start();

	while (1)
	{
		#if DEBUG_LOOP_EN
		debug_loop_delays(shared_mem->shepherd_state);
		#endif

		DEBUG_GPIO_STATE_1;
		check_gpio(shared_mem, last_analog_sample_ticks);
		DEBUG_GPIO_STATE_0;

		/* [Event1] Check for interrupt from Linux host to take timestamp */
		if (read_r31() & HOST_INT_TIMESTAMP_MASK)
		{
			if (!INTC_CHECK_EVENT(HOST_PRU_EVT_TIMESTAMP)) continue;

			/* Take timestamp of IEP */
			sync_rqst.value[0] = iep_get_cnt_val();
			DEBUG_EVENT_STATE_3;
			/* Clear interrupt */
			INTC_CLEAR_EVENT(HOST_PRU_EVT_TIMESTAMP);

			if (sync_state == IDLE)    sync_state = REPLY_PENDING;
			else {
				send_status(shared_mem, MSG_ERR_SYNC_STATE_NOT_IDLE, sync_state);
				return 0;
			}
			send_sync_request(shared_mem, &sync_rqst);
			DEBUG_EVENT_STATE_0;
			continue;  // for more regular gpio-sampling
		}

		/*  [Event 2] Timer compare 0 handle -> trigger for buffer swap on pru0 */
		if (shared_mem->cmp0_trigger_for_pru1)
		{
			DEBUG_EVENT_STATE_2;
			// reset trigger
			shared_mem->cmp0_trigger_for_pru1 = 0;

			/* update clock compensation of sample-trigger */
			iep_set_cmp_val(IEP_CMP1, 0);
			iep_enable_evt_cmp(IEP_CMP1);
			analog_sample_period = sync_repl.analog_sample_period;
			compensation_steps = sync_repl.compensation_steps;
			compensation_increment = sync_repl.compensation_steps;
			compensation_counter = 0;

			/* update main-loop */
			buffer_block_period = sync_repl.buffer_block_period;
			iep_set_cmp_val(IEP_CMP0, buffer_block_period);

			/* transmit pru0-util, current design puts this in fresh/next buffer */
			if (shared_mem->sample_buffer != NULL)
			{
				shared_mem->sample_buffer->pru0_sum_ticks_for_buffer = pru0_sum_ticks_for_buffer;
				shared_mem->sample_buffer->pru0_max_ticks_per_sample = pru0_max_ticks_per_sample;
				pru0_sum_ticks_for_buffer = 0;
				pru0_max_ticks_per_sample = 0;
			}

			/* more maintenance */
			last_analog_sample_ticks = 0;

			DEBUG_EVENT_STATE_0;
			continue; // for more regular gpio-sampling
		}

		/* [Event 3] Timer compare 1 handle -> trigger for analog sample on pru0 */
		if (shared_mem->cmp1_trigger_for_pru1)
		{
			/* prevent a race condition (cmp0_event has to happen before cmp1_event!) */
			if (shared_mem->cmp0_trigger_for_pru1) continue;

			DEBUG_EVENT_STATE_1;
			// reset trigger
			shared_mem->cmp1_trigger_for_pru1 = 0;

			// Update Timer-Values
			last_analog_sample_ticks = iep_get_cmp_val(IEP_CMP1);
			if (last_analog_sample_ticks > 0) // this assumes sample0 taken on cmp1==0
			{
				shared_mem->last_sample_timestamp_ns += SAMPLE_INTERVAL_NS; // TODO: should be directly done on pru0 (noncritical)
			}

			/* Forward sample timer based on current analog_sample_period*/
			uint32_t next_cmp_val = last_analog_sample_ticks + analog_sample_period;
			compensation_counter += compensation_increment; // fixed point magic
			/* If we are in compensation phase add one */
			if ((compensation_counter >= ADC_SAMPLES_PER_BUFFER) && (compensation_steps > 0)) {
				next_cmp_val += 1;
				compensation_steps--;
				compensation_counter -= ADC_SAMPLES_PER_BUFFER;
			}
			iep_set_cmp_val(IEP_CMP1, next_cmp_val);

			/* If we are waiting for a reply from Linux kernel module */
			if (receive_sync_reply(shared_mem, &sync_repl) > 0)
			{
				sync_state = IDLE;
				shared_mem->next_buffer_timestamp_ns = sync_repl.next_timestamp_ns;
			}
			DEBUG_EVENT_STATE_0;
			continue; // for more regular gpio-sampling
		}

		/* Mem-Reading for PRU0 -> this can vary from 420 - 3000 (rare) */
		if ((shared_mem->analog_sample_counter != shared_mem->analog_value_index) &&
		    (shared_mem->sample_buffer != NULL) &&
		    (shared_mem->analog_sample_counter < ADC_SAMPLES_PER_BUFFER))
		{
			DEBUG_RAMRD_STATE_1;
			const uint32_t value_index = shared_mem->analog_sample_counter;
			shared_mem->analog_value_current = shared_mem->sample_buffer->values_current[value_index];
			//if (value_index == 0u) DEBUG_RAMRD_STATE_0;
			shared_mem->analog_value_voltage = shared_mem->sample_buffer->values_voltage[value_index];
			//if (value_index == 0u) DEBUG_RAMRD_STATE_1;
			shared_mem->analog_value_index = value_index;
			DEBUG_RAMRD_STATE_0;
		}

		/* remote gpio-triggering for pru0 */
		if (shared_mem->vsource_batok_trigger_for_pru1)
		{
			if (shared_mem->vsource_batok_pin_value)
			{
				GPIO_ON(GPIO_BATOK);
				DEBUG_PGOOD_STATE_1;
			}
			else
			{
				GPIO_OFF(GPIO_BATOK);
				DEBUG_PGOOD_STATE_0;
			}
			shared_mem->vsource_batok_trigger_for_pru1 = false;
		}

		/* pru0 util monitoring */
		if (shared_mem->pru0_ticks_per_sample != 0xFFFFFFFFu)
		{
			if (shared_mem->pru0_ticks_per_sample < (1u<<20u))
			{
				if (shared_mem->pru0_ticks_per_sample > pru0_max_ticks_per_sample)
				{
					pru0_max_ticks_per_sample = shared_mem->pru0_ticks_per_sample;
				}
				pru0_sum_ticks_for_buffer += shared_mem->pru0_ticks_per_sample;
			}
			shared_mem->pru0_ticks_per_sample = 0xFFFFFFFFu;
		}
	}
}

void main(void)
{
	volatile struct SharedMem *const shared_memory = (volatile struct SharedMem *)PRU_SHARED_MEM_STRUCT_OFFSET;

    	/* Allow OCP master port access by the PRU so the PRU can read external memories */
	CT_CFG.SYSCFG_bit.STANDBY_INIT = 0;
	DEBUG_STATE_0;

	/* Enable 'timestamp' interrupt from ARM host */
	CT_INTC.EISR_bit.EN_SET_IDX = HOST_PRU_EVT_TIMESTAMP;

	/* wait until pru0 is ready */
	while(shared_memory->cmp0_trigger_for_pru1 == 0u) __delay_cycles(10);
	shared_memory->cmp0_trigger_for_pru1 = 0u;

reset:
	send_status(shared_memory, MSG_STATUS_RESTARTING_ROUTINE, 101);
	/* Make sure the mutex is clear */
	simple_mutex_exit(&shared_memory->gpio_edges_mutex);

	shared_memory->analog_value_current = 0u;
	shared_memory->analog_value_voltage = 0u;
	shared_memory->analog_value_index = 0u;

	DEBUG_STATE_0;
	iep_init();
	iep_reset();

	event_loop(shared_memory);
	goto reset;
}
