#include <asm/io.h>
#include <linux/kobject.h>
#include <linux/string.h>
#include <linux/sysfs.h>

#include "commons.h"
#include "pru_comm.h"
#include "pru_mem_msg_sys.h"
#include "sync_ctrl.h"
#include "sysfs_interface.h"

int             schedule_start(unsigned int start_time_second);

struct kobject *kobj_ref;
struct kobject *kobj_mem_ref;
struct kobject *kobj_sync_ref;
struct kobject *kobj_prog_ref;

static ssize_t  sysfs_sync_error_show(struct kobject        *kobj,
                                      struct kobj_attribute *attr, char *buf);

static ssize_t  sysfs_sync_error_sum_show(struct kobject        *kobj,
                                          struct kobj_attribute *attr,
                                          char                  *buf);

static ssize_t  sysfs_sync_correction_show(struct kobject        *kobj,
                                           struct kobj_attribute *attr,
                                           char                  *buf);

static ssize_t  sysfs_SharedMem_show(struct kobject        *kobj,
                                     struct kobj_attribute *attr, char *buf);

static ssize_t  sysfs_state_show(struct kobject        *kobj,
                                 struct kobj_attribute *attr, char *buf);

static ssize_t  sysfs_state_store(struct kobject        *kobj,
                                  struct kobj_attribute *attr, const char *buf,
                                  size_t count);

static ssize_t  sysfs_mode_show(struct kobject        *kobj,
                                struct kobj_attribute *attr, char *buf);

static ssize_t  sysfs_mode_store(struct kobject        *kobj,
                                 struct kobj_attribute *attr, const char *buf,
                                 size_t count);

static ssize_t  sysfs_auxiliary_voltage_store(struct kobject        *kobj,
                                              struct kobj_attribute *attr,
                                              const char *buf, size_t count);

static ssize_t  sysfs_calibration_settings_store(struct kobject        *kobj,
                                                 struct kobj_attribute *attr,
                                                 const char *buf, size_t count);

static ssize_t  sysfs_calibration_settings_show(struct kobject        *kobj,
                                                struct kobj_attribute *attr, char *buf);

static ssize_t  sysfs_virtual_converter_settings_store(struct kobject        *kobj,
                                                       struct kobj_attribute *attr,
                                                       const char *buf, size_t count);

static ssize_t  sysfs_virtual_converter_settings_show(struct kobject        *kobj,
                                                      struct kobj_attribute *attr, char *buf);

static ssize_t  sysfs_virtual_harvester_settings_store(struct kobject        *kobj,
                                                       struct kobj_attribute *attr,
                                                       const char *buf, size_t count);

static ssize_t  sysfs_virtual_harvester_settings_show(struct kobject        *kobj,
                                                      struct kobj_attribute *attr, char *buf);

static ssize_t  sysfs_pru_msg_system_store(struct kobject        *kobj,
                                           struct kobj_attribute *attr,
                                           const char *buffer, size_t count);
static ssize_t  sysfs_pru_msg_system_show(struct kobject        *kobj,
                                          struct kobj_attribute *attr, char *buffer);

static ssize_t  sysfs_prog_state_store(struct kobject        *kobj,
                                       struct kobj_attribute *attr,
                                       const char *buffer, size_t count);
static ssize_t  sysfs_prog_state_show(struct kobject        *kobj,
                                      struct kobj_attribute *attr,
                                      char                  *buf);
static ssize_t  sysfs_prog_protocol_store(struct kobject        *kobj,
                                          struct kobj_attribute *attr,
                                          const char *buffer, size_t count);
static ssize_t  sysfs_prog_protocol_show(struct kobject        *kobj,
                                         struct kobj_attribute *attr,
                                         char                  *buf);
static ssize_t  sysfs_prog_datarate_store(struct kobject        *kobj,
                                          struct kobj_attribute *attr,
                                          const char *buffer, size_t count);
static ssize_t  sysfs_prog_datasize_store(struct kobject        *kobj,
                                          struct kobj_attribute *attr,
                                          const char *buffer, size_t count);
static ssize_t  sysfs_prog_pin_store(struct kobject        *kobj,
                                     struct kobj_attribute *attr,
                                     const char *buffer, size_t count);


struct kobj_attr_struct_s
{
    struct kobj_attribute attr;
    unsigned int          val_offset;
};

struct kobj_attribute attr_state =
        __ATTR(state, 0660, sysfs_state_show, sysfs_state_store);

struct kobj_attr_struct_s attr_mem_base_addr = {
        .attr       = __ATTR(address, 0660, sysfs_SharedMem_show, NULL),
        .val_offset = offsetof(struct SharedMem, mem_base_addr)};
