#ifndef __COMMONS_H_
#define __COMMONS_H_
// NOTE: a (almost) Copy of this definition-file exists for the kernel module (copy changes by hand)
// NOTE: and most of the structs are hardcoded in read_buffer() in shepherd_io.py

#include "simple_lock.h"
#include "shepherd_config.h"
#include "stdint_fast.h"

/**
 * These are the system events that we use to signal events to the PRUs.
 * See the AM335x TRM Table 4-22 for a list of all events
 */
#define HOST_PRU_EVT_TIMESTAMP          (20u)

/* The SharedMem struct resides at the beginning of the PRUs shared memory */
#define PRU_SHARED_MEM_STRUCT_OFFSET    (0x10000u)

/* gpio_buffer_size that comes with every analog_sample_buffer (0.1s) */
#define MAX_GPIO_EVT_PER_BUFFER         (16384u)

// Test data-containers and constants with pseudo-assertion with zero cost (if expression evaluates to 0 this causes a div0
// NOTE: name => alphanum without spaces and without ""
#define ASSERT(name, expression) 	extern uint32_t assert_name[1/(expression)]

/* Message content description used to distinguish messages for PRU0 */
enum MsgType {
	/* USERSPACE (enum <0xC0) */
	MSG_NONE = 0x00u,
	MSG_BUF_FROM_HOST = 0x01u,
	MSG_BUF_FROM_PRU = 0x02u,
	// DEBUG
	MSG_DBG_ADC = 0xA0u,
	MSG_DBG_DAC = 0xA1u,
	MSG_DBG_GPI = 0xA2u,
	MSG_DBG_PRINT = 0xA6u,
	/* KERNELSPACE (enum >=0xC0) */
	// STATUS
	MSG_STATUS_RESTARTING_SYNC_ROUTINE = 0xC0,
	// ERROR
	MSG_ERROR = 0xE0u,
	MSG_ERR_MEMCORRUPTION = 0xE1u,
	MSG_ERR_BACKPRESSURE = 0xE2u,
	MSG_ERR_INCMPLT = 0xE3u,
	MSG_ERR_INVLDCMD = 0xE4u,
	MSG_ERR_NOFREEBUF = 0xE5u,
	MSG_ERR_TIMESTAMP = 0xE6u,
	MSG_ERR_SYNC_STATE_NOT_IDLE = 0xE7u
};

/* Message IDs used in Mem-Protocol between PRUs and kernel module */
enum MsgID { MSG_TO_KERNEL = 0x55, MSG_TO_PRU = 0xAA };

enum ShepherdMode {
	MODE_HARVEST,
	MODE_HARVEST_TEST,
	MODE_EMULATE,
	MODE_EMULATE_TEST,
	MODE_DEBUG,
	MODE_NONE
}; // TODO: allow to set "NONE", shutsdown hrv & emu

enum ShepherdState {
	STATE_UNKNOWN,
	STATE_IDLE,
	STATE_ARMED,
	STATE_RUNNING,
	STATE_RESET,
	STATE_FAULT
};

struct GPIOEdges {
	uint32_t idx;
	uint64_t timestamp_ns[MAX_GPIO_EVT_PER_BUFFER];
    uint16_t  bitmask[MAX_GPIO_EVT_PER_BUFFER];
} __attribute__((packed));

struct SampleBuffer {
	uint32_t len;
	uint64_t timestamp_ns;
	uint32_t values_voltage[ADC_SAMPLES_PER_BUFFER]; // TODO: would be more efficient for PRU to keep matching V&C together
	uint32_t values_current[ADC_SAMPLES_PER_BUFFER];
	struct GPIOEdges gpio_edges;
} __attribute__((packed));

/* calibration values - usage example: voltage_uV = adc_value * gain_factor + offset
 * numbers for hw-rev2.0
 * ADC: VIn = DOut * 19.5313 uV -> factor for raw-value to calc uV_n8 (*256) = 5'000
 * 	CIn = DOut * 195.313 nA -> factor for raw-value to calc nA_n8 (*256) = 50'000
 * DAC	VOut = DIn * 76.2939 uV -> inverse factor to get raw_n20-value from uV_n20 = 13'743
 */
