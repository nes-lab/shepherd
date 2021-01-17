#ifndef __COMMONS_H_
#define __COMMONS_H_
// NOTE: a Copy of this definition-file exists for the kernel module (copy changes by hand)
// NOTE: and most of the structs are hardcoded in read_buffer() in shepherd_io.py

#include "simple_lock.h"
#include "shepherd_config.h"
#include "stdint_fast.h"


#define HOST_PRU_EVT_TIMESTAMP          20U

#define PRU_PRU_EVT_SAMPLE              30U
#define PRU_PRU_EVT_BLOCK_END           31U	// TODO: can be removed, after trigger-replacement

#define PRU_SHARED_MEM_STRUCT_OFFSET    0x10000u

#define MAX_GPIO_EVT_PER_BUFFER         16384U


/* Message IDs used in Data Exchange Protocol between PRU0 and user space */
enum DEPMsgID {
	MSG_DEP_ERROR = 0u,
	MSG_DEP_BUF_FROM_HOST = 1u,
	MSG_DEP_BUF_FROM_PRU = 2u,
	MSG_DEP_ERR_INCMPLT = 3u,
	MSG_DEP_ERR_INVLDCMD = 4u,
	MSG_DEP_ERR_NOFREEBUF = 5u,
	MSG_DEP_DBG_PRINT = 6u,
	MSG_DEP_DBG_ADC = 0xF0u,
	MSG_DEP_DBG_DAC = 0xF1u
};

/* Message IDs used in Synchronization Protocol between PRU1 and kernel module */
enum SyncMsgID { MSG_SYNC_CTRL_REQ = 0x55, MSG_SYNC_CTRL_REP = 0xAA };

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

struct CalibrationSettings {
	/* Gain of load current adc. It converts current to adc value, TODO: probably nA? */
	int32_t adc_load_current_gain;
	/* Offset of load current adc */
	int32_t adc_load_current_offset;
	/* Gain of load voltage adc. It converts voltage to adc value */
	int32_t adc_load_voltage_gain;
	/* Offset of load voltage adc */
	int32_t adc_load_voltage_offset;
	/* TODO: this should also contain DAC-Values */
	/* TODO: rename to  */
} __attribute__((packed));

/* This structure defines all settings of virtual source emulation*/
/* more complex regulators use vars in their section and above */
/* NOTE: sys-FS-FNs uses 4 byte steps, so struct must be (size)mod4=0 */
struct VirtSourceSettings {
	/* Direct Reg */
	uint32_t c_output_capacitance_uf; // final (always last) stage to catch current spikes of target
	/* Boost Reg, ie. BQ25504 */
	uint32_t v_harvest_boost_threshold_mV; // min input-voltage for the boost converter to work
	uint32_t c_storage_capacitance_uf;
	uint32_t c_storage_voltage_init_mV; // allow a proper / fast startup
	uint32_t c_storage_voltage_max_mV;  // -> boost shuts off
	uint32_t c_storage_current_leak_nA;
	uint32_t c_storage_enable_threshold_mV;  // -> target gets connected (hysteresis-combo with next value)
	uint32_t c_storage_disable_threshold_mV; // -> target gets disconnected
	uint8_t LUT_inp_efficiency_n8[12][12]; // depending on inp_voltage, inp_current, (cap voltage)
		// n8 means normalized to 2^8 = 1.0
	uint32_t pwr_good_low_threshold_mV; // range where target is informed by output-pin
	uint32_t pwr_good_high_threshold_mV;
	/* Buck Boost, ie. BQ25570) */
	uint32_t dc_output_voltage_mV;
	uint8_t LUT_output_efficiency_n8[12]; // depending on output_current
} __attribute__((packed));

// pseudo-assertion to test for correct struct-size, zero cost
extern uint32_t CHECK_VIRTSOURCE[1/((sizeof(struct VirtSourceSettings) & 0x03u) == 0x00u)];

/* Format of RPMSG used in Data Exchange Protocol between PRU0 and user space */
struct DEPMsg {
	uint32_t msg_type;
	uint32_t value;
} __attribute__((packed));

/* Format of RPMSG message sent from PRU1 to kernel module */
struct CtrlReqMsg {
	/* Identifier => Canary, This is used to identify memory corruption */
	uint8_t identifier;
	/* Token-System to signal new message & the ack, (sender sets unread, receiver resets) */
	uint8_t msg_unread;
	/* Alignment with memory, (bytes)mod4 */
	uint8_t reserved[2];
	/* Number of ticks passed on the PRU's IEP timer */
	uint32_t ticks_iep;
	/* Previous buffer period in IEP ticks */
	uint32_t old_period;
} __attribute__((packed));

/* Format of RPMSG message sent from kernel module to PRU1 */
struct CtrlRepMsg {
	/* Identifier => Canary, This is used to identify memory corruption */
	uint8_t identifier;
	/* Token-System to signal new message & the ack, (sender sets unread, receiver resets) */
	uint8_t msg_unread;
	/* Alignment with memory, (bytes)mod4 */
	uint8_t reserved0[2];
	/* Actual Content of message */
	int32_t clock_corr;
	uint64_t next_timestamp_ns;
} __attribute__((packed));

/* Format of memory structure shared between PRU0, PRU1 and kernel module (lives in shared RAM of PRUs) */
struct SharedMem {
	uint32_t shepherd_state;
	/* Stores the mode, e.g. harvesting or emulation */
	uint32_t shepherd_mode;
	/* Allows setting a fixed voltage for the seconds DAC-Output (Channel A),
	 * TODO: this has to be optimized, allow better control (off, link to ch-b, change NOW) */
	uint32_t dac_auxiliary_voltage_mV;
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
	struct CalibrationSettings calibration_settings;
	/* This structure defines all settings of virtcap emulation*/
	struct VirtSourceSettings virtsource_settings;
	/* replacement Msg-System for slow rpmsg (check 640ns, receive 4820ns) */
	struct CtrlReqMsg ctrl_req;
	struct CtrlRepMsg ctrl_rep;
	/* NOTE: End of region (also) controlled by kernel module */

	/* Used to exchange timestamp of next buffer between PRU1 and PRU0 */
	uint64_t next_timestamp_ns;
	/* Protects write access to below gpio_edges structure */
	simple_mutex_t gpio_edges_mutex;
	/**
	* Pointer to gpio_edges structure in current buffer. Only PRU0 knows about
	* which is the current buffer, but PRU1 is sampling GPIOs. Therefore PRU0
	* shares the memory location of the current gpio_edges struct
	*/
	struct GPIOEdges *gpio_edges;
	/* Counter for ADC-Samples, updated by PRU0, also needed (non-writing) by PRU1 for some timing-calculations */
	uint32_t analog_sample_counter;
	/* Token system to ensure both PRUs can share interrupts */
	bool_ft cmp0_handled_by_pru0;
	bool_ft cmp0_handled_by_pru1;
	bool_ft cmp1_handled_by_pru0;
	bool_ft cmp1_handled_by_pru1;
} __attribute__((packed));

#endif /* __COMMONS_H_ */
