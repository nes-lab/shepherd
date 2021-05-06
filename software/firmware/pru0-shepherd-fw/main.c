#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include <pru_cfg.h>
#include <pru_iep.h>
#include <rsc_types.h>

#include "iep.h"

#include "stdint_fast.h"
#include "gpio.h"
#include "intc.h"
#include "resource_table_def.h"
#include "simple_lock.h"

#include "commons.h"
#include "hw_config.h"
#include "ringbuffer.h"
#include "sampling.h"
#include "shepherd_config.h"
#include "virtual_source.h"

/* Used to signal an invalid buffer index */
#define NO_BUFFER 	(0xFFFFFFFF)

// alternative message channel specially dedicated for errors
static void send_status(volatile struct SharedMem *const shared_mem, enum MsgType type, const uint32_t value)
{
	// do not care for sent-status, newest error wins IF different from previous
	if (!((shared_mem->pru1_msg_error.type == type) && (shared_mem->pru1_msg_error.value == value)))
	{
		shared_mem->pru0_msg_error.unread = 0u;
		shared_mem->pru0_msg_error.type = type;
		shared_mem->pru0_msg_error.value = value;
		shared_mem->pru0_msg_error.id = MSG_TO_KERNEL;
		// NOTE: always make sure that the unread-flag is activated AFTER payload is copied
		shared_mem->pru0_msg_error.unread = 1u;
	}
	if (type >= 0xE0) __delay_cycles(200U/TIMER_TICK_NS); // 200 ns
}

// send returns a 1 on success
static bool_ft send_message(volatile struct SharedMem *const shared_mem, enum MsgType type, const uint32_t value)
{
	if (shared_mem->pru0_msg_outbox.unread == 0)
	{
		shared_mem->pru0_msg_outbox.type = type;
		shared_mem->pru0_msg_outbox.value = value;
		shared_mem->pru0_msg_outbox.id = MSG_TO_KERNEL;
		// NOTE: always make sure that the unread-flag is activated AFTER payload is copied
		shared_mem->pru0_msg_outbox.unread = 1u;
		return 1;
	}
	/* Error occurs if kernel was not able to handle previous message in time */
	send_status(shared_mem, MSG_ERR_BACKPRESSURE, 0);
	return 0;
}

// only one central hub should receive, because a message is only handed out once
static bool_ft receive_message(volatile struct SharedMem *const shared_mem, struct ProtoMsg *const msg_container)
{
	if (shared_mem->pru0_msg_inbox.unread >= 1)
	{
		if (shared_mem->pru0_msg_inbox.id == MSG_TO_PRU)
		{
			*msg_container = shared_mem->pru0_msg_inbox;
			shared_mem->pru0_msg_inbox.unread = 0;
			return 1;
		}
		// send mem_corruption warning
		send_status(shared_mem, MSG_ERR_MEMCORRUPTION, 0);
	}
	return 0;
}


static uint32_t handle_buffer_swap(volatile struct SharedMem *const shared_mem, struct RingBuffer *const free_buffers_ptr,
			  struct SampleBuffer *const buffers_far, const uint32_t current_buffer_idx, const uint32_t analog_sample_idx)
{
	uint32_t next_buffer_idx;
	uint8_t tmp_idx;
	struct SampleBuffer * next_buffer;

	/* Fetch and prepare new buffer from ring */
	if (ring_get(free_buffers_ptr, &tmp_idx) > 0) {
		next_buffer_idx = (uint32_t)tmp_idx;
        	next_buffer = buffers_far + next_buffer_idx;
		next_buffer->timestamp_ns = shared_mem->next_buffer_timestamp_ns;
		shared_mem->last_sample_timestamp_ns = shared_mem->next_buffer_timestamp_ns;

		if (shared_mem->next_buffer_timestamp_ns == 0)
		{
			/* debug-output for a wrong timestamp */
			send_status(shared_mem, MSG_ERR_TIMESTAMP, 0);
		}
	} else {
		next_buffer_idx = NO_BUFFER;
		send_status(shared_mem, MSG_ERR_NOFREEBUF, 0);
	}

	/* Lock access to gpio_edges structure to allow swap without inconsistency */
	simple_mutex_enter(&shared_mem->gpio_edges_mutex);

	if (next_buffer_idx != NO_BUFFER)
	{
		shared_mem->gpio_edges = &next_buffer->gpio_edges;
		shared_mem->gpio_edges->idx = 0;
	}
	else
	{
		shared_mem->gpio_edges = NULL;
	}

	simple_mutex_exit(&shared_mem->gpio_edges_mutex);

	/* If we had a valid buffer, return it to host */
	if (current_buffer_idx != NO_BUFFER)
	{
		(buffers_far + current_buffer_idx)->len = analog_sample_idx; // TODO: could be removed in future, not possible by design
		send_message(shared_mem, MSG_BUF_FROM_PRU, current_buffer_idx);
	}

	return next_buffer_idx;
}


static bool_ft handle_kernel_com(volatile struct SharedMem *const shared_mem, struct RingBuffer *const free_buffers_ptr)
{
	struct ProtoMsg msg_in;

	if (receive_message(shared_mem, &msg_in) == 0)
		return 1u;

	if ((shared_mem->shepherd_mode == MODE_DEBUG) && (shared_mem->shepherd_state == STATE_RUNNING))
	{
        	uint32_t res;
		switch (msg_in.type) {
		case MSG_DBG_ADC:
			res = sample_dbg_adc(msg_in.value);
			send_message(shared_mem, MSG_DBG_ADC, res);
			return 1u;

		case MSG_DBG_DAC:
			sample_dbg_dac(msg_in.value);
			return 1u;

		case MSG_DBG_GPI:
			send_message(shared_mem,MSG_DBG_GPI, shared_mem->gpio_pin_state);
			return 1U;

		default:
			send_message(shared_mem,MSG_ERR_INVLDCMD, msg_in.type);
			return 0U;
		}
	} else
	{
		// most common and important msg first
		if (msg_in.type == MSG_BUF_FROM_HOST) {
			ring_put(free_buffers_ptr, (uint8_t)msg_in.value);
			return 1U;
		} else if ((msg_in.type == MSG_TEST) && (msg_in.value == 1)) {
			// pipeline-test for msg-system
			send_message(shared_mem,MSG_TEST, msg_in.value);
		} else if ((msg_in.type == MSG_TEST) && (msg_in.value == 2)) {
			// pipeline-test for msg-system
			send_status(shared_mem, MSG_TEST, msg_in.value);
		} else {
			send_message(shared_mem,MSG_ERR_INVLDCMD, msg_in.type);
		}
	}
	return 0u;
}

void event_loop(volatile struct SharedMem *const shared_mem,
		struct RingBuffer *const free_buffers_ptr,
		struct SampleBuffer *const buffers_far)
{
	uint32_t sample_buf_idx = NO_BUFFER;
	enum ShepherdMode shepherd_mode = (enum ShepherdMode)shared_mem->shepherd_mode;
	uint32_t iep_tmr_cmp_sts = 0;

	while (1)
	{
		// take a snapshot of current triggers until something happens -> ensures prioritized handling
		// edge case: sample0 @cnt=0, cmp0&1 trigger, but cmp0 needs to get handled before cmp1
		// NOTE: pru1 manages the irq, but pru0 reacts to it directly -> less jitter
		while (!(iep_tmr_cmp_sts = iep_get_tmr_cmp_sts())); // read iep-reg -> 12 cycles, 60 ns

		// Pretrigger for extra low jitter and up-to-date samples, ADCs will be triggered to sample on rising edge
		if (iep_tmr_cmp_sts & IEP_CMP1_MASK)
		{
			GPIO_OFF(SPI_CS_ADCs_MASK);
			// determine minimal low duration for starting sampling -> datasheet not clear, but 15-50 ns could be enough
			__delay_cycles(100 / 5);
			GPIO_ON(SPI_CS_ADCs_MASK);
			// TODO: look at asm-code, is there still potential for optimization?
			// TODO: make sure that 1 us passes before trying to get that value
		}

		// Activate new Buffer-Cycle & Ensure proper execution order on pru1 -> cmp0_event (E2) must be handled before cmp1_event (E3)!
		if (iep_tmr_cmp_sts & IEP_CMP0_MASK)
		{
			/* Clear Timer Compare 0 and forward it to pru1 */
			GPIO_TOGGLE(DEBUG_PIN1_MASK);
			shared_mem->cmp0_trigger_for_pru1 = 1u;
			iep_clear_evt_cmp(IEP_CMP0); // CT_IEP.TMR_CMP_STS.bit0
			/* prepare a new buffer-cycle */
			shared_mem->analog_sample_counter = 0u;
			GPIO_TOGGLE(DEBUG_PIN1_MASK);
		}

		// Sample, swap buffer and receive messages
		if (iep_tmr_cmp_sts & IEP_CMP1_MASK)
		{
			/* Clear Timer Compare 1 and forward it to pru1 */
			shared_mem->cmp1_trigger_for_pru1 = 1u;
			iep_clear_evt_cmp(IEP_CMP1); // CT_IEP.TMR_CMP_STS.bit1

			/* The actual sampling takes place here */
			if ((sample_buf_idx != NO_BUFFER) && (shared_mem->analog_sample_counter < ADC_SAMPLES_PER_BUFFER))
			{
				GPIO_ON(DEBUG_PIN0_MASK);
				sample(buffers_far + sample_buf_idx, shared_mem->analog_sample_counter, shepherd_mode);
				GPIO_OFF(DEBUG_PIN0_MASK);
			}
			shared_mem->analog_sample_counter++;

			if (shared_mem->analog_sample_counter == ADC_SAMPLES_PER_BUFFER)
			{
				/* Did the Linux kernel module ask for reset? */
				if (shared_mem->shepherd_state == STATE_RESET) return;

				/* PRU tries to exchange a full buffer for a fresh one if measurement is running */
				if ((shared_mem->shepherd_state == STATE_RUNNING) &&
				    (shared_mem->shepherd_mode != MODE_DEBUG))
				{
					sample_buf_idx = handle_buffer_swap(shared_mem, free_buffers_ptr, buffers_far, sample_buf_idx,
									    shared_mem->analog_sample_counter);
					GPIO_TOGGLE(DEBUG_PIN1_MASK); // NOTE: desired user-feedback
				}
			}
			else
			{
				/* only handle kernel-communications if this is not the last sample */
				GPIO_ON(DEBUG_PIN0_MASK);
				handle_kernel_com(shared_mem, free_buffers_ptr);
                		GPIO_OFF(DEBUG_PIN0_MASK);
			}
		}
	}
}