struct kobj_attr_struct_s attr_mem_size = {
        .attr       = __ATTR(size, 0660, sysfs_SharedMem_show, NULL),
        .val_offset = offsetof(struct SharedMem, mem_size)};

struct kobj_attr_struct_s attr_n_buffers = {
        .attr       = __ATTR(n_buffers, 0660, sysfs_SharedMem_show, NULL),
        .val_offset = offsetof(struct SharedMem, n_buffers)};
struct kobj_attr_struct_s attr_samples_per_buffer = {
        .attr       = __ATTR(samples_per_buffer, 0660, sysfs_SharedMem_show, NULL),
        .val_offset = offsetof(struct SharedMem, samples_per_buffer)};
struct kobj_attr_struct_s attr_buffer_period_ns = {
        .attr       = __ATTR(buffer_period_ns, 0660, sysfs_SharedMem_show, NULL),
        .val_offset = offsetof(struct SharedMem, buffer_period_ns)};
struct kobj_attr_struct_s attr_mode = {
        .attr       = __ATTR(mode, 0660, sysfs_mode_show, sysfs_mode_store),
        .val_offset = offsetof(struct SharedMem, shepherd_mode)};
struct kobj_attr_struct_s attr_auxiliary_voltage = {
        .attr       = __ATTR(dac_auxiliary_voltage_raw, 0660, sysfs_SharedMem_show,
                             sysfs_auxiliary_voltage_store),
        .val_offset = offsetof(struct SharedMem, dac_auxiliary_voltage_raw)};
struct kobj_attr_struct_s attr_calibration_settings = {
        .attr       = __ATTR(calibration_settings, 0660, sysfs_calibration_settings_show,
                             sysfs_calibration_settings_store),
        .val_offset = offsetof(struct SharedMem, calibration_settings)};
struct kobj_attr_struct_s attr_virtual_converter_settings = {
        .attr       = __ATTR(virtual_converter_settings, 0660, sysfs_virtual_converter_settings_show,
                             sysfs_virtual_converter_settings_store),
        .val_offset = offsetof(struct SharedMem, converter_settings)};
struct kobj_attr_struct_s attr_virtual_harvester_settings = {
        .attr       = __ATTR(virtual_harvester_settings, 0660, sysfs_virtual_harvester_settings_show,
                             sysfs_virtual_harvester_settings_store),
        .val_offset = offsetof(struct SharedMem, harvester_settings)};
struct kobj_attr_struct_s attr_pru_msg_system_settings = {
        .attr       = __ATTR(pru_msg_box, 0660, sysfs_pru_msg_system_show,
                             sysfs_pru_msg_system_store),
        .val_offset = 0};

struct kobj_attr_struct_s attr_prog_state = {
        .attr       = __ATTR(state, 0660, sysfs_prog_state_show, sysfs_prog_state_store),
        .val_offset = offsetof(struct SharedMem, programmer_ctrl) + offsetof(struct ProgrammerCtrl, state)};
struct kobj_attr_struct_s attr_prog_protocol = {
        .attr       = __ATTR(protocol, 0660, sysfs_prog_protocol_show, sysfs_prog_protocol_store),
        .val_offset = offsetof(struct SharedMem, programmer_ctrl) + offsetof(struct ProgrammerCtrl, protocol)};
struct kobj_attr_struct_s attr_prog_datarate = {
        .attr       = __ATTR(datarate, 0660, sysfs_SharedMem_show, sysfs_prog_datarate_store),
        .val_offset = offsetof(struct SharedMem, programmer_ctrl) + offsetof(struct ProgrammerCtrl, datarate)};
struct kobj_attr_struct_s attr_prog_datasize = {
        .attr       = __ATTR(datasize, 0660, sysfs_SharedMem_show, sysfs_prog_datasize_store),
        .val_offset = offsetof(struct SharedMem, programmer_ctrl) + offsetof(struct ProgrammerCtrl, datasize)};
struct kobj_attr_struct_s attr_prog_pin_tck = {
        .attr       = __ATTR(pin_tck, 0660, sysfs_SharedMem_show, sysfs_prog_pin_store),
        .val_offset = offsetof(struct SharedMem, programmer_ctrl) + offsetof(struct ProgrammerCtrl, pin_tck)};
struct kobj_attr_struct_s attr_prog_pin_tdio = {
        .attr       = __ATTR(pin_tdio, 0660, sysfs_SharedMem_show, sysfs_prog_pin_store),
        .val_offset = offsetof(struct SharedMem, programmer_ctrl) + offsetof(struct ProgrammerCtrl, pin_tdio)};
