#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include <pru_cfg.h>
#include <pru_iep.h>
#include <rsc_types.h>

#include "iep.h"

#include "stdint_fast.h"
#include "gpio.h"
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
// TODO: also used for status,
static void emit_error(volatile struct SharedMem *const shared_mem, enum MsgType type, const uint32_t value)
{
	//if (shared_mem->pru0_msg_error.msg_unread == 0) // do not care, newest error wins
	{
		shared_mem->pru0_msg_error.msg_type = type;
		shared_mem->pru0_msg_error.value = value;
		shared_mem->pru0_msg_error.msg_id = MSG_TO_KERNEL;
		// NOTE: always make sure that the unread-flag is activated AFTER payload is copied
		shared_mem->pru0_msg_error.msg_unread = 1u;
	}
	if (type >= 0xE0)
		__delay_cycles(1000000U/TIMER_TICK_NS); // 1 ms
}

// send returns a 1 on success
static bool_ft send_message(volatile struct SharedMem *const shared_mem, enum MsgType type, const uint32_t value)
{
	if (shared_mem->pru0_msg_outbox.msg_unread == 0)
	{
		shared_mem->pru0_msg_outbox.msg_type = type;
		shared_mem->pru0_msg_outbox.value = value;
		shared_mem->pru0_msg_outbox.msg_id = MSG_TO_KERNEL;
		// NOTE: always make sure that the unread-flag is activated AFTER payload is copied
		shared_mem->pru0_msg_outbox.msg_unread = 1u;
		return 1;
	}
	/* Error occurs if kernel was not able to handle previous message in time */
	emit_error(shared_mem, MSG_ERR_BACKPRESSURE, 0);
	return 0;
}

// only one central hub should receive, because a message is only handed out once
static bool_ft receive_message(volatile struct SharedMem *const shared_mem, struct ProtoMsg *const msg_container)
{
	if (shared_mem->pru0_msg_inbox.msg_unread >= 1)
	{
		if (shared_mem->pru0_msg_inbox.msg_id == MSG_TO_PRU)
		{
			*msg_container = shared_mem->pru0_msg_inbox;
			shared_mem->pru0_msg_inbox.msg_unread = 0;
			return 1;
		}
		// send mem_corruption warning
		emit_error(shared_mem, MSG_ERR_MEMCORRUPTION, 0);
	}
	return 0;
}


static uint32_t handle_buffer_swap(volatile struct SharedMem *const shared_mem, struct RingBuffer *const free_buffers_ptr,
			  struct SampleBuffer *const buffers_far, const uint32_t current_buffer_idx, const uint32_t analog_sample_idx)
{
	uint32_t next_buffer_idx;
	uint8_t tmp_idx;

	/* If we currently have a valid buffer, return it to host */
	// NOTE1: this must come first or else python-backend gets confused
	// NOTE2: was in mutex-state before, but it does not need to, only blocks gpio-sampling / pru1 (80% of workload is in this fn)
	// TODO: this section should be in mutex...
	if (current_buffer_idx != NO_BUFFER)
	{
		if (analog_sample_idx != ADC_SAMPLES_PER_BUFFER) // TODO: could be removed in future, not possible anymore
		{
			emit_error(shared_mem, MSG_ERR_INCMPLT, analog_sample_idx);
		}

		(buffers_far + current_buffer_idx)->len = analog_sample_idx;
		send_message(shared_mem, MSG_BUF_FROM_PRU, current_buffer_idx);
	}

	/* Lock access to gpio_edges structure to avoid inconsistency */
	simple_mutex_enter(&shared_mem->gpio_edges_mutex);