struct Calibration_Config {
	/* Gain of load current adc. It converts current to ADC raw value */
	uint32_t adc_current_factor_nA_n8; // n8 means normalized to 2^8 => 1.0
	/* Offset of load current adc */
	int32_t adc_current_offset_nA;
	/* Gain of DAC. It converts voltage to DAC raw value */
	uint32_t dac_voltage_inv_factor_uV_n20;
	/* Offset of load voltage DAC */
	int32_t dac_voltage_offset_uV;
} __attribute__((packed));


#define LUT_SIZE	(12)

/* This structure defines all settings of virtual source emulation
 * more complex regulators use vars in their section and above
 * NOTE: sys-FS-FNs currently uses 4 byte steps for transfer, so struct must be (size)mod4=0
 * Container-sizes with SI-Units:
 * 	_nF-u32 = ~ 4.3 F
 * 	_uV-u32 = 4294 V
 * 	_nA-u32 = ~ 4.3 A
 */
struct VirtSource_Config {
	uint32_t converter_mode; // enum for  different functionality, TODO: implement
	/* Direct Reg */
	uint32_t C_output_nF; // (final stage) to compensate for (hard to detect) enable-current-surge of real capacitors
	/* Boost Reg, ie. BQ25504 */
	uint32_t V_inp_boost_threshold_uV; // min input-voltage for the boost converter to work
	uint32_t C_storage_nF;
	uint32_t V_storage_init_uV; // allow a proper / fast startup
	uint32_t V_storage_max_uV;  // -> boost shuts off
	uint32_t I_storage_leak_nA; // TODO: ESR could also be considered
	uint32_t V_storage_enable_threshold_uV;  // -> target gets connected (hysteresis-combo with next value)
	uint32_t V_storage_disable_threshold_uV; // -> target gets disconnected
	uint32_t interval_check_thresholds_ns; // some BQs check every 65 ms if output should be disconnected
	uint32_t V_pwr_good_low_threshold_uV; // range where target is informed by output-pin
	uint32_t V_pwr_good_high_threshold_uV;
	uint32_t dV_stor_en_thrs_uV; // compensate C_out, for disable state when V_store < V_store_enable/disable_threshold_uV
	/* Buck Boost, ie. BQ25570) */
	uint32_t V_output_uV;
	uint32_t dV_stor_low_uV; // compensate C_out, for disable state when V_store < V_out
	/* LUTs */
	uint8_t LUT_inp_efficiency_n8[LUT_SIZE][LUT_SIZE]; // depending on inp_voltage, inp_current, (cap voltage), n8 means normalized to 2^8 => 1.0
	uint32_t LUT_out_inv_efficiency_n10[LUT_SIZE]; // depending on output_current, n8 means normalized to 2^8 => 1/1.0,
} __attribute__((packed));

// pseudo-assertion to test for correct struct-size, zero cost
extern uint32_t CHECK_VIRTSOURCE[1/((sizeof(struct VirtSource_Config) & 0x03u) == 0x00u)];

/* Format of Message-Protocol between PRU0 Kernel Module */
struct ProtoMsg {
	/* Identifier => Canary, This is used to identify memory corruption */
	uint8_t msg_id;
	/* Token-System to signal new message & the ack, (sender sets unread/1, receiver resets/0) */
	uint8_t msg_unread;
	/* content description used to distinguish messages */
	uint8_t msg_type;
	/* Alignment with memory, (bytes)mod4 */
	uint8_t reserved[1];
	/* Actual Content of message */
	uint32_t value;
} __attribute__((packed));