struct kobj_attr_struct_s attr_prog_pin_tdo = {
        .attr       = __ATTR(pin_tdo, 0660, sysfs_SharedMem_show, sysfs_prog_pin_store),
        .val_offset = offsetof(struct SharedMem, programmer_ctrl) + offsetof(struct ProgrammerCtrl, pin_tdo)};
struct kobj_attr_struct_s attr_prog_pin_tms = {
        .attr       = __ATTR(pin_tms, 0660, sysfs_SharedMem_show, sysfs_prog_pin_store),
        .val_offset = offsetof(struct SharedMem, programmer_ctrl) + offsetof(struct ProgrammerCtrl, pin_tms)};

struct kobj_attribute attr_sync_error =
        __ATTR(error, 0660, sysfs_sync_error_show, NULL);

struct kobj_attribute attr_sync_correction =
        __ATTR(correction, 0660, sysfs_sync_correction_show, NULL);

struct kobj_attribute attr_sync_error_sum =
        __ATTR(error_sum, 0660, sysfs_sync_error_sum_show, NULL);

static struct attribute *pru_attrs[] = {
        &attr_n_buffers.attr.attr,
        &attr_samples_per_buffer.attr.attr,
        &attr_buffer_period_ns.attr.attr,
        &attr_mode.attr.attr,
        &attr_auxiliary_voltage.attr.attr,
        &attr_calibration_settings.attr.attr,
        &attr_virtual_converter_settings.attr.attr,
        &attr_virtual_harvester_settings.attr.attr,
        &attr_pru_msg_system_settings.attr.attr,
        NULL,
};

static struct attribute_group attr_group = {
        .attrs = pru_attrs,
};

static struct attribute *pru_mem_attrs[] = {
        &attr_mem_base_addr.attr.attr,
        &attr_mem_size.attr.attr,
        NULL,
};

static struct attribute_group attr_mem_group = {
        .attrs = pru_mem_attrs,
};

static struct attribute *pru_prog_attrs[] = {
        &attr_prog_state.attr.attr,
        &attr_prog_protocol.attr.attr,
        &attr_prog_datarate.attr.attr,
        &attr_prog_datasize.attr.attr,
        &attr_prog_pin_tck.attr.attr,
        &attr_prog_pin_tdio.attr.attr,
        &attr_prog_pin_tdo.attr.attr,
        &attr_prog_pin_tms.attr.attr,
        NULL,
};

static struct attribute_group attr_prog_group = {
        .attrs = pru_prog_attrs,
};

static struct attribute *pru_sync_attrs[] = {
        &attr_sync_error.attr,
        &attr_sync_error_sum.attr,
        &attr_sync_correction.attr,
        NULL,
};

static struct attribute_group attr_sync_group = {
        .attrs = pru_sync_attrs,
};

static ssize_t sysfs_SharedMem_show(struct kobject        *kobj,
                                    struct kobj_attribute *attr, char *buf)
{
    struct kobj_attr_struct_s *kobj_attr_wrapped;

    kobj_attr_wrapped = container_of(attr, struct kobj_attr_struct_s, attr);
    return sprintf(
            buf, "%u",
            readl(pru_shared_mem_io + kobj_attr_wrapped->val_offset));
}

static ssize_t sysfs_sync_error_show(struct kobject        *kobj,
                                     struct kobj_attribute *attr, char *buf)
{
    return sprintf(buf, "%lld", sync_data->error_now);
}

static ssize_t sysfs_sync_error_sum_show(struct kobject        *kobj,
                                         struct kobj_attribute *attr, char *buf)
{
    return sprintf(buf, "%lld", sync_data->error_sum);
}

static ssize_t sysfs_sync_correction_show(struct kobject        *kobj,
                                          struct kobj_attribute *attr,
                                          char                  *buf)
{
    return sprintf(buf, "%d", sync_data->clock_corr);
}

static ssize_t sysfs_state_show(struct kobject        *kobj,
                                struct kobj_attribute *attr, char *buf)
{
    switch (pru_comm_get_state())
    {
        case STATE_IDLE:
            return sprintf(buf, "idle");
        case STATE_ARMED:
            return sprintf(buf, "armed");
        case STATE_RUNNING:
            return sprintf(buf, "running");
        case STATE_RESET:
            return sprintf(buf, "reset");
        case STATE_FAULT:
            return sprintf(buf, "fault");
        default:
            return sprintf(buf, "unknown");
    }
}

