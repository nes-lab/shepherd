from virtual_harvester_data import VirtualHarvesterData


class KernelHrvStruct:
    def __init__(self, setting):
        # Kernel-Task -> Map settings-list to internal state-vars struct HarvesterConfig
        # NOTE:
        #  - yaml is based on si-units like nA, mV, ms, uF
        #  - c-code and py-copy is using nA, uV, ns, nF, fW, raw
        setting = VirtualHarvesterData(setting)
        values = setting.export_for_sysfs()
        self.algorithm: int = values[0]
        self.hrv_mode: int = values[1]
        self.window_size: int = values[2]
        self.voltage_uV: int = values[3]
        self.voltage_min_uV: int = values[4]
        self.voltage_max_uV: int = values[5]
        self.voltage_step_uV: int = values[6]
        self.current_limit_nA: int = values[7]
        self.setpoint_n8: int = values[8]
        self.interval_n: int = values[9]
        self.duration_n: int = values[10]
        self.wait_cycles_n: int = values[11]


class VirtualHarvesterModel:
    """
    this is ported py-version of the pru-code, goals:
    - stay close to original code-base
    - offer a comparison for the tests
    - step 1 to a virtualization of emulation
    NOTE1: DO NOT OPTIMIZE -> stay close to original c-code-base
    NOTE2: adc-harvest-routines are not part of this model (virtual_harvester lines 66:289)
    Compromises:
    - Py has to map the settings-list to internal vars -> is kernel-task
    - Python has no static vars -> FName_reset is handling the class-vars
    """

    cfg: KernelHrvStruct = None

    HRV_IVCURVE: int = 2**4
    HRV_CV: int = 2**8
    HRV_MPPT_VOC: int = 2**12
    HRV_MPPT_PO: int = 2**13
    HRV_MPPT_OPT: int = 2**14

    # INIT static vars: CV
    voltage_last: int = 0
    current_last: int = 0
    compare_last: int = 0

    # INIT static vars: VOC
    age_now: int = 0
    voc_now: int = 0
    age_nxt: int = 0
    voc_nxt: int = 0

    # INIT static vars: PO
    # already done: interval step
    power_last: int = 0

    # INIT static vars: OPT
    # already done: age_now, age_nxt
    power_now: int = 0
    voltage_now: int = 0
    current_now: int = 0
    power_nxt: int = 0
    voltage_nxt: int = 0
    current_nxt: int = 0

    def __init__(self, setting):

        self.cfg = KernelHrvStruct(setting)

        # INIT global vars: shared states
        self.voltage_set_uV: int = self.cfg.voltage_uV + 1
        # self.settle_steps: int = 0  # adc_ivcurve
        self.interval_step: int = 2**30

        self.is_rising: bool = self.cfg.hrv_mode & (2**1)

        # PO-Relevant (iv & adc)
        self.volt_step_uV: int = self.cfg.voltage_step_uV

        # self.power_last_raw: int = 0  # adc_mppt_po

        # globals for iv_cv
        self.voltage_hold: int = 0
        self.current_hold: int = 0
        self.voltage_step_x4_uV: int = self.cfg.voltage_step_uV * 4

    def iv_sample(self, _voltage_uV: int, _current_nA: int) -> tuple:
        if self.cfg.window_size <= 1:
            return _voltage_uV, _current_nA
        if self.cfg.algorithm >= self.HRV_MPPT_OPT:
            return self.iv_mppt_opt(_voltage_uV, _current_nA)
        if self.cfg.algorithm >= self.HRV_MPPT_PO:
            return self.iv_mppt_po(_voltage_uV, _current_nA)
        if self.cfg.algorithm >= self.HRV_MPPT_VOC:
            return self.iv_mppt_voc(_voltage_uV, _current_nA)
        if self.cfg.algorithm >= self.HRV_CV:
            return self.iv_cv(_voltage_uV, _current_nA)
        # next line is only implied in C
        return _voltage_uV, _current_nA

    def iv_cv(self, _voltage_uV: int, _current_nA: int) -> tuple:
        compare_now = _voltage_uV < self.voltage_set_uV
        step_size_now = abs(_voltage_uV - self.voltage_last)
        distance_now = abs(_voltage_uV - self.voltage_set_uV)
        distance_last = abs(self.voltage_last - self.voltage_set_uV)

        if compare_now != self.compare_last and step_size_now < self.voltage_step_x4_uV:
            if distance_now < distance_last and distance_now < self.voltage_step_x4_uV:
                self.voltage_hold = _voltage_uV
                self.current_hold = _current_nA
            elif distance_last < distance_now and distance_last < self.voltage_step_x4_uV:
                self.voltage_hold = self.voltage_last
                self.current_hold = self.voltage_last

        self.voltage_last = _voltage_uV
        self.current_last = _current_nA
        self.compare_last = compare_now
        return self.voltage_hold, self.current_hold

    def iv_mppt_voc(self, _voltage_uV: int, _current_nA: int) -> tuple:
        self.interval_step = (self.interval_step + 1) % self.cfg.interval_n
        self.age_nxt += 1
        self.age_now += 1

        if (
            (_current_nA < self.cfg.current_limit_nA)
            and (_voltage_uV < self.voc_nxt)
            and (_voltage_uV >= self.cfg.voltage_min_uV)
            and (_voltage_uV <= self.cfg.voltage_max_uV)
        ):
            self.voc_nxt = _voltage_uV
            self.age_nxt = 0

        if (self.age_now > self.cfg.window_size) or (self.voc_nxt <= self.voc_now):
            self.age_now = self.age_nxt
            self.voc_now = self.voc_nxt
            self.age_nxt = 0
            self.voc_nxt = self.cfg.voltage_max_uV

        _voltage_uV, _current_nA = self.iv_cv(_voltage_uV, _current_nA)
        if self.interval_step < self.cfg.duration_n:
            self.voltage_set_uV = int(self.voc_now * self.cfg.setpoint_n8 / 256)
            _current_nA = 0

        return _voltage_uV, _current_nA

    def iv_mppt_po(self, _voltage_uV: int, _current_nA: int) -> tuple:
        self.interval_step = (self.interval_step + 1) % self.cfg.interval_n

        _voltage_uV, _current_nA = self.iv_cv(_voltage_uV, _current_nA)

        if self.interval_step == 0:
            power_now = _voltage_uV * _current_nA
            if power_now > self.power_last:
                if self.is_rising:
                    self.voltage_set_uV += self.volt_step_uV
                else:
                    self.voltage_set_uV -= self.volt_step_uV
                self.volt_step_uV *= 2
            else:
                self.is_rising ^= 1
                self.volt_step_uV = self.cfg.voltage_step_uV
                if self.is_rising:
                    self.voltage_set_uV += self.volt_step_uV
                else:
                    self.voltage_set_uV -= self.volt_step_uV

            self.power_last = power_now

            if self.voltage_set_uV >= self.cfg.voltage_max_uV:
                self.voltage_set_uV = self.cfg.voltage_max_uV
                self.is_rising = 0
                self.volt_step_uV = self.cfg.voltage_step_uV
            if self.voltage_set_uV <= self.cfg.voltage_min_uV:
                self.voltage_set_uV = self.cfg.voltage_min_uV
                self.is_rising = 1
                self.volt_step_uV = self.cfg.voltage_step_uV

        return self.iv_cv(_voltage_uV, _current_nA)

    def iv_mppt_opt(self, _voltage_uV: int, _current_nA: int) -> tuple:
        self.age_now += 1
        self.age_nxt += 1

        power_fW = _voltage_uV * _current_nA
        if (
            (power_fW > self.power_nxt)
            and (_voltage_uV >= self.cfg.voltage_min_uV)
            and (_voltage_uV <= self.cfg.voltage_max_uV)
        ):
            self.age_nxt = 0
            self.power_nxt = power_fW
            self.voltage_nxt = _voltage_uV
            self.current_nxt = _current_nA

        if (self.age_now > self.cfg.window_size) or (self.power_nxt >= self.power_now):
            self.age_now = self.age_nxt
            self.power_now = self.power_nxt
            self.voltage_now = self.voltage_nxt
            self.current_now = self.current_nxt
            self.age_nxt = 0
            self.power_nxt = 0
            self.voltage_nxt = 0
            self.current_nxt = 0

        return self.voltage_now, self.current_now
