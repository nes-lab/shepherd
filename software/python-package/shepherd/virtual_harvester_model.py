from virtual_harvester_data import VirtualHarvesterData


class VirtualHarvesterModel(object):
    """
    this is ported py-version of the pru-code, goals:
    - stay close to original code-base
    - offer a comparison for the tests
    - step 1 to a virtualization of emulation
    NOTE: DO NOT OPTIMIZE -> stay close to original c-code-base
    """

    HRV_IVCURVE = 2**4
    HRV_CV = 2**8
    HRV_MPPT_VOC = 2**12
    HRV_MPPT_PO = 2**13
    HRV_MPPT_OPT = 2**14

    def __init__(self, setting):

        # NOTE:
        #  - yaml is based on si-units like nA, mV, ms, uF
        #  - c-code and py-copy is using nA, uV, ns, nF, fW, raw
        setting = VirtualHarvesterData(setting)
        values = setting.export_for_sysfs()
        self.algorithm = values[0]
        self.window_size = values[1]
        self.voltage_uV = values[2]
        self.voltage_min_uV = values[3]
        self.voltage_max_uV = values[4]
        self.voltage_step_uV = values[5]
        self.current_limit_nA = values[6]
        self.setpoint_n8 = values[7]
        self.interval_n = values[8]
        self.duration_n = values[9]
        self.dac_resolution_bit = values[10]
        self.wait_cycles_n = values[11]

        # global states
        self.voltage_set_uV = self.voltage_uV
        self.windows_samples = self.window_size
        self.voltage_hold = 0
        self.current_hold = 0
        self.voltage_step_x4_uV = self.voltage_step_uV * 4

        # CV statics
        self.voltage_last = 0
        self.current_last = 0
        self.compare_last = 0

        # VOC statics
        self.age_now = 0
        self.voc_now = 0
        self.age_nxt = 0
        self.voc_nxt = 0
        self.interval_step = 2**30

        # PO statics
        # already done: interval step
        self.power_last = 0
        self.incr_direction = 1
        self.incr_step_uV = 100

        # OPT statics
        # already done: age_now, age_nxt
        self.power_now = 0
        self.voltage_now = 0
        self.current_now = 0
        self.power_nxt = 0
        self.voltage_nxt = 0
        self.current_nxt = 0

    def iv_sample(self, voltage_uV: int, current_nA: int) -> tuple:
        if self.window_size <= 1:
            return voltage_uV, current_nA
        elif self.algorithm >= self.HRV_MPPT_OPT:
            return self.iv_mppt_opt(voltage_uV, current_nA)
        elif self.algorithm >= self.HRV_MPPT_PO:
            return self.iv_mppt_po(voltage_uV, current_nA)
        elif self.algorithm >= self.HRV_MPPT_VOC:
            return self.iv_mppt_voc(voltage_uV, current_nA)
        elif self.algorithm >= self.HRV_CV:
            return self.iv_cv(voltage_uV, current_nA)

    def iv_cv(self, voltage_uV: int, current_nA: int) -> tuple:
        compare_now = voltage_uV < self.voltage_set_uV
        voltage_step = abs(voltage_uV - self.voltage_last)

        if (compare_now != self.compare_last) and (
            voltage_step < self.voltage_step_x4_uV
        ):
            if self.voltage_last < voltage_uV:
                self.voltage_hold = self.voltage_last
                self.current_hold = self.voltage_last
            else:
                self.voltage_hold = voltage_uV
                self.current_hold = current_nA

        self.voltage_last = voltage_uV
        self.current_last = current_nA
        self.compare_last = compare_now
        return self.voltage_hold, self.current_hold

    def iv_mppt_voc(self, voltage_uV: int, current_nA: int) -> tuple:
        self.interval_step = (
            0 if (self.interval_step >= self.interval_n) else (self.interval_step + 1)
        )
        self.age_now += 1
        self.age_nxt += 1

        if (
            (current_nA < self.current_limit_nA)
            and (voltage_uV < self.voc_nxt)
            and (voltage_uV >= self.voltage_min_uV)
            and (voltage_uV <= self.voltage_max_uV)
        ):
            self.voc_nxt = voltage_uV
            self.age_nxt = 0

        if (self.age_now > self.windows_samples) or (self.voc_nxt <= self.voc_now):
            self.age_now = self.age_nxt
            self.voc_now = self.voc_nxt
            self.age_nxt = 0
            self.voc_nxt = self.voltage_max_uV

        voltage_uV, current_nA = self.iv_cv(voltage_uV, current_nA)
        if self.interval_step < self.duration_n:
            self.voltage_set_uV = int(self.voc_now * self.setpoint_n8 / 256)
            current_nA = 0

        return voltage_uV, current_nA

    def iv_mppt_po(self, voltage_uV: int, current_nA: int) -> tuple:
        self.interval_step = (
            0 if (self.interval_step >= self.interval_n) else (self.interval_step + 1)
        )
        if self.interval_step == 0:
            power_now = voltage_uV * current_nA
            if power_now > self.power_last:
                if self.incr_direction:
                    self.voltage_set_uV += self.incr_step_uV
                else:
                    self.voltage_set_uV -= self.incr_step_uV
                self.incr_step_uV *= 2
            else:
                self.incr_direction ^= 1
                self.incr_step_uV = self.voltage_step_uV
                if self.incr_direction:
                    self.voltage_set_uV += self.incr_step_uV
                else:
                    self.voltage_set_uV -= self.incr_step_uV
            self.power_last = power_now
            self.voltage_set_uV = min(
                max(self.voltage_set_uV, self.voltage_min_uV), self.voltage_max_uV
            )
        return self.iv_cv(voltage_uV, current_nA)

    def iv_mppt_opt(self, voltage_uV: int, current_nA: int) -> tuple:
        self.age_now += 1
        self.age_nxt += 1

        power = voltage_uV * current_nA
        if (
            (power > self.power_nxt)
            and (voltage_uV >= self.voltage_min_uV)
            and (voltage_uV <= self.voltage_max_uV)
        ):
            self.age_nxt = 0
            self.power_nxt = power
            self.voltage_nxt = voltage_uV
            self.current_nxt = current_nA

        if (self.age_now > self.windows_samples) or (self.power_nxt >= self.power_now):
            self.age_now = self.age_nxt
            self.power_now = self.power_nxt
            self.voltage_now = self.voltage_nxt
            self.current_now = self.current_nxt
            self.age_nxt = 0
            self.power_nxt = 0
            self.voltage_nxt = 0
            self.current_nxt = 0

        return self.voltage_now, self.current_now