static ssize_t sysfs_state_store(struct kobject        *kobj,
                                 struct kobj_attribute *attr, const char *buf,
                                 size_t count)
{
    struct timespec ts_now;
    int             tmp;

    if (strncmp(buf, "start", 5) == 0)
    {
        if ((count < 5) || (count > 6))
            return -EINVAL;

        if (pru_comm_get_state() != STATE_IDLE)
            return -EBUSY;

        pru_comm_set_state(STATE_RUNNING);
        return count;
    }

    else if (strncmp(buf, "stop", 4) == 0)
    {
        if ((count < 4) || (count > 5))
            return -EINVAL;

        pru_comm_cancel_delayed_start();
        pru_comm_set_state(STATE_RESET);
        return count;
    }

    else if (sscanf(buf, "%d", &tmp) == 1)
    {
        /* Timestamp system clock */

        if (pru_comm_get_state() != STATE_IDLE)
            return -EBUSY;

        getnstimeofday(&ts_now);
        if (tmp < ts_now.tv_sec + 1)
            return -EINVAL;
        printk(KERN_INFO "shprd.k: Setting start-timestamp to %d", tmp);
        pru_comm_set_state(STATE_ARMED);
        pru_comm_schedule_delayed_start(tmp);
        return count;
    }
    else
        return -EINVAL;
}

static ssize_t sysfs_mode_show(struct kobject        *kobj,
                               struct kobj_attribute *attr, char *buf)
{
    struct kobj_attr_struct_s *kobj_attr_wrapped;
    unsigned int               mode;

    kobj_attr_wrapped = container_of(attr, struct kobj_attr_struct_s, attr);

    mode              = readl(pru_shared_mem_io + kobj_attr_wrapped->val_offset);

    switch (mode)
    {
        case MODE_HARVESTER:
            return sprintf(buf, "harvester");
        case MODE_HRV_ADC_READ:
            return sprintf(buf, "hrv_adc_read");
        case MODE_EMULATOR:
            return sprintf(buf, "emulator");
        case MODE_EMU_ADC_READ:
            return sprintf(buf, "emu_adc_read");
        case MODE_DEBUG:
            return sprintf(buf, "debug");
        case MODE_NONE:
            return sprintf(buf, "none");
        default:
            return -EINVAL;
    }
}

static ssize_t sysfs_mode_store(struct kobject        *kobj,
                                struct kobj_attribute *attr, const char *buf,
                                size_t count)
{
    struct kobj_attr_struct_s *kobj_attr_wrapped;
    unsigned int               mode;

    if (pru_comm_get_state() != STATE_IDLE)
        return -EBUSY;

    kobj_attr_wrapped = container_of(attr, struct kobj_attr_struct_s, attr);

    if (pru_comm_get_state() != STATE_IDLE)
        return -EBUSY;

    // note: longer string must come first in case of similar strings (emulation_cal, emulation)
    if (strncmp(buf, "harvester", 9) == 0)
    {
        if ((count < 9) || (count > 10)) return -EINVAL;
        mode = MODE_HARVESTER;
    }
    else if (strncmp(buf, "hrv_adc_read", 12) == 0)
    {
        if ((count < 12) || (count > 13)) return -EINVAL;
        mode = MODE_HRV_ADC_READ;
    }
    else if (strncmp(buf, "emulator", 8) == 0)
    {
        if ((count < 8) || (count > 9)) return -EINVAL;
        mode = MODE_EMULATOR;
    }
    else if (strncmp(buf, "emu_adc_read", 12) == 0)
    {
        if ((count < 12) || (count > 13)) return -EINVAL;
        mode = MODE_EMU_ADC_READ;
    }
    else if (strncmp(buf, "debug", 5) == 0)
    {
        if ((count < 5) || (count > 6)) return -EINVAL;
        mode = MODE_DEBUG;
    }
    else
        return -EINVAL;

    writel(mode, pru_shared_mem_io + kobj_attr_wrapped->val_offset);
    printk(KERN_INFO "shprd.k: new mode = %d (%s)", mode, buf);
    pru_comm_set_state(STATE_RESET);
    return count;
}

static ssize_t sysfs_auxiliary_voltage_store(struct kobject        *kobj,
                                             struct kobj_attribute *attr,
                                             const char *buf, size_t count)
{
    unsigned int               tmp;
    struct kobj_attr_struct_s *kobj_attr_wrapped;

    if (pru_comm_get_state() != STATE_IDLE)
        return -EBUSY;

    kobj_attr_wrapped = container_of(attr, struct kobj_attr_struct_s, attr);

    if (sscanf(buf, "%u", &tmp) == 1)
    {
        printk(KERN_INFO "shprd.k: Setting auxiliary DAC-voltage to raw %u",
               tmp);
        writel(tmp, pru_shared_mem_io + kobj_attr_wrapped->val_offset);

        pru_comm_set_state(STATE_RESET); // TODO: really needed?
        return count;
    }

    return -EINVAL;
}

