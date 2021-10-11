from typing import NoReturn, Union
from pathlib import Path
import yaml
import logging

logger = logging.getLogger(__name__)


class VirtualConverterData(object):
    """

    """
    vcs: dict = {}

    def __init__(self, setting: Union[dict, str, Path], samplerate_sps: int = 100_000):
        """

        :param setting:
        """
        self.samplerate_sps = samplerate_sps
        def_file = "virtual_converter_defs.yml"
        def_path = Path(__file__).parent.resolve()/def_file
        with open(def_path, "r") as def_data:
            self.vc_configs = yaml.safe_load(def_data)["virtconverters"]
            self.vc_base = self.vc_configs["neutral"]
        self.vc_inheritance = []

        if isinstance(setting, str) and Path(setting).exists():
            setting = Path(setting)
        if isinstance(setting, Path) and setting.exists():  # TODO: not perfect - better also check for ".yml", same above
            with open(setting, "r") as config_data:
                setting = yaml.safe_load(config_data)["virtconverter"]
        if isinstance(setting, str):
            if setting in self.vc_configs:
                self.vc_inheritance.append(setting)
                setting = self.vc_configs[setting]
            else:
                raise NotImplementedError(f"VirtualConverter was set to '{setting}', but definition missing in '{def_file}'")

        if setting is None:
            self.vcs = {}
        elif isinstance(setting, VirtualConverterData):
            self.vcs = setting.vcs
        elif isinstance(setting, dict):
            self.vcs = setting
        else:
            raise NotImplementedError(
                f"VirtualConverterData {type(setting)}'{setting}' could not be handled. In case of file-path -> does it exist?")

        # self.check_and_complete()

    def export_for_sysfs(self) -> list:
        """ prepares virtconverter settings for PRU core (a lot of unit-conversions)

        This Fn add values in correct order and convert to requested unit

        Returns:
            int-list (2nd level for LUTs) that can be feed into sysFS
        """
        return [
            int(self.vcs["algorithm"]),
            int(self.vcs["window_size"]),
            int(self.vcs["voltage_mV"] * 1e3),  # uV
            int(self.vcs["voltage_min_mV"] * 1e3),  # uV
            int(self.vcs["voltage_max_mV"] * 1e3),  # uV
            int(max(0, min(255, self.vcs["setpoint_n"] * 256))),  # n8 -> 0..1 is mapped to 0..255
            int(self.vcs["interval_ms"] * self.samplerate_sps // 10**3),  # n, samples
            int(self.vcs["duration_ms"] * self.samplerate_sps // 10**3),  # n, samples
        ]