/* Control request message sent from PRU1 to this kernel module, TODO: replace by protoMsg*/
struct CtrlReqMsg {
	/* Identifier => Canary, This is used to identify memory corruption */
	uint8_t identifier;
	/* Token-System to signal new message & the ack, (sender sets unread/1, receiver resets/0) */
	uint8_t msg_unread;
	/* Alignment with memory, (bytes)mod4 */
	uint8_t reserved[2];
	/* Number of ticks passed on the PRU's IEP timer */
	uint32_t ticks_iep;
} __attribute__((packed));

/* Control reply message sent from this kernel module to PRU1 after running the control loop */
struct CtrlRepMsg {
	/* Identifier => Canary, This is used to identify memory corruption */
	uint8_t identifier;
	/* Token-System to signal new message & the ack, (sender sets unread, receiver resets) */
	uint8_t msg_unread;
	/* Alignment with memory, (bytes)mod4 */
	uint8_t reserved0[2];
	/* Actual Content of message */
	uint32_t buffer_block_period;   // corrected ticks that equal 100ms
	uint32_t analog_sample_period;  // ~ 10 us
	uint32_t compensation_steps;    // remainder of buffer_block/sample_count = sample_period
	uint64_t next_timestamp_ns;     // start of next buffer block
} __attribute__((packed));

/* Format of memory structure shared between PRU0, PRU1 and kernel module (lives in shared RAM of PRUs) */
struct SharedMem {
	uint32_t shepherd_state;
	/* Stores the mode, e.g. harvesting or emulation */
	uint32_t shepherd_mode;
	/* Allows setting a fixed voltage for the seconds DAC-Output (Channel A),
	 * TODO: this has to be optimized, allow better control (off, link to ch-b, change NOW) */
	uint32_t dac_auxiliary_voltage_raw;
	/* Physical address of shared area in DDR RAM, that is used to exchange data between user space and PRUs */
	uint32_t mem_base_addr;
	/* Length of shared area in DDR RAM */
	uint32_t mem_size;
	/* Maximum number of buffers stored in the shared DDR RAM area */
	uint32_t n_buffers;
	/* Number of IV samples stored per buffer */
	uint32_t samples_per_buffer;
	/* The time for sampling samples_per_buffer. Determines sampling rate */
	uint32_t buffer_period_ns;
	/* ADC calibration settings */
	struct Calibration_Config calibration_settings;
	/* This structure defines all settings of virtual source emulation*/
	struct VirtSource_Config virtsource_settings;
	/* replacement Msg-System for slow rpmsg (check 640ns, receive 4820ns) */
	struct ProtoMsg pru0_msg_inbox;
	struct ProtoMsg pru0_msg_outbox;
	struct ProtoMsg pru0_msg_error;
	struct CtrlReqMsg pru1_msg_ctrl_req;
	struct CtrlRepMsg pru1_msg_ctrl_rep;
	struct ProtoMsg   pru1_msg_error;
	/* NOTE: End of region (also) controlled by kernel module */

	/* Used to use/exchange timestamp of last sample taken & next buffer between PRU1 and PRU0 */
	uint64_t last_sample_timestamp_ns;
	uint64_t next_buffer_timestamp_ns;
	/* Protects write access to below gpio_edges structure */
	simple_mutex_t gpio_edges_mutex;
	/* internal gpio-register from PRU1 (for PRU1, debug), only updated when not running */
	uint32_t gpio_pin_state;
	/**
	* Pointer to gpio_edges structure in current buffer. Only PRU0 knows about
	* which is the current buffer, but PRU1 is sampling GPIOs. Therefore PRU0
	* shares the memory location of the current gpio_edges struct
	*/
	struct GPIOEdges *gpio_edges;
	/* Counter for ADC-Samples, updated by PRU0, also needed (non-writing) by PRU1 for some timing-calculations */
	uint32_t analog_sample_counter;
	/* Token system to ensure both PRUs can share interrupts */
	bool_ft cmp0_trigger_for_pru1;
	bool_ft cmp1_trigger_for_pru1;
} __attribute__((packed));

ASSERT(shared_mem_size, sizeof(struct SharedMem) < 10000);

#endif /* __COMMONS_H_ */