static ssize_t sysfs_calibration_settings_store(struct kobject        *kobj,
                                                struct kobj_attribute *attr,
                                                const char *buf, size_t count)
{
    struct CalibrationConfig   tmp;
    struct kobj_attr_struct_s *kobj_attr_wrapped;

    if (pru_comm_get_state() != STATE_IDLE)
        return -EBUSY;

    kobj_attr_wrapped = container_of(attr, struct kobj_attr_struct_s, attr);

    if (sscanf(buf, "%u %d %u %d %u %d",
               &tmp.adc_current_factor_nA_n8, &tmp.adc_current_offset_nA,
               &tmp.adc_voltage_factor_uV_n8, &tmp.adc_voltage_offset_uV,
               &tmp.dac_voltage_inv_factor_uV_n20, &tmp.dac_voltage_offset_uV) == 6)
    {
        printk(KERN_INFO
               "shprd: Setting ADC-Current calibration config. gain: %d, offset: %d",
               tmp.adc_current_factor_nA_n8, tmp.adc_current_offset_nA);

        printk(KERN_INFO
               "shprd: Setting ADC-Voltage calibration config. gain: %d, offset: %d",
               tmp.adc_voltage_factor_uV_n8, tmp.adc_voltage_offset_uV);

        printk(KERN_INFO
               "shprd: Setting DAC-Voltage calibration config. gain: %d, offset: %d",
               tmp.dac_voltage_inv_factor_uV_n20, tmp.dac_voltage_offset_uV);

        writel(tmp.adc_current_factor_nA_n8,
               pru_shared_mem_io + kobj_attr_wrapped->val_offset + 0);
        writel(tmp.adc_current_offset_nA,
               pru_shared_mem_io + kobj_attr_wrapped->val_offset + 4);
        writel(tmp.adc_voltage_factor_uV_n8,
               pru_shared_mem_io + kobj_attr_wrapped->val_offset + 8);
        writel(tmp.adc_voltage_offset_uV,
               pru_shared_mem_io + kobj_attr_wrapped->val_offset + 12);
        writel(tmp.dac_voltage_inv_factor_uV_n20,
               pru_shared_mem_io + kobj_attr_wrapped->val_offset + 16);
        writel(tmp.dac_voltage_offset_uV,
               pru_shared_mem_io + kobj_attr_wrapped->val_offset + 20);
        /* TODO: this should copy the struct in one go */

        return count;
    }

    return -EINVAL;
}

static ssize_t sysfs_calibration_settings_show(struct kobject        *kobj,
                                               struct kobj_attribute *attr, char *buf)
{
    struct kobj_attr_struct_s *kobj_attr_wrapped;

    kobj_attr_wrapped = container_of(attr, struct kobj_attr_struct_s, attr);
    return sprintf(
            buf, "%u %d \n%u %d \n%u %d \n",
            readl(pru_shared_mem_io + kobj_attr_wrapped->val_offset + 0),
            readl(pru_shared_mem_io + kobj_attr_wrapped->val_offset + 4),
            readl(pru_shared_mem_io + kobj_attr_wrapped->val_offset + 8),
            readl(pru_shared_mem_io + kobj_attr_wrapped->val_offset + 12),
            readl(pru_shared_mem_io + kobj_attr_wrapped->val_offset + 16),
            readl(pru_shared_mem_io + kobj_attr_wrapped->val_offset + 20));
}

