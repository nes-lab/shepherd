from typing import NoReturn, Union
from pathlib import Path
import yaml
import logging
from calibration_default import M_DAC

logger = logging.getLogger(__name__)

algorithms = {"neutral": 2**0,
              "ivcurve": 2**4,
              "cv": 2**8,
              "ci": 2**9,
              "mppt_voc": 2**12,
              "mppt_po": 2**13,
              }


class VirtualConverterData(object):
    """

    """
    _config: dict = {}
    _name: str = "vConverter"

    def __init__(self, setting: Union[dict, str, Path], samplerate_sps: int = 100_000):
        """

        :param setting:
        """
        self.samplerate_sps = samplerate_sps
        def_file = "virtual_converter_defs.yml"
        def_path = Path(__file__).parent.resolve()/def_file
        with open(def_path, "r") as def_data:
            self._config_defs = yaml.safe_load(def_data)["virtconverters"]
            self._config_base = self._config_defs["neutral"]
        self._inheritance = []

        if isinstance(setting, str) and Path(setting).exists():
            setting = Path(setting)

        if isinstance(setting, Path) and setting.exists() and \
                setting.is_file() and setting.suffix in ["yaml", "yml"]:
            with open(setting, "r") as config_data:
                setting = yaml.safe_load(config_data)["virtconverter"]
        if isinstance(setting, str):
            if setting in self._config_defs:
                self._inheritance.append(setting)
                setting = self._config_defs[setting]
            else:
                raise NotImplementedError(f"[{self._name}] was set to '{setting}', but definition missing in '{def_file}'")

        if setting is None:
            self._config = {}
        elif isinstance(setting, VirtualConverterData):
            self._config = setting._config
        elif isinstance(setting, dict):
            self._config = setting
        else:
            raise NotImplementedError(
                f"[{self._name}] {type(setting)}'{setting}' could not be handled. In case of file-path -> does it exist?")
        self.check_and_complete()

    def check_and_complete(self, verbose: bool = True) -> NoReturn:

        if "converter_base" in self._config:
            base_name = self._config["converter_base"]
        else:
            base_name = "neutral"

        if base_name in self._inheritance:
            raise ValueError(f"[{self._name}] loop detected in 'converter_base'-inheritance-system @ last entry of {self._inheritance}")
        else:
            self._inheritance.append(base_name)

        if base_name == "neutral":
            # root of recursive completion
            self._config_base = self._config_defs[base_name]
            logger.debug(f"[{self._name}] Config-Set was initialized with '{base_name}'-base")
            verbose = False
        elif base_name in self._config_defs:
            config_stash = self._config
            self.vss = self._config_defs[base_name]
            self.check_and_complete(verbose=False)
            logger.debug(f"[{self._name}] Config-Set was completed with '{base_name}'-base")
            self._config_base = self._config
            self._config = config_stash
        else:
            raise NotImplementedError(f"[{self._name}] converter-base '{base_name}' is unknown to system")

        if not "algorithm_num" in self._config:
            self._config["algorithm_num"] = 0
        if base_name in algorithms:
            self._config["algorithm_num"] += algorithms[base_name]
        self._check_num("algorithm_num", verbose=verbose)

        self._check_num("window_size", 16, 512, verbose=verbose)

        self._check_num("voltage_mV", 0, 5000, verbose=verbose)
        self._check_num("voltage_min_mV", 0, 5000, verbose=verbose)
        self._check_num("voltage_max_mV", self._config["voltage_min_mV"], 5000, verbose=verbose)
        self._check_num("current_uA", 0, 50_000, verbose=verbose)

        self._check_num("setpoint_n", 0, 1, verbose=verbose)

        self._check_num("dynamic_bit", 1, M_DAC, verbose=verbose)
        self._config["dac_steps_bit"] = M_DAC - self._config["dynamic_bit"] + 1

        self._check_num("wait_cycles", 0, 100, verbose=verbose)

        time_min_ms = (1 + self._config["dynamic_bit"]) * (1 + self._config["wait_cycles"]) * 1000 / self.samplerate_sps

        self._check_num("interval_ms", time_min_ms, 1_000_000, verbose=verbose)
        self._check_num("duration_ms", time_min_ms, self._config["interval_ms"], verbose=verbose)

    def _check_num(self, setting_key: str, min_value: float = 0, max_value: float = 2**32-1, verbose: bool = True) -> NoReturn:
        try:
            set_value = self._config[setting_key]
        except KeyError:
            set_value = self._config_base[setting_key]
            if verbose:
                logger.debug(f"[{self._name}] '{setting_key}' not provided, will be set to inherited value = {set_value}")
        if (min_value is not None) and (set_value < min_value):
            set_value = min_value
            if verbose:
                logger.debug(f"[{self._name}] {setting_key} = {set_value} must be >= {min_value}")
        if (max_value is not None) and (set_value > max_value):
            set_value = max_value
            if verbose:
                logger.debug(f"[{self._name}] {setting_key} = {set_value} must be <= {max_value}")
        if not isinstance(set_value, (int, float)) or (set_value < 0):
            raise NotImplementedError(
                f"[{self._name}] '{setting_key}' must a single positive number, but is '{set_value}'")
        self._config[setting_key] = set_value

    def export_for_sysfs(self) -> list:
        """ prepares virtconverter settings for PRU core (a lot of unit-conversions)

        This Fn add values in correct order and convert to requested unit

        Returns:
            int-list (2nd level for LUTs) that can be feed into sysFS
        """
        return [
            int(self._config["algorithm_num"]),
            int(self._config["window_size"]),
            int(self._config["voltage_mV"] * 1e3),  # uV
            int(self._config["voltage_min_mV"] * 1e3),  # uV
            int(self._config["voltage_max_mV"] * 1e3),  # uV
            int(self._config["current_uA"] * 1e3),  # nA
            int(max(0, min(255, self._config["setpoint_n"] * 256))),  # n8 -> 0..1 is mapped to 0..255
            int(self._config["interval_ms"] * self.samplerate_sps // 10 ** 3),  # n, samples
            int(self._config["duration_ms"] * self.samplerate_sps // 10 ** 3),  # n, samples
            int(self._config["dac_steps_bit"]),  # bit
            int(self._config["wait_cycles"]),  # n, samples
        ]