	/* Fetch new buffer from ring */
	if (ring_get(free_buffers_ptr, &tmp_idx) > 0) {
		next_buffer_idx = (uint32_t)tmp_idx;
        	struct SampleBuffer *const next_buffer = buffers_far + next_buffer_idx;
		next_buffer->timestamp_ns = shared_mem->next_buffer_timestamp_ns;
		shared_mem->last_sample_timestamp_ns = shared_mem->next_buffer_timestamp_ns;
		shared_mem->gpio_edges = &next_buffer->gpio_edges;
		shared_mem->gpio_edges->idx = 0;

		if (shared_mem->next_buffer_timestamp_ns == 0)
		{
			/* debug-output for a wrong timestamp */
			emit_error(shared_mem, MSG_ERR_TIMESTAMP, 0);
		}
	} else {
		next_buffer_idx = NO_BUFFER;
		shared_mem->gpio_edges = NULL;
		emit_error(shared_mem, MSG_ERR_NOFREEBUF, 0);
	}
	simple_mutex_exit(&shared_mem->gpio_edges_mutex);

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
		switch (msg_in.msg_type) {
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
			send_message(shared_mem,MSG_ERR_INVLDCMD, msg_in.msg_type);
			return 0U;
		}
	} else
	{
		if (msg_in.msg_type == MSG_BUF_FROM_HOST) {
			ring_put(free_buffers_ptr, (uint8_t)msg_in.value);
			return 1U;
		} else {
			send_message(shared_mem,MSG_ERR_INVLDCMD, msg_in.msg_type);
			return 0U;
		}
	}
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
		while (!(iep_tmr_cmp_sts = iep_get_tmr_cmp_sts())); // read iep-reg -> 12 cycles, 60 ns
		if (iep_tmr_cmp_sts & IEP_CMP1_MASK)
		{
			// Pretrigger for extra low jitter and up-to-date samples, ADCs will be triggered to sample on rising edge
			// TODO: look at asm-code, is there still potential for optimization?
			GPIO_OFF(SPI_CS_ADCs_MASK);
			// determine minimal low duration for starting sampling -> datasheet not clear, but 15-50 ns could be enough
			__delay_cycles(100 / 5);
			GPIO_ON(SPI_CS_ADCs_MASK);
			// TODO: make sure that 1 us passes before trying to get that value
		}

		// System to ensure proper execution order on pru1 -> cmp0_event (E2) must be handled before cmp1_event (E3)!
		if (iep_tmr_cmp_sts & IEP_CMP0_MASK)
		{
			/* Clear Timer Compare 0 and forward it to pru1 */
			shared_mem->cmp0_trigger_for_pru1 = 1;
			iep_clear_evt_cmp(IEP_CMP0); // CT_IEP.TMR_CMP_STS.bit0
		}

		// pru1 manages the irq, but pru0 reacts to it directly -> less jitter
		if (iep_tmr_cmp_sts & IEP_CMP1_MASK)
		{
			/* Clear Timer Compare 1 and forward it to pru1 */
			shared_mem->cmp1_trigger_for_pru1 = 1;
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
                		// TODO: this still needs sorting -> buffer-swap must be called even before a buffer is full ... to get a valid buffer
				/* Did the Linux kernel module ask for reset? */
				if (shared_mem->shepherd_state == STATE_RESET) return;

				/* PRU tries to exchange a full buffer for a fresh one if measurement is running */
				if ((shared_mem->shepherd_state == STATE_RUNNING) &&
				    (shared_mem->shepherd_mode != MODE_DEBUG))
				{
					//sample_buf_idx = handle_buffer_swap(shared_mem, free_buffers_ptr, buffers_far, sample_buf_idx, analog_sample_idx);
					sample_buf_idx = handle_buffer_swap(shared_mem, free_buffers_ptr, buffers_far, sample_buf_idx,
									    shared_mem->analog_sample_counter);
					shared_mem->analog_sample_counter = 0;
					GPIO_TOGGLE(DEBUG_PIN1_MASK); // NOTE: desired user-feedback
				}
			}
			/* only handle kernel-communications if this is not the last sample */
			else {
				GPIO_ON(DEBUG_PIN0_MASK);
				handle_kernel_com(shared_mem, free_buffers_ptr);
                		GPIO_OFF(DEBUG_PIN0_MASK);
			}
		}

		// this stack ensures low overhead to event loop AND full buffer before switching
		if (iep_tmr_cmp_sts & IEP_CMP0_MASK)
		{
			GPIO_TOGGLE(DEBUG_PIN1_MASK);
			// TODO: a buffer swap should be done here, but then would the first sample not be on timer=0
			// TODO: prepare: accelerate buffer_swap and harden pre-trigger, then this routine can come before the actual sampling
			if (shared_mem->analog_sample_counter > 1)
				shared_mem->analog_sample_counter = 1;
			GPIO_TOGGLE(DEBUG_PIN1_MASK);
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
	// Initialize all struct-Members Part A (Part B in Reset Loop)
	shared_memory->mem_base_addr = resourceTable.shared_mem.pa;
	shared_memory->mem_size = resourceTable.shared_mem.len;

	shared_memory->n_buffers = RING_SIZE;
	shared_memory->samples_per_buffer = ADC_SAMPLES_PER_BUFFER;
	shared_memory->buffer_period_ns = BUFFER_PERIOD_NS;

	shared_memory->dac_auxiliary_voltage_raw = 0;
	shared_memory->shepherd_state = STATE_IDLE;
	shared_memory->shepherd_mode = MODE_HARVEST;  // TODO: is this the the error for "wrong state"?

	shared_memory->last_sample_timestamp_ns = 0;
	shared_memory->next_buffer_timestamp_ns = 0;
	shared_memory->analog_sample_counter = 0;

	/* this init is nonsense, but testable for byteorder and proper values */
	shared_memory->calibration_settings = (struct Calibration_Config){
		.adc_current_factor_nA_n8=255u, .adc_current_offset_nA=-1,
		.dac_voltage_inv_factor_uV_n20=254u, .dac_voltage_offset_uV=-2};

	vsource_struct_init(&shared_memory->virtsource_settings);

	shared_memory->pru1_msg_ctrl_req = (struct CtrlReqMsg){.identifier=0u, .msg_unread=0u, .ticks_iep=0u};
	shared_memory->pru1_msg_ctrl_rep = (struct CtrlRepMsg){
		.identifier=0u,
		.msg_unread=0u,
		.buffer_block_period=TIMER_BASE_PERIOD,
		.analog_sample_period=TIMER_BASE_PERIOD/ADC_SAMPLES_PER_BUFFER,
		.compensation_steps=0,
		.next_timestamp_ns=0u};
	shared_memory->pru1_msg_error = (struct ProtoMsg){.msg_id=0u, .msg_unread=0u, .msg_type=MSG_NONE};

	shared_memory->pru0_msg_outbox = (struct ProtoMsg){.msg_id=0u, .msg_unread=0u, .msg_type=MSG_NONE};
	shared_memory->pru0_msg_inbox = (struct ProtoMsg){.msg_id=0u, .msg_unread=0u, .msg_type=MSG_NONE};
	shared_memory->pru0_msg_error = (struct ProtoMsg){.msg_id=0u, .msg_unread=0u, .msg_type=MSG_NONE};

	/*
	 * The dynamically allocated shared DDR RAM holds all the buffers that
	 * are used to transfer the actual data between us and the Linux host.
	 * This memory is requested from remoteproc via a carveout resource request
	 * in our resourcetable
	 */
	struct SampleBuffer *const buffers_far = (struct SampleBuffer *)resourceTable.shared_mem.pa;

	/* Allow OCP master port access by the PRU so the PRU can read external memories */
	CT_CFG.SYSCFG_bit.STANDBY_INIT = 0;

reset:
	ring_init(&free_buffers);

	GPIO_ON(DEBUG_PIN0_MASK | DEBUG_PIN1_MASK);
	sample_init(shared_memory);
	GPIO_OFF(DEBUG_PIN0_MASK | DEBUG_PIN1_MASK);

	shared_memory->gpio_edges = NULL;

	// Initialize struct-Members Part B
	// Reset Token-System to init-values
	shared_memory->cmp0_trigger_for_pru1 = 0;
	shared_memory->cmp1_trigger_for_pru1 = 0;

	shared_memory->shepherd_state = STATE_IDLE;
	/* Make sure the mutex is clear */
	simple_mutex_exit(&shared_memory->gpio_edges_mutex);

	event_loop(shared_memory, &free_buffers, buffers_far);
	goto reset;
}