static ssize_t sysfs_virtual_converter_settings_store(struct kobject        *kobj,
                                                      struct kobj_attribute *attr,
                                                      const char *buffer, size_t count)
{
    const uint32_t             inp_lut_size = LUT_SIZE * LUT_SIZE * 1u;
    const uint32_t             out_lut_size = LUT_SIZE * 4u;
    const uint32_t             non_lut_size = sizeof(struct ConverterConfig) - inp_lut_size - out_lut_size;
    struct kobj_attr_struct_s *kobj_attr_wrapped;
    uint32_t                   mem_offset = 0u;
    int                        buf_pos    = 0;
    uint32_t                   i          = 0u;

    if (pru_comm_get_state() != STATE_IDLE)
        return -EBUSY;

    kobj_attr_wrapped = container_of(attr, struct kobj_attr_struct_s, attr);

    /* u32 beginning of struct */
    mem_offset        = kobj_attr_wrapped->val_offset;
    for (i = 0; i < non_lut_size; i += 4)
    {
        uint32_t value_retrieved, value_length;
        int      ret = sscanf(&buffer[buf_pos], "%u%n ", &value_retrieved, &value_length);
        buf_pos += value_length;
        if (ret != 1) return -EINVAL;
        writel(value_retrieved, pru_shared_mem_io + mem_offset + i);
    }

    /* u8 input LUT */
    mem_offset = kobj_attr_wrapped->val_offset + non_lut_size;
    for (i = 0; i < inp_lut_size; i += 1)
    {
        uint32_t value_retrieved, value_length;
        int      ret = sscanf(&buffer[buf_pos], "%u%n ", &value_retrieved, &value_length);
        buf_pos += value_length;
        if (ret != 1) return -EINVAL;
        if (value_retrieved > 255) printk(KERN_WARNING "shprd.k: virtual Converter parsing got a u8-value out of bound");
        writeb((uint8_t) value_retrieved, pru_shared_mem_io + mem_offset + i);
    }

    /* u32 output LUT */
    mem_offset = kobj_attr_wrapped->val_offset + non_lut_size + inp_lut_size;
    for (i = 0; i < out_lut_size; i += 4)
    {
        uint32_t value_retrieved, value_length;
        int      ret = sscanf(&buffer[buf_pos], "%u%n ", &value_retrieved, &value_length);
        buf_pos += value_length;
        if (ret != 1) return -EINVAL;
        writel(value_retrieved, pru_shared_mem_io + mem_offset + i);
    }

    printk(KERN_INFO "shprd.k: Setting Virtual Converter Config");

    return count;
}

static ssize_t sysfs_virtual_converter_settings_show(struct kobject        *kobj,
                                                     struct kobj_attribute *attr, char *buf)
{
    const uint32_t             inp_lut_size = LUT_SIZE * LUT_SIZE * 1u;
    const uint32_t             out_lut_size = LUT_SIZE * 4u;
    const uint32_t             non_lut_size = sizeof(struct ConverterConfig) - inp_lut_size - out_lut_size;
    struct kobj_attr_struct_s *kobj_attr_wrapped;
    uint32_t                   mem_offset = 0u;
    uint32_t                   i          = 0u;
    int                        count      = 0;

    kobj_attr_wrapped                     = container_of(attr, struct kobj_attr_struct_s, attr);

    /* u32 beginning of struct */
    mem_offset                            = kobj_attr_wrapped->val_offset;
    for (i = 0; i < non_lut_size; i += 4)
    {
        count += sprintf(buf + strlen(buf), "%u \n", readl(pru_shared_mem_io + mem_offset + i));
    }

    /* u8 input LUT */
    mem_offset = kobj_attr_wrapped->val_offset + non_lut_size;
    for (i = 0; i < inp_lut_size; i += 1)
    {
        count += sprintf(buf + strlen(buf), "%u ", readb(pru_shared_mem_io + mem_offset + i));
    }
    count += sprintf(buf + strlen(buf), "\n");

    /* u32 output LUT */
    mem_offset = kobj_attr_wrapped->val_offset + non_lut_size + inp_lut_size;
    for (i = 0; i < out_lut_size; i += 4)
    {
        count += sprintf(buf + strlen(buf), "%u ", readl(pru_shared_mem_io + mem_offset + i));
    }
    count += sprintf(buf + strlen(buf), "\n");
    printk(KERN_INFO "shprd.k: reading struct ConverterConfig");
    return count;
}

static ssize_t sysfs_virtual_harvester_settings_store(struct kobject        *kobj,
                                                      struct kobj_attribute *attr,
                                                      const char *buffer, size_t count)
{
    static const uint32_t      struct_size = sizeof(struct HarvesterConfig);
    struct kobj_attr_struct_s *kobj_attr_wrapped;
    uint32_t                   mem_offset = 0u;
    int                        buf_pos    = 0;
    uint32_t                   i          = 0u;

    if (pru_comm_get_state() != STATE_IDLE)
        return -EBUSY;

    kobj_attr_wrapped = container_of(attr, struct kobj_attr_struct_s, attr);
    mem_offset        = kobj_attr_wrapped->val_offset;
    for (i = 0; i < struct_size; i += 4)
    {
        uint32_t value_retrieved, value_length;
        int      ret = sscanf(&buffer[buf_pos], "%u%n ", &value_retrieved, &value_length);
        buf_pos += value_length;
        if (ret != 1) return -EINVAL;
        writel(value_retrieved, pru_shared_mem_io + mem_offset + i);
    }
    printk(KERN_INFO "shprd.k: writing struct HarvesterConfig");
    return count;
}

static ssize_t sysfs_virtual_harvester_settings_show(struct kobject        *kobj,
                                                     struct kobj_attribute *attr, char *buf)
{
    static const uint32_t      struct_size = sizeof(struct HarvesterConfig);
    struct kobj_attr_struct_s *kobj_attr_wrapped;
    uint32_t                   mem_offset = 0u;
    uint32_t                   i          = 0u;
    int                        count      = 0;

