from pathlib import Path

import ryaml
from pydantic import BaseModel
from shepherd_core.data_models.base.timezone import local_now
from shepherd_core.data_models.base.wrapper import Wrapper
from typing_extensions import Self


class WatchdogConfig(BaseModel):
    __slots__ = ()

    interval: int = 600
    """ ⤷ how often to send the ACK. Somewhere between 60 s to 30 minutes"""

    pin_ack: int = 68
    """ ⤷ pin that is resetting the hardware watchdog

    Cape v2 uses P8_10 / GPIO 68
    """

    network_needed: bool = False
    """ ⤷ watchdog should check network connection"""

    network_hosts: list[str] = [
        "8.8.4.4",  # google
        "8.8.8.8",  # google
        "1.1.1.1",  # cloudflare
        "4.2.2.1",  # L3 nameserver
        "4.2.2.2",  # L3 nameserver
    ]
    """ ⤷ default entries not only tests network access, but internet access.

    A reboot is issued as soon as all of these fail to be pinged.
    """

    @classmethod
    def file_path(cls) -> Path:
        return Path("/etc/shepherd/watchdog.yaml")

    def to_file(self) -> None:
        """Store data to YAML in a wrapper."""
        model_wrap = Wrapper(
            datatype=type(self).__name__,
            created=local_now(),
            parameters=self.model_dump(exclude_unset=False, mode="json"),
        ).model_dump(exclude_unset=True, exclude_defaults=False, mode="json")
        config_path = self.file_path()
        if not config_path.parent.exists():
            config_path.parent.mkdir(parents=True)
        with config_path.open("w", encoding="utf-8") as cfg_file:
            ryaml.dump(cfg_file, model_wrap)

    @classmethod
    def from_file(cls) -> Self | None:
        """Load from YAML."""
        config_path = cls.file_path()
        if not config_path.exists():
            return None
        with config_path.open(encoding="utf-8") as cfg_file:
            cfg_dict = ryaml.load(cfg_file)
        cfg_wrap = Wrapper(**cfg_dict)
        if cfg_wrap.datatype not in {cls.__name__, "Config"}:
            raise ValueError("Data in file does not match the requirement")
        return cls(**cfg_wrap.parameters)

    @classmethod
    def backup(cls) -> bool:
        path_config = cls.file_path()
        if path_config.exists():
            path_config.rename(path_config.with_suffix(f".backup_{local_now().isoformat()}"))
            return True
        return False
