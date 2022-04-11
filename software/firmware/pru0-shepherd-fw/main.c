#include <stdint.h>

#include <pru_cfg.h>
//#include <pru_iep.h>
//#include <rsc_types.h>

#include "iep.h"
#include "stdint_fast.h"
#include "gpio.h"
#include "intc.h"
#include "resource_table_def.h"
#include "simple_lock.h"

#include "commons.h"
#include "hw_config.h"
#include "ringbuffer.h"
#include "shepherd_config.h"

#include "calibration.h"
#include "virtual_converter.h"
#include "sampling.h"

/* PRU0 Feature Selection */
//#define ENABLE_DEBUG_MATH_FN	// reduces firmware by ~9 kByte

#ifdef ENABLE_DEBUG_MATH_FN
#include "math64_safe.h"
#endif

/* Used to signal an invalid buffer index */
#define NO_BUFFER 	(0xFFFFFFFF)

// alternative message channel specially dedicated for errors
static void send_status(volatile struct SharedMem *const shared_mem, enum MsgType type, const uint32_t value)
{
	// do not care for sent-status, newest error wins IF different from previous
	if (!((shared_mem->pru1_msg_error.type == type) && (shared_mem->pru1_msg_error.value[0] == value)))
	{
		shared_mem->pru0_msg_error.unread = 0u;
		shared_mem->pru0_msg_error.type = type;
		shared_mem->pru0_msg_error.value[0] = value;
		shared_mem->pru0_msg_error.id = MSG_TO_KERNEL;
		// NOTE: always make sure that the unread-flag is activated AFTER payload is copied
		shared_mem->pru0_msg_error.unread = 1u;
	}
	if (type >= 0xE0) __delay_cycles(200U/TIMER_TICK_NS); // 200 ns
}