    kobj_attr_wrapped                     = container_of(attr, struct kobj_attr_struct_s, attr);
    mem_offset                            = kobj_attr_wrapped->val_offset;
    for (i = 0; i < struct_size; i += 4)
    {
        count += sprintf(buf + strlen(buf), "%u \n", readl(pru_shared_mem_io + mem_offset + i));
    }
    printk(KERN_INFO "shprd.k: reading struct HarvesterConfig");
    return count;
}

static ssize_t sysfs_pru_msg_system_store(struct kobject        *kobj,
                                          struct kobj_attribute *attr,
                                          const char *buffer, size_t count)
{
    struct ProtoMsg pru_msg;

    if (sscanf(buffer, "%hhu %u %u", &pru_msg.type, &pru_msg.value[0], &pru_msg.value[1]) != 0)
    {
        put_msg_to_pru(&pru_msg);
        return count;
    }

    return -EINVAL;
}

static ssize_t sysfs_pru_msg_system_show(struct kobject        *kobj,
                                         struct kobj_attribute *attr, char *buf)
{
    int             count = 0;
    struct ProtoMsg pru_msg;

    if (get_msg_from_pru(&pru_msg))
    {
        count += sprintf(buf + strlen(buf), "%hhu %u %u", pru_msg.type, pru_msg.value[0], pru_msg.value[1]);
    }
    else
    {
        count += sprintf(buf + strlen(buf), "%hhu ", 0x00u);
    }
    return count;
}


static ssize_t sysfs_prog_state_show(struct kobject        *kobj,
                                     struct kobj_attribute *attr, char *buf)
{
    struct kobj_attr_struct_s *kobj_attr_wrapped;
    uint32_t                   value;
    kobj_attr_wrapped = container_of(attr, struct kobj_attr_struct_s, attr);
    value             = readl(pru_shared_mem_io + kobj_attr_wrapped->val_offset);
    if (value == 0)
        return sprintf(buf, "idle");
    else if (value == 1)
        return sprintf(buf, "starting");
    else if (value == 2)
        return sprintf(buf, "initializing");
    else if (value == 0xBAAAAAADu)
        return sprintf(buf, "error");
    else
        return sprintf(buf, "running - %u", value);
}

static ssize_t sysfs_prog_state_store(struct kobject        *kobj,
                                      struct kobj_attribute *attr,
                                      const char *buffer, size_t count)
{
    struct kobj_attr_struct_s *kobj_attr_wrapped;
    uint32_t                   value = 0u;
    kobj_attr_wrapped                = container_of(attr, struct kobj_attr_struct_s, attr);

    if (strncmp(buffer, "start", 5) == 0)
        value = 1;
    else if (strncmp(buffer, "stop", 4) == 0)
        value = 0;
    else
        return -EINVAL;

    if ((value > 0) && (pru_comm_get_state() != STATE_IDLE))
        return -EBUSY;
    // TODO: kernel should test validity of struct (instead of pru) -> best place is here

    writel(value, pru_shared_mem_io + kobj_attr_wrapped->val_offset);
    return count;
}

static ssize_t sysfs_prog_protocol_show(struct kobject        *kobj,
                                        struct kobj_attribute *attr, char *buf)
{
    struct kobj_attr_struct_s *kobj_attr_wrapped;
    kobj_attr_wrapped = container_of(attr, struct kobj_attr_struct_s, attr);

    switch (readl(pru_shared_mem_io + kobj_attr_wrapped->val_offset))
    {
        case 1:
            return sprintf(buf, "swd");
        case 2:
            return sprintf(buf, "sbw");
        case 3:
            return sprintf(buf, "jtag");
        default:
            return sprintf(buf, "unknown");
    }
}

static ssize_t sysfs_prog_protocol_store(struct kobject        *kobj,
                                         struct kobj_attribute *attr,
                                         const char *buffer, size_t count)
{
    struct kobj_attr_struct_s *kobj_attr_wrapped;
    uint32_t                   value = 0u;

    if (pru_comm_get_state() != STATE_IDLE)
        return -EBUSY;

    kobj_attr_wrapped = container_of(attr, struct kobj_attr_struct_s, attr);

    if (strncmp(buffer, "swd", 3) == 0)
        value = 1;
    else if (strncmp(buffer, "sbw", 3) == 0)
        value = 2;
    else if (strncmp(buffer, "jtag", 4) == 0)
        value = 3;
    else
    {
        printk(KERN_INFO "shprd.k: setting programmer-protocol failed -> unknown value");
        return -EINVAL;
    }

    writel(value, pru_shared_mem_io + kobj_attr_wrapped->val_offset);
    return count;
}

