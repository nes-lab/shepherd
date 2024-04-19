#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include <pru_cfg.h>
#include <pru_iep.h>
#include <rsc_types.h>

#include "gpio.h"
#include "iep.h"
#include "intc.h"
#include "resource_table_def.h"
#include "simple_lock.h"
#include "stdint_fast.h"

#include "commons.h"
#include "hw_config.h"
#include "ringbuffer.h"
#include "shepherd_config.h"

#include "messenger.h"
#include "programmer.h"

/* Used to signal an invalid buffer index */
#define NO_BUFFER (0xFFFFFFFF)


static bool_ft handle_kernel_com(volatile struct SharedMem *const shared_mem,
                                 struct RingBuffer *const         free_buffers_ptr)
{
    struct ProtoMsg msg_in;

    if (receive_message(shared_mem, &msg_in) == 0) return 1u;

    if ((shared_mem->shepherd_mode == MODE_DEBUG) && (shared_mem->shepherd_state == STATE_RUNNING))
    {
        //uint32_t res;

        switch (msg_in.type)
        {
            case MSG_DBG_GPI:
                send_message(shared_mem, MSG_DBG_GPI, shared_mem->gpio_pin_state, 0);
                return 1U;

            default: send_message(shared_mem, MSG_ERR_INVLDCMD, msg_in.type, 0); return 0U;
        }
    }
    else
    {
        // most common and important msg first
        if (msg_in.type == MSG_BUF_FROM_HOST)
        {
            ring_put(free_buffers_ptr, (uint8_t) msg_in.value[0]);
            return 1U;
        }
        else if ((msg_in.type == MSG_TEST) && (msg_in.value[0] == 1))
        {
            // pipeline-test for msg-system
            send_message(shared_mem, MSG_TEST, msg_in.value[0], 0);
        }
        else if ((msg_in.type == MSG_TEST) && (msg_in.value[0] == 2))
        {
            // pipeline-test for msg-system
            send_status(shared_mem, MSG_TEST, msg_in.value[0]);
        }
        else { send_message(shared_mem, MSG_ERR_INVLDCMD, msg_in.type, 0); }
    }
    return 0u;
}

void event_loop(volatile struct SharedMem *const shared_mem,
                struct RingBuffer *const         free_buffers_ptr)
{
    uint32_t iep_tmr_cmp_sts = 0;

    while (1)
    {
        while (!(iep_tmr_cmp_sts = iep_get_tmr_cmp_sts()));

        // Pretrigger for extra low jitter and up-to-date samples, ADCs will be triggered to sample on rising edge
        if (iep_tmr_cmp_sts & IEP_CMP1_MASK)
        {
            GPIO_OFF(SPI_CS_ADCs_MASK);
            __delay_cycles(100 / 5);
            GPIO_ON(SPI_CS_ADCs_MASK);
        }

        // Activate new Buffer-Cycle & Ensure proper execution order on pru1 -> cmp0_event (E2) must be handled before cmp1_event (E3)!
        if (iep_tmr_cmp_sts & IEP_CMP0_MASK)
        {
            /* Clear Timer Compare 0 and forward it to pru1 */
            //GPIO_TOGGLE(DEBUG_PIN1_MASK);
            shared_mem->cmp0_trigger_for_pru1 = 1u;
            iep_clear_evt_cmp(IEP_CMP0); // CT_IEP.TMR_CMP_STS.bit0
            /* prepare a new buffer-cycle */
            shared_mem->analog_sample_counter = 0u;
            //GPIO_TOGGLE(DEBUG_PIN1_MASK);
        }

        // Sample, swap buffer and receive messages
        if (iep_tmr_cmp_sts & IEP_CMP1_MASK)
        {
            /* Clear Timer Compare 1 and forward it to pru1 */
            shared_mem->cmp1_trigger_for_pru1 = 1u;
            iep_clear_evt_cmp(IEP_CMP1); // CT_IEP.TMR_CMP_STS.bit1

            /* The actual sampling was done here */
            shared_mem->analog_sample_counter++;

            /* Did the Linux kernel module ask for reset? */
            if (shared_mem->shepherd_state == STATE_RESET) return;
            handle_kernel_com(shared_mem, free_buffers_ptr);
        }
    }
}

