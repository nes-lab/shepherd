"""
shepherd.target_io
~~~~~
Lib to talk to the targets. See the dedicated sub

"""

from contextlib import suppress

from .commons import CAPE_HW_VER
from .logger import log

# allow importing shepherd on x86 - for testing
with suppress(ModuleNotFoundError):
    from periphery import GPIO

if CAPE_HW_VER == 25:
    from .target_io_v25 import GPIO_LOG_BIT_POSITIONS
    from .target_io_v25 import target_pins
    from .target_io_v25 import target_port_to_cape_mapping
else:
    from .target_io_v24 import GPIO_LOG_BIT_POSITIONS
    from .target_io_v24 import target_pins
    from .target_io_v24 import target_port_to_cape_mapping


class TargetIO:
    def __init__(self) -> None:
        """Initializes relevant variables.

        Args:

        """
        dir_pins = {pin["dir"] for pin in target_pins if isinstance(pin["dir"], int)}
        self.dirs: dict[int, GPIO] = {}
        for pin in dir_pins:
            self.dirs[pin] = GPIO(pin, "out")
            self.dirs[pin].write(value=True)  # True == Output to target

        self.gpios: dict[str, GPIO] = {}
        for pin_info in target_pins:
            if pin_info["dir"] == "I":
                self.gpios[pin_info["name"]] = GPIO(pin_info["pin"], "in")
            else:
                self.gpios[pin_info["name"]] = GPIO(pin_info["pin"], "out")
                self.gpios[pin_info["name"]].write(value=False)  # init LOW

        self.pin_names: list[str] = [pin["name"] for pin in target_pins]
        self.pin_count: int = len(target_pins)

    def one_high(self, num: int) -> None:
        """Sets exactly one, the wanted pin_num, HIGH, the others to LOW

        Args:
            num: number of pin, in reference to list target_pins
        """
        for index in range(self.pin_count):
            self.set_pin(index, state=index == num)

    def get_pin_state(self, num: int) -> bool:
        """
        Args:
            num: number of pin, in reference to list target_pins

        Returns: pin state
        """
        pin_name = target_pins[num]["name"]
        return self.gpios[pin_name].read()

    def set_pin(self, num: int, *, state: bool) -> bool:
        """
        Args:
            num: number of pin, in reference to list target_pins
            state:

        Returns: True if wanted change is set (does not mean that it was actually changed here)
        """
        if self.get_pin_direction(num):
            return False
        pin_name = target_pins[num]["name"]
        if self.gpios[pin_name].direction == "in":
            log.warning("Error: pin %s was input, shouldn't be", pin_name)
        self.gpios[pin_name].write(value=state)
        return True

    def get_pin_direction(self, num: int) -> bool:
        """
        Args:
            num: number of pin, in reference to list target_pins

        Returns: False / 0 means Output, True / 1 means Input
        """
        dir_param = target_pins[num]["dir"]
        if isinstance(dir_param, str):
            return dir_param == "I"
        if isinstance(dir_param, int):
            dir_pin = self.dirs[dir_param]
            return not dir_pin.read()
        raise RuntimeError(
            "Something went wrong - could not determine pin-direction",
        )

    def set_pin_direction(self, num: int, *, pdir: bool) -> bool:
        """
        Args:
            num: number of pin, in reference to list target_pins
            pdir: False / 0 means Output, True / 1 means Input

        Returns: True if wanted change is set (does not mean that it was actually changed here)

        """
        dir_param = target_pins[num]["dir"]
        if isinstance(dir_param, str):
            # not changeable
            pin_state = dir_param == "I"
            return pin_state == pdir
        if isinstance(dir_param, int):
            pins_affected = [pin["name"] for pin in target_pins if pin["dir"] == dir_param]

            # changing pin-dir has to be done in 2 stages to be safe
            if pdir:  # GPIO -> input
                for pin in pins_affected:
                    self.gpios[pin].direction = "in"
            # dir-pin high == output (reversed to dir)
            self.dirs[dir_param].write(value=not pdir)
            if not pdir:  # GPIO -> input
                for pin in pins_affected:
                    self.gpios[pin].direction = "out"

            return True
        return False


__all__ = [
    "GPIO_LOG_BIT_POSITIONS",
    "TargetIO",
    "target_pins",
    "target_port_to_cape_mapping",
]
