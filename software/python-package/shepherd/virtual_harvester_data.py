from typing import NoReturn, Union
from pathlib import Path
import yaml
import logging
from shepherd.calibration_default import M_DAC
from shepherd.calibration import CalibrationData

logger = logging.getLogger(__name__)

# Currently implemented harvesters
# NOTE: numbers have meaning and will be tested ->
# - harvesting on "neutral" is not possible
# - emulation with "ivcurve" or lower is also resulting in Error
# - "_opt" has its own algo for emulation, but is only a fast mppt_po for harvesting
algorithms = {"neutral": 2**0,
              "ivcurve": 2**4,
              "cv": 2**8,
              #"ci": 2**9, # is this desired?
              "mppt_voc": 2**12,
              "mppt_po": 2**13,
              "mppt_opt": 2**14,
              }


class VirtualHarvesterData(object):
    """ TODO: this class is very similar to virtual_source_data, could share a base-class

    :param setting: harvester-config as name, path to yaml or already usable as dict
    :param samplerate_sps:
    :param for_emulation: unlocks a different kind of algorithms and constraints
    :param window_samples: complete length of the ivcurve (if applicable) -> steps * (1 + wait_cycles)
    """
    data: dict = {}
    name: str = "vHarvester"
    _default: str = "ivcurve"  # fallback in case of Setting = None
    _def_file = "virtual_harvester_defs.yml"
    _cal = CalibrationData.from_default()

    def __init__(self,
                 setting: Union[dict, str, Path],
                 samplerate_sps: int = 100_000,
                 for_emulation: bool = False,
                 window_samples: int = None,
                 ):

        self.samplerate_sps = samplerate_sps
        self.for_emulation = for_emulation
        def_path = Path(__file__).parent.resolve() / self._def_file
        with open(def_path, "r") as def_data:
            self._config_defs = yaml.safe_load(def_data)["harvesters"]
            self._config_base = self._config_defs["neutral"]
        self._inheritance = []

        if isinstance(setting, str) and Path(setting).exists():
            setting = Path(setting)
        if isinstance(setting, Path) and setting.exists() and \
                setting.is_file() and setting.suffix in [".yaml", ".yml"]:
            self._inheritance.append(str(setting))
            with open(setting, "r") as config_data:
                setting = yaml.safe_load(config_data)["harvesters"]
        if isinstance(setting, str):
            if setting in self._config_defs:
                self._inheritance.append(setting)
                setting = self._config_defs[setting]
            else:
                raise NotImplementedError(f"[{self.name}] was set to '{setting}', but definition missing in '{self._def_file}'")

        if setting is None:
            self._inheritance.append(self._default)
            self.data = self._config_defs[self._default]
        elif isinstance(setting, VirtualHarvesterData):
            self._inheritance.append(self.name + "-Element")
            self.data = setting.data
            self.samplerate_sps = setting.samplerate_sps
            self.for_emulation = setting.for_emulation
        elif isinstance(setting, dict):
            self._inheritance.append("parameter-dict")
            self.data = setting
        else:
            raise NotImplementedError(
                f"[{self.name}] {type(setting)}'{setting}' could not be handled. In case of file-path -> does it exist?")

        if window_samples is not None:
            self.data["window_samples"] = window_samples
        else:
            self.data["window_samples"] = 0

        self._check_and_complete()
        logger.debug(f"[{self.name}] initialized with the following inheritance-chain: '{self._inheritance}'")

    def _check_and_complete(self, verbose: bool = True) -> NoReturn:

        if "base" in self.data:
            base_name = self.data["base"]
        else:
            base_name = "neutral"

        if base_name in self._inheritance:
            raise ValueError(f"[{self.name}] loop detected in 'base'-inheritance-system @ '{base_name}' already in {self._inheritance}")
        else:
            self._inheritance.append(base_name)

        if base_name == "neutral":
            # root of recursive completion
            self._config_base = self._config_defs[base_name]
            logger.debug(f"[{self.name}] Parameter-Set will be completed with '{base_name}'-base")
            verbose = False
        elif base_name in self._config_defs:
            config_stash = self.data
            self.data = self._config_defs[base_name]
            logger.debug(f"[{self.name}] Parameter-Set will be completed with '{base_name}'-base")
            self._check_and_complete(verbose=False)
            self._config_base = self.data
            self.data = config_stash
        else:
            raise NotImplementedError(f"[{self.name}] converter-base '{base_name}' is unknown to system")

        self.data["algorithm_num"] = 0
        for base in self._inheritance:
            if base in algorithms:
                self.data["algorithm_num"] += algorithms[base]
        self._check_num("algorithm_num", verbose=verbose)

        self._check_num("window_size", 16, 512, verbose=verbose)

        self._check_num("voltage_min_mV", 0, 5000, verbose=verbose)
        self._check_num("voltage_max_mV", self.data["voltage_min_mV"], 5000, verbose=verbose)
        self._check_num("voltage_mV", self.data["voltage_min_mV"], self.data["voltage_max_mV"], verbose=verbose)

        current_limit_uA = 10**6 * self._cal.convert_raw_to_value("harvesting", "adc_current", 4)
        self._check_num("current_limit_uA", current_limit_uA, 50_000, verbose=verbose)

        v_dynamic_uV = 1000 * (self.data["voltage_max_mV"] - self.data["voltage_min_mV"])
        self.data["voltage_step_uV"] = v_dynamic_uV // self.data["window_size"]
        self._check_num("voltage_step_uV", 1, 1_000_000, verbose=verbose)

        self._check_num("setpoint_n", 0, 1, verbose=verbose)

        self._check_num("dynamic_bit", 1, M_DAC, verbose=verbose)
        self.data["dac_steps_bit"] = M_DAC - self.data["dynamic_bit"] + 1

        self._check_num("wait_cycles", 0, 100, verbose=verbose)

        # factor in timing-constraints
        window_samples = self.data["window_size"] * (1 + self.data["wait_cycles"])

        if "mppt_po" in self._inheritance:
            time_min_ms = (1 + self.data["wait_cycles"]) * 1000 / self.samplerate_sps
        else:
            time_min_ms = (1 + self.data["dynamic_bit"]) * (1 + self.data["wait_cycles"]) * 1000 / self.samplerate_sps

        if self.for_emulation:
            window_ms = window_samples * 1000 / self.samplerate_sps
            time_min_ms = max(time_min_ms, window_ms)

        self._check_num("interval_ms", 0.01, 1_000_000, verbose=verbose)  # creates param if missing
        self._check_num("duration_ms", 0.01, 1_000_000, verbose=verbose)  # creates param if missing
        ratio_old = self.data["duration_ms"] / self.data["interval_ms"]
        self._check_num("interval_ms", time_min_ms, 1_000_000, verbose=verbose)
        self._check_num("duration_ms", time_min_ms, self.data["interval_ms"], verbose=verbose)
        ratio_new = self.data["duration_ms"] / self.data["interval_ms"]
        if (ratio_new/ratio_old - 1) > 0.1:
            logger.debug(f"[{self.name}] Ratio between interval & duration has changed more than 10% due to constraints, from {ratio_old} to {ratio_new}")

        # for proper emulation
        if "window_samples" not in self.data:
            self.data["window_samples"] = window_samples
        if self.for_emulation and (window_samples > self.data["window_samples"]):
            self.data["window_samples"] = window_samples

    def _check_num(self, setting_key: str, min_value: float = 0, max_value: float = 2**32-1, verbose: bool = True) -> NoReturn:
        try:
            set_value = self.data[setting_key]
        except KeyError:
            set_value = self._config_base[setting_key]
            if verbose:
                logger.debug(f"[{self.name}] '{setting_key}' not provided, set to inherited value = {set_value}")
        if (min_value is not None) and (set_value < min_value):
            if verbose:
                logger.debug(f"[{self.name}] {setting_key} = {set_value}, but must be >= {min_value}")
            set_value = min_value
        if (max_value is not None) and (set_value > max_value):
            if verbose:
                logger.debug(f"[{self.name}] {setting_key} = {set_value}, but must be <= {max_value}")
            set_value = max_value
        if not isinstance(set_value, (int, float)) or (set_value < 0):
            raise NotImplementedError(
                f"[{self.name}] '{setting_key}' must a single positive number, but is '{set_value}'")
        self.data[setting_key] = set_value

    def export_for_sysfs(self) -> list:
        """ prepares virtconverter settings for PRU core (a lot of unit-conversions)

        This Fn add values in correct order and convert to requested unit

        Returns:
            int-list (2nd level for LUTs) that can be feed into sysFS
        """
        if self.for_emulation and self.data["algorithm_num"] <= algorithms["ivcurve"]:
            raise ValueError(f"Select valid harvest-algorithm for emulation, current usage = {self._inheritance}")
        elif self.data["algorithm_num"] < algorithms["ivcurve"]:
            raise ValueError(f"Select valid harvest-algorithm for harvesting, current usage = {self._inheritance}")

        return [
            int(self.data["algorithm_num"]),
            int(self.data["window_samples"] if self.for_emulation else self.data["window_size"]),
            int(self.data["voltage_mV"] * 1e3),  # uV
            int(self.data["voltage_min_mV"] * 1e3),  # uV
            int(self.data["voltage_max_mV"] * 1e3),  # uV
            int(self.data["voltage_step_uV"]),  # uV
            int(self.data["current_limit_uA"] * 1e3),  # nA
            int(max(0, min(255, self.data["setpoint_n"] * 256))),  # n8 -> 0..1 is mapped to 0..255
            int(self.data["interval_ms"] * self.samplerate_sps // 10 ** 3),  # n, samples
            int(self.data["duration_ms"] * self.samplerate_sps // 10 ** 3),  # n, samples
            int(self.data["dac_steps_bit"]),  # bit
            int(self.data["wait_cycles"]),  # n, samples
        ]