void main(void)
{
	GPIO_OFF(DEBUG_PIN0_MASK | DEBUG_PIN1_MASK);
	static struct RingBuffer free_buffers;

	/*
	 * The shared mem is dynamically allocated and we have to inform user space
	 * about the address and size via sysfs, which exposes parts of the
	 * shared_mem structure.
	 * Do this initialization early! The kernel module relies on it.
	 */
	volatile struct SharedMem *const shared_memory = (volatile struct SharedMem *)PRU_SHARED_MEM_STRUCT_OFFSET;

	// Initialize struct-Members Part A, must come first - this blocks PRU1!
	shared_memory->cmp0_trigger_for_pru1 = 0u; // Reset Token-System to init-values
	shared_memory->cmp1_trigger_for_pru1 = 0u;

	// Initialize all struct-Members Part B
	shared_memory->mem_base_addr = resourceTable.shared_mem.pa;
	shared_memory->mem_size = resourceTable.shared_mem.len;

	shared_memory->n_buffers = RING_SIZE;
	shared_memory->samples_per_buffer = ADC_SAMPLES_PER_BUFFER;
	shared_memory->buffer_period_ns = BUFFER_PERIOD_NS;

	shared_memory->dac_auxiliary_voltage_raw = 0u;
	shared_memory->shepherd_state = STATE_IDLE;
	shared_memory->shepherd_mode = MODE_HARVEST;  // TODO: is this the the error for "wrong state"?

	shared_memory->last_sample_timestamp_ns = 0u;
	shared_memory->next_buffer_timestamp_ns = 0u;
	shared_memory->analog_sample_counter = 0u;
	shared_memory->gpio_edges = NULL;

	/* this init is nonsense, but testable for byteorder and proper values */
	shared_memory->calibration_settings = (struct Calibration_Config){
		.adc_current_factor_nA_n8=255u, .adc_current_offset_nA=-1,
		.dac_voltage_inv_factor_uV_n20=254u, .dac_voltage_offset_uV=-2};

	vsource_struct_init(&shared_memory->virtsource_settings);

	shared_memory->pru1_sync_outbox = (struct ProtoMsg){.id =0u, .unread =0u, .type =MSG_NONE, .value=TIMER_BASE_PERIOD};
	shared_memory->pru1_sync_inbox = (struct SyncMsg){
		.id =0u,
		.unread =0u,
		.type =MSG_NONE,
		.buffer_block_period=TIMER_BASE_PERIOD,
		.analog_sample_period=TIMER_BASE_PERIOD/ADC_SAMPLES_PER_BUFFER,
		.compensation_steps=0u,
		.next_timestamp_ns=0u};
	shared_memory->pru1_msg_error = (struct ProtoMsg){.id =0u, .unread =0u, .type =MSG_NONE};

	shared_memory->pru0_msg_outbox = (struct ProtoMsg){.id =0u, .unread =0u, .type =MSG_NONE};
	shared_memory->pru0_msg_inbox = (struct ProtoMsg){.id =0u, .unread =0u, .type =MSG_NONE};
	shared_memory->pru0_msg_error = (struct ProtoMsg){.id =0u, .unread =0u, .type =MSG_NONE};

	/*
	 * The dynamically allocated shared DDR RAM holds all the buffers that
	 * are used to transfer the actual data between us and the Linux host.
	 * This memory is requested from remoteproc via a carveout resource request
	 * in our resourcetable
	 */
	struct SampleBuffer *const buffers_far = (struct SampleBuffer *)resourceTable.shared_mem.pa;

	/* Allow OCP master port access by the PRU so the PRU can read external memories */
	CT_CFG.SYSCFG_bit.STANDBY_INIT = 0;

	/* allow PRU1 to enter event-loop */
	shared_memory->cmp0_trigger_for_pru1 = 1u;

reset:
	send_message(shared_memory, MSG_STATUS_RESTARTING_ROUTINE, 100);

	ring_init(&free_buffers);

	GPIO_ON(DEBUG_PIN0_MASK | DEBUG_PIN1_MASK);
	sample_init(shared_memory);
	GPIO_OFF(DEBUG_PIN0_MASK | DEBUG_PIN1_MASK);

	shared_memory->gpio_edges = NULL;

	shared_memory->shepherd_state = STATE_IDLE;
	/* Make sure the mutex is clear */
	simple_mutex_exit(&shared_memory->gpio_edges_mutex);

	event_loop(shared_memory, &free_buffers, buffers_far);
	goto reset;
}