int main(void)
{
    GPIO_OFF(DEBUG_PIN0_MASK | DEBUG_PIN1_MASK);
    static struct RingBuffer         free_buffers;

    /*
	 * The shared mem is dynamically allocated and we have to inform user space
	 * about the address and size via sysfs, which exposes parts of the
	 * shared_mem structure.
	 * Do this initialization early! The kernel module relies on it.
	 */
    volatile struct SharedMem *const shared_memory =
            (volatile struct SharedMem *) PRU_SHARED_MEM_STRUCT_OFFSET;

    // Initialize struct-Members Part A, must come first - this blocks PRU1!
    shared_memory->cmp0_trigger_for_pru1             = 0u; // Reset Token-System to init-values
    shared_memory->cmp1_trigger_for_pru1             = 0u;

    // Initialize all struct-Members Part B
    shared_memory->mem_base_addr                     = resourceTable.shared_mem.pa;
    shared_memory->mem_size                          = resourceTable.shared_mem.len;

    shared_memory->n_buffers                         = FIFO_BUFFER_SIZE;
    shared_memory->samples_per_buffer                = ADC_SAMPLES_PER_BUFFER;
    shared_memory->buffer_period_ns                  = BUFFER_PERIOD_NS;

    shared_memory->dac_auxiliary_voltage_raw         = 0u;
    shared_memory->shepherd_state                    = STATE_IDLE;
    shared_memory->shepherd_mode                     = MODE_HARVESTER;

    shared_memory->last_sample_timestamp_ns          = 0u;
    shared_memory->next_buffer_timestamp_ns          = 0u;
    shared_memory->analog_sample_counter             = 0u;
    shared_memory->gpio_edges                        = NULL;
    shared_memory->sample_buffer                     = NULL;

    shared_memory->gpio_pin_state                    = 0u;

    shared_memory->vsource_batok_trigger_for_pru1    = false;
    shared_memory->vsource_batok_pin_value           = false;

    /* minimal init for these structs to make them safe */
    /* NOTE: more inits are done in kernel */
    shared_memory->converter_settings.converter_mode = 0u;
    shared_memory->harvester_settings.algorithm      = 0u;
    shared_memory->programmer_ctrl.state             = PRG_STATE_IDLE;
    shared_memory->programmer_ctrl.target            = PRG_TARGET_NONE;

    shared_memory->pru1_sync_outbox.unread           = 0u;
    shared_memory->pru1_sync_inbox.unread            = 0u;
    shared_memory->pru1_msg_error.unread             = 0u;

    shared_memory->pru0_msg_outbox.unread            = 0u;
    shared_memory->pru0_msg_inbox.unread             = 0u;
    shared_memory->pru0_msg_error.unread             = 0u;

    /*
	 * The dynamically allocated shared DDR RAM holds all the buffers that
	 * are used to transfer the actual data between us and the Linux host.
	 * This memory is requested from remoteproc via a carveout resource request
	 * in our resourcetable
	 */
    struct SampleBuffer *const buffers_far = (struct SampleBuffer *) resourceTable.shared_mem.pa;

    /* Allow OCP primary port access by the PRU so the PRU can read external memories */
    CT_CFG.SYSCFG_bit.STANDBY_INIT         = 0u;

    /* allow PRU1 to enter event-loop */
    shared_memory->cmp0_trigger_for_pru1   = 1u;

reset:
    send_message(shared_memory, MSG_STATUS_RESTARTING_ROUTINE, 0u, 0u);
    shared_memory->pru0_ticks_per_sample = 0u; // 2000 ticks are in one 10 us sample

    ring_init(&free_buffers);

    shared_memory->gpio_edges                = NULL;
    shared_memory->vsource_skip_gpio_logging = false;

    shared_memory->shepherd_state            = STATE_IDLE;
    /* Make sure the mutex is clear */
    simple_mutex_exit(&shared_memory->gpio_edges_mutex);

    while (shared_memory->shepherd_state == STATE_IDLE)
    {
        if (shared_memory->programmer_ctrl.state == PRG_STATE_STARTING)
        {
            programmer(shared_memory, buffers_far);
        }
        // else event_loop(shared_memory, &free_buffers);
    }

    goto reset;
}