static ssize_t sysfs_prog_datarate_store(struct kobject        *kobj,
                                         struct kobj_attribute *attr,
                                         const char *buffer, size_t count)
{
    struct kobj_attr_struct_s *kobj_attr_wrapped;
    uint32_t                   value;

    if (pru_comm_get_state() != STATE_IDLE)
        return -EBUSY;

    kobj_attr_wrapped = container_of(attr, struct kobj_attr_struct_s, attr);

    if (sscanf(buffer, "%u", &value) != 1)
        return -EINVAL;
    if ((value < 1) || (value > 10000000)) // TODO: replace with valid boundaries
        return -EINVAL;
    writel(value, pru_shared_mem_io + kobj_attr_wrapped->val_offset);
    return count;
}

static ssize_t sysfs_prog_datasize_store(struct kobject        *kobj,
                                         struct kobj_attribute *attr,
                                         const char *buffer, size_t count)
{
    struct kobj_attr_struct_s *kobj_attr_wrapped;
    uint32_t                   value;
    uint32_t                   value_max;

    if (pru_comm_get_state() != STATE_IDLE)
        return -EBUSY;

    kobj_attr_wrapped = container_of(attr, struct kobj_attr_struct_s, attr);
    value_max         = readl(pru_shared_mem_io + offsetof(struct SharedMem, mem_size));

    if (sscanf(buffer, "%u", &value) != 1)
        return -EINVAL;
    if ((value < 1) || (value > value_max))
        return -EINVAL;
    writel(value, pru_shared_mem_io + kobj_attr_wrapped->val_offset);
    return count;
}

static ssize_t sysfs_prog_pin_store(struct kobject        *kobj,
                                    struct kobj_attribute *attr,
                                    const char *buffer, size_t count)
{
    struct kobj_attr_struct_s *kobj_attr_wrapped;
    uint32_t                   value;

    if (pru_comm_get_state() != STATE_IDLE)
        return -EBUSY;

    kobj_attr_wrapped = container_of(attr, struct kobj_attr_struct_s, attr);

    if (sscanf(buffer, "%u", &value) != 1)
        return -EINVAL;
    if (value > 10000) // TODO: replace with proper range-test for valid pin-def
        return -EINVAL;
    writel(value, pru_shared_mem_io + kobj_attr_wrapped->val_offset);
    return count;
}


int sysfs_interface_init(void)
{
    int retval = 0;

    kobj_ref   = kobject_create_and_add("shepherd", NULL);

    if ((retval = sysfs_create_file(kobj_ref, &attr_state.attr)))
    {
        printk(KERN_ERR "shprd.k: Cannot create sysfs state attrib");
        goto r_sysfs;
    }

    if ((retval = sysfs_create_group(kobj_ref, &attr_group)))
    {
        printk(KERN_ERR "shprd.k: cannot create sysfs attrib group");
        goto r_state;
    };

    kobj_mem_ref = kobject_create_and_add("memory", kobj_ref);

    if ((retval = sysfs_create_group(kobj_mem_ref, &attr_mem_group)))
    {
        printk(KERN_ERR
               "shprd.k: cannot create sysfs memory attrib group");
        goto r_group;
    };

    kobj_sync_ref = kobject_create_and_add("sync", kobj_ref);

    if ((retval = sysfs_create_group(kobj_sync_ref, &attr_sync_group)))
    {
        printk(KERN_ERR
               "shprd.k: cannot create sysfs sync attrib group");
        goto r_mem;
    };

    kobj_prog_ref = kobject_create_and_add("programmer", kobj_ref);

    if ((retval = sysfs_create_group(kobj_prog_ref, &attr_prog_group)))
    {
        printk(KERN_ERR
               "shprd.k: cannot create sysfs programmer attrib group");
        goto r_mem;
    };

    return 0;

r_mem:
    kobject_put(kobj_mem_ref);
r_group:
    sysfs_remove_group(kobj_ref, &attr_group);
r_state:
    sysfs_remove_file(kobj_ref, &attr_state.attr);
r_sysfs:
    kobject_put(kobj_ref);

    return retval;
}

void sysfs_interface_exit(void)
{
    sysfs_remove_group(kobj_ref, &attr_group);
    sysfs_remove_file(kobj_ref, &attr_state.attr);
    kobject_put(kobj_prog_ref);
    kobject_put(kobj_sync_ref);
    kobject_put(kobj_mem_ref);
    kobject_put(kobj_ref);
}