// send returns a 1 on success
static bool_ft send_message(volatile struct SharedMem *const shared_mem, enum MsgType type, const uint32_t value1, const uint32_t value2)
{
	if (shared_mem->pru0_msg_outbox.unread == 0)
	{
		shared_mem->pru0_msg_outbox.type = type;
		shared_mem->pru0_msg_outbox.value[0] = value1;
		shared_mem->pru0_msg_outbox.value[1] = value2;
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
			  struct SampleBuffer *const buffers_far, const uint32_t last_buffer_idx)
{
	uint32_t next_buffer_idx;
	uint8_t tmp_idx;

	/* Fetch and prepare new buffer from ring */
	if (ring_get(free_buffers_ptr, &tmp_idx) > 0u)
	{
		next_buffer_idx = (uint32_t)tmp_idx;
		shared_mem->sample_buffer = buffers_far + next_buffer_idx;
		shared_mem->sample_buffer->timestamp_ns = shared_mem->next_buffer_timestamp_ns;
		shared_mem->last_sample_timestamp_ns = shared_mem->next_buffer_timestamp_ns;

		if (shared_mem->next_buffer_timestamp_ns == 0u)
		{
			/* debug-output for a wrong timestamp */
			send_status(shared_mem, MSG_ERR_TIMESTAMP, 0);
		}
	}
	else
	{
		next_buffer_idx = NO_BUFFER;
		shared_mem->sample_buffer = NULL;
		send_status(shared_mem, MSG_ERR_NOFREEBUF, 0u);
	}

	/* Lock the access to gpio_edges structure to allow swap without inconsistency */
	simple_mutex_enter(&shared_mem->gpio_edges_mutex);

	if (next_buffer_idx != NO_BUFFER)
	{
		shared_mem->gpio_edges = &shared_mem->sample_buffer->gpio_edges;
		shared_mem->gpio_edges->idx = 0;
	}
	else
	{
		shared_mem->gpio_edges = NULL;
	}

	simple_mutex_exit(&shared_mem->gpio_edges_mutex);

	/* If we had a valid buffer, return it to host */
	if (last_buffer_idx != NO_BUFFER)
	{
		(buffers_far + last_buffer_idx)->len = ADC_SAMPLES_PER_BUFFER; // TODO: could be removed in future, not used ATM
		send_message(shared_mem, MSG_BUF_FROM_PRU, last_buffer_idx, ADC_SAMPLES_PER_BUFFER);
	}

	return next_buffer_idx;
}

#ifdef ENABLE_DEBUG_MATH_FN
extern uint32_t get_num_size_as_bits(uint32_t value);
uint64_t debug_math_fns(const uint32_t factor, const uint32_t mode)
{
	uint64_t result = 0;
	const uint64_t f2 = (uint64_t)factor + ((uint64_t)(factor) << 32u);
	const uint64_t f3 = factor - 10;
	GPIO_TOGGLE(DEBUG_PIN1_MASK);

	if (mode == 1)
	{
		const uint32_t r32 = factor * factor;
		result = r32;
	}									// ~ 28 ns, limits 0..65535
	else if (mode == 2)	result = factor * factor; 			// ~ 34 ns, limits 0..65535
	else if (mode == 3)	result = (uint64_t)factor * factor; 		// ~ 42 ns, limits 0..65535 -> wrong behaviour!!!
	else if (mode == 4)	result = factor * (uint64_t)factor; 		// ~ 48 ns, limits 0..(2^32-1) -> works fine?
	else if (mode == 5)	result = (uint64_t)factor * (uint64_t)factor; 	// ~ 54 ns, limits 0..(2^32-1)
	else if (mode == 6)	result = ((uint64_t)factor)*((uint64_t)factor); // ~ 54 ns, limits 0..(2^32-1)
	else if (mode == 11)	result = factor * f2;				// ~ 3000 - 4800 - 6400 ns, limits 0..(2^32-1) -> time depends on size (4, 16, 32 bit)
	else if (mode == 12)	result = f2 * factor;				// same as above
	else if (mode == 13)	result = f2*f2;					// same as above
	else if (mode == 14)	result = mul64(f2,f2);				//
	else if (mode == 15)	result = mul64(factor,f2);			//
	else if (mode == 16)	result = mul64(f2,factor);			//
	else if (mode == 17)	result = mul64((uint64_t)factor,f2);		//
	else if (mode == 18)	result = mul64(f2,(uint64_t)factor);		//
	else if (mode == 21)	result = factor + f2;				// ~ 84 ns, limits 0..(2^31-1) or (2^63-1)
	else if (mode == 22)	result = f2 + factor;				// ~ 90 ns, limits 0..(2^31-1) or (2^63-1)
	else if (mode == 23)	result = f2 + f3;				// ~ 92 ns, limits 0..(2^31-1) or (2^63-1)
	else if (mode == 24)	result = f2 + 1111ull;				// ~ 102 ns, overflow at 2^32
	else if (mode == 25)	result = 1111ull + f2;				// ~ 110 ns, overflow at 2^32
	else if (mode == 26)	result = f2 + (uint64_t)1111u;			//
	else if (mode == 27)	result = add64(f2, f3);				//
	else if (mode == 28)	result = add64(factor, f3);			//
	else if (mode == 29)	result = add64(f3, factor);			//
	else if (mode == 31)	result = factor - f3;				// ~ 100 ns, limits 0..(2^32-1)
	else if (mode == 32)	result = f2 - factor;				// ~ 104 ns, limits 0..(2^64-1)
	else if (mode == 33)	result = f2 - f3;				// same
	else if (mode == 41)	result = ((uint64_t)(factor) << 32u);		// ~ 128 ns, limit (2^32-1)
	else if (mode == 42)	result = (f2 >> 32u);				// ~ 128 ns, also works
	else if (mode == 51)	result = get_num_size_as_bits(factor);		//
	GPIO_TOGGLE(DEBUG_PIN1_MASK);
	return result;
}
#endif

static bool_ft handle_kernel_com(volatile struct SharedMem *const shared_mem, struct RingBuffer *const free_buffers_ptr)
{
	struct ProtoMsg msg_in;

	if (receive_message(shared_mem, &msg_in) == 0)
		return 1u;

	if ((shared_mem->shepherd_mode == MODE_DEBUG) && (shared_mem->shepherd_state == STATE_RUNNING))
	{
        	uint32_t res;
        	uint64_t res64;
		switch (msg_in.type) {

		case MSG_DBG_ADC:
			res = sample_dbg_adc(msg_in.value[0]);
			send_message(shared_mem, MSG_DBG_ADC, res, 0);
			return 1u;

		case MSG_DBG_DAC: // TODO: better name: MSG_CTRL_DAC
			sample_dbg_dac(msg_in.value[0]);
			return 1u;

		case MSG_DBG_GP_BATOK:
			set_batok_pin(shared_mem, msg_in.value[0] > 0);
			return 1U;

		case MSG_DBG_GPI:
			send_message(shared_mem,MSG_DBG_GPI, shared_mem->gpio_pin_state, 0);
			return 1U;

		case MSG_DBG_VSOURCE_P_INP: // TODO: these can be done with normal emulator instantiation
			converter_calc_inp_power(msg_in.value[0], msg_in.value[1]);
			send_message(shared_mem, MSG_DBG_VSOURCE_P_INP, (uint32_t)(get_P_input_fW()>>32u) , (uint32_t)get_P_input_fW());
			return 1u;

		case MSG_DBG_VSOURCE_P_OUT:
			converter_calc_out_power(msg_in.value[0]);
			send_message(shared_mem, MSG_DBG_VSOURCE_P_OUT, (uint32_t)(get_P_output_fW()>>32u), (uint32_t)get_P_output_fW());
			return 1u;

		case MSG_DBG_VSOURCE_V_CAP:
			converter_update_cap_storage();
			send_message(shared_mem, MSG_DBG_VSOURCE_V_CAP, get_V_intermediate_uV(), 0);
			return 1u;

		case MSG_DBG_VSOURCE_V_OUT:
			res = converter_update_states_and_output(shared_mem);
			send_message(shared_mem, MSG_DBG_VSOURCE_V_OUT, res, 0);
			return 1u;

		case MSG_DBG_VSOURCE_INIT:
			calibration_initialize(&shared_mem->calibration_settings);
			converter_initialize(&shared_mem->converter_settings);
			send_message(shared_mem, MSG_DBG_VSOURCE_INIT, 0, 0);
			return 1u;

		case MSG_DBG_VSOURCE_CHARGE:
			converter_calc_inp_power(msg_in.value[0], msg_in.value[1]);
			converter_calc_out_power(0u);
			converter_update_cap_storage();
			res = converter_update_states_and_output(shared_mem);
			send_message(shared_mem, MSG_DBG_VSOURCE_CHARGE, get_V_intermediate_uV(), res);
			return 1u;

		case MSG_DBG_VSOURCE_DRAIN:
			converter_calc_inp_power(0u, 0u);
			converter_calc_out_power(msg_in.value[0]);
			converter_update_cap_storage();
			res = converter_update_states_and_output(shared_mem);
			send_message(shared_mem, MSG_DBG_VSOURCE_DRAIN, get_V_intermediate_uV(), res);
			return 1u;

#ifdef ENABLE_DEBUG_MATH_FN
		case MSG_DBG_FN_TESTS:
			res64 = debug_math_fns(msg_in.value[0], msg_in.value[1]);
			send_message(shared_mem, MSG_DBG_FN_TESTS, (uint32_t)(res64>>32u), (uint32_t)res64);
			return 1u;
#endif //ENABLE_DEBUG_MATH_FN

		default:
			send_message(shared_mem,MSG_ERR_INVLDCMD, msg_in.type, 0);
			return 0U;
		}
	} else
	{
		// most common and important msg first
		if (msg_in.type == MSG_BUF_FROM_HOST) {
			ring_put(free_buffers_ptr, (uint8_t)msg_in.value[0]);
			return 1U;
		} else if ((msg_in.type == MSG_TEST) && (msg_in.value[0] == 1)) {
			// pipeline-test for msg-system
			send_message(shared_mem,MSG_TEST, msg_in.value[0], 0);
		} else if ((msg_in.type == MSG_TEST) && (msg_in.value[0] == 2)) {
			// pipeline-test for msg-system
			send_status(shared_mem, MSG_TEST, msg_in.value[0]);
		} else {
			send_message(shared_mem,MSG_ERR_INVLDCMD, msg_in.type, 0);
		}
	}
	return 0u;
}

void event_loop(volatile struct SharedMem *const shared_mem,
		struct RingBuffer *const free_buffers_ptr,
		struct SampleBuffer *const buffers_far) // TODO: should be volatile, also for programmer and more
{
	uint32_t sample_buf_idx = NO_BUFFER;
	enum ShepherdMode shepherd_mode = (enum ShepherdMode)shared_mem->shepherd_mode;
	uint32_t iep_tmr_cmp_sts = 0u;

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
		// timestamp pru0 to monitor utilization
		const uint32_t timer_start = iep_get_cnt_val() - 30u; // rough estimate on

		// Activate new Buffer-Cycle & Ensure proper execution order on pru1 -> cmp0_event (E2) must be handled before cmp1_event (E3)!
		if (iep_tmr_cmp_sts & IEP_CMP0_MASK)
		{
			/* Clear Timer Compare 0 and forward it to pru1 */
			GPIO_TOGGLE(DEBUG_PIN0_MASK);
			shared_mem->cmp0_trigger_for_pru1 = 1u;
			iep_clear_evt_cmp(IEP_CMP0); // CT_IEP.TMR_CMP_STS.bit0
			/* prepare a new buffer-cycle */
			shared_mem->analog_sample_counter = 0u;
			/* without a buffer: only show short Signal for new Cycle */
			if (sample_buf_idx == NO_BUFFER) GPIO_TOGGLE(DEBUG_PIN0_MASK);
		}

		// Sample, swap buffer and receive messages
		if (iep_tmr_cmp_sts & IEP_CMP1_MASK)
		{
			/* Clear Timer Compare 1 and forward it to pru1 */
			shared_mem->cmp1_trigger_for_pru1 = 1u;
			iep_clear_evt_cmp(IEP_CMP1); // CT_IEP.TMR_CMP_STS.bit1
			uint32_t inc_done = 0u;

			/* The actual sampling takes place here */
			if ((sample_buf_idx != NO_BUFFER) && (shared_mem->analog_sample_counter < ADC_SAMPLES_PER_BUFFER))
			{
				GPIO_ON(DEBUG_PIN1_MASK);
				inc_done = sample(shared_mem, shared_mem->sample_buffer, shepherd_mode);
				GPIO_OFF(DEBUG_PIN1_MASK);
			}

			/* counter-incrementation, allow premature incrementation by sub-sampling_fn, use return_value to register it */
			if (!inc_done)
				shared_mem->analog_sample_counter++;

			if (shared_mem->analog_sample_counter == ADC_SAMPLES_PER_BUFFER)
			{
				/* Did the Linux kernel module ask for reset? */
				if (shared_mem->shepherd_state == STATE_RESET) return;

				/* PRU tries to exchange a full buffer for a fresh one if measurement is running */
				if ((shared_mem->shepherd_state == STATE_RUNNING) &&
				    (shared_mem->shepherd_mode != MODE_DEBUG))
				{
					GPIO_ON(DEBUG_PIN1_MASK);
					sample_buf_idx = handle_buffer_swap(shared_mem, free_buffers_ptr, buffers_far, sample_buf_idx);
					GPIO_OFF(DEBUG_PIN1_MASK);
				}
				/* pre-reset counter, so pru1 can fetch data */
				shared_mem->analog_sample_counter = 0u;
				shared_mem->analog_value_index = NO_BUFFER;
			}
			else
			{
				/* only handle kernel-communications if this is not the last sample */
				GPIO_ON(DEBUG_PIN1_MASK);
				handle_kernel_com(shared_mem, free_buffers_ptr);
                		GPIO_OFF(DEBUG_PIN1_MASK);
			}
		}

		// record loop-duration -> gets further processed by pru1
		shared_mem->pru0_ticks_per_sample = iep_get_cnt_val() - timer_start;
		/*
		GPIO_OFF(DEBUG_PIN0_MASK);
		if (shared_mem->pru0_ticks_per_sample >= 1950u)
		{
			// TODO: debug-artifact to find long loop-cycles
			GPIO_TOGGLE(DEBUG_PIN0_MASK);
		}*/
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

	shared_memory->n_buffers = FIFO_BUFFER_SIZE;
	shared_memory->samples_per_buffer = ADC_SAMPLES_PER_BUFFER;
	shared_memory->buffer_period_ns = BUFFER_PERIOD_NS;

	shared_memory->dac_auxiliary_voltage_raw = 0u;
	shared_memory->shepherd_state = STATE_IDLE;
	shared_memory->shepherd_mode = MODE_HARVESTER;

	shared_memory->last_sample_timestamp_ns = 0u;
	shared_memory->next_buffer_timestamp_ns = 0u;
	shared_memory->analog_sample_counter = 0u;
	shared_memory->gpio_edges = NULL;
	shared_memory->sample_buffer = NULL;

	shared_memory->gpio_pin_state = 0u;

	shared_memory->vsource_batok_trigger_for_pru1 = false;
	shared_memory->vsource_batok_pin_value = false;

	/* minimal init for these structs to make them safe */
	/* NOTE: more inits are done in kernel */
	shared_memory->converter_settings.converter_mode = 0u;
	shared_memory->harvester_settings.algorithm = 0u;
	shared_memory->programmer_ctrl.state = 0u;
	shared_memory->programmer_ctrl.protocol = 0u;

	shared_memory->pru1_sync_outbox.unread = 0u;
	shared_memory->pru1_sync_inbox.unread = 0u;
	shared_memory->pru1_msg_error.unread = 0u;

	shared_memory->pru0_msg_outbox.unread =0u;
	shared_memory->pru0_msg_inbox.unread =0u;
	shared_memory->pru0_msg_error.unread =0u;

	/*
	 * The dynamically allocated shared DDR RAM holds all the buffers that
	 * are used to transfer the actual data between us and the Linux host.
	 * This memory is requested from remoteproc via a carveout resource request
	 * in our resourcetable
	 */
	struct SampleBuffer *const buffers_far = (struct SampleBuffer *)resourceTable.shared_mem.pa;

	/* Allow OCP master port access by the PRU so the PRU can read external memories */
	CT_CFG.SYSCFG_bit.STANDBY_INIT = 0u;

	/* allow PRU1 to enter event-loop */
	shared_memory->cmp0_trigger_for_pru1 = 1u;

reset:
	send_message(shared_memory, MSG_STATUS_RESTARTING_ROUTINE, 0u, 0u);
	shared_memory->pru0_ticks_per_sample = 0u; // 2000 ticks are in one 10 us sample

	ring_init(&free_buffers);

	GPIO_ON(DEBUG_PIN0_MASK | DEBUG_PIN1_MASK);
	sample_init(shared_memory);
	GPIO_OFF(DEBUG_PIN0_MASK | DEBUG_PIN1_MASK);

	shared_memory->gpio_edges = NULL;
	shared_memory->vsource_skip_gpio_logging = false;

	shared_memory->shepherd_state = STATE_IDLE;
	/* Make sure the mutex is clear */
	simple_mutex_exit(&shared_memory->gpio_edges_mutex);

	event_loop(shared_memory, &free_buffers, buffers_far);

	goto reset;
}
