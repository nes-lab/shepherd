#ifndef __COMMONS_H_
#define __COMMONS_H_
// NOTE: a Copy of this definition-file exists for the pru-firmware (copy changes by hand)

/**
 * These are the system events that we use to signal events to the PRUs.
 * See the AM335x TRM Table 4-22 for a list of all events
 */
#define HOST_PRU_EVT_TIMESTAMP 20

/* The SharedMem struct resides at the beginning of the PRUs shared memory */
#define PRU_SHARED_MEM_STRUCT_OFFSET 0x10000

enum SyncMsgID { MSG_SYNC_CTRL_REQ = 0x55, MSG_SYNC_CTRL_REP = 0xAA };

enum ShepherdMode {
	MODE_HARVEST,
	MODE_HARVEST_TEST,
	MODE_EMULATE,
	MODE_EMULATE_TEST,
	MODE_DEBUG,
	MODE_NONE
};
enum ShepherdState {
	STATE_UNKNOWN,
	STATE_IDLE,
	STATE_ARMED,
	STATE_RUNNING,
	STATE_RESET,
	STATE_FAULT
};

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
} __attribute__((packed));

/* This structure defines all settings of virtual source emulation*/
/* more complex regulators use vars in their section and above */
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
    uint8_t LUT_output_efficiency_n8[12]; // depending on output_current, TODO: was inverse
    /* TODO: is there a drop voltage?, can input voltage be higher than cap-voltage, and all power be used? */
} __attribute__((packed));

/* Control request message sent from PRU1 to this kernel module */
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

/* Control reply message sent from this kernel module to PRU1 after running the control loop */
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


/* This is external to expose some of the attributes through sysfs */
extern void __iomem *pru_shared_mem_io;

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
	/* This structure defines all settings of virtual source emulation*/
	struct VirtSourceSettings virtsource_settings;
	/* replacement Msg-System for slow rpmsg (check 640ns, receive 4820ns) */
	struct CtrlReqMsg ctrl_req;
	struct CtrlRepMsg ctrl_rep;
} __attribute__((packed));

#endif /* __COMMONS_H_ */