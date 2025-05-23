"""
shepherd.target_io
~~~~~
Lib to talk to the targets. there are 7x GPIO, 1x UART and 2x SWD (or 1x JTAG)
IO has semi-static direction, low-power, and is good for several MBit

GPIO 0            - dir1-pin / rxtx
GPIO 1            - dir1-pin / rxtx
GPIO 2            - dir1-pin / rxtx
GPIO 3            - dir1-pin / rxtx
GPIO 4            - always RX
GPIO 5            - always RX
GPIO 6            - always RX
GPIO 7 - uart rx  - always RX
GPIO 8 - uart tx  - dir2-pin / rxtx
BAT OK            - always TX

Prog1 CLK - jtag TCK   - always TX
Prog1 IO  - jtag TDI   - pDir1-pin / rxtx
Prog2 CLK - jtag TDO   - always TX
Prog2 IO  - jtag TMS   - pDir2-pin / rxtx

Direction Pins:

gpio0to3 = 78  # P8_37, GPIO2[14]
uart_tx = 79   # P8_38, GPIO2[15]
prog1_io = 10   # P8_31, GPIO0[10]
prog2_io = 11   # P8_32, GPIO0[11]

"""

from collections.abc import Mapping
from contextlib import suppress

from .logger import log

# allow importing shepherd on x86 - for testing
with suppress(ModuleNotFoundError):
    from periphery import GPIO


target_pins: list[dict] = [  # pin-order from target-connector
    {"name": "gpio0", "pin": 26, "dir": 78},
    {"name": "gpio1", "pin": 27, "dir": 78},
    {"name": "gpio2", "pin": 46, "dir": 78},
    {"name": "gpio3", "pin": 47, "dir": 78},
    {"name": "gpio4", "pin": 61, "dir": "I"},
    {"name": "gpio5", "pin": 80, "dir": "I"},
    {"name": "gpio6", "pin": 81, "dir": "I"},
    {"name": "uart_rx", "pin": 14, "dir": "I"},
    {"name": "uart_tx", "pin": 15, "dir": 79},  # TODO: why not BatOK here?
    {"name": "prog1_clk", "pin": 5, "dir": "O"},  # P9_17
    {"name": "prog1_io", "pin": 4, "dir": 10},  # P9_18, dir P8_31
    {"name": "prog2_clk", "pin": 8, "dir": "O"},  # P8_35
    {"name": "prog2_io", "pin": 9, "dir": 11},  # P8_33, dir P8_32, noqa: CM001
]

target_port_to_cape_v24_mapping: Mapping[int, int] = {
    0: 8,  # UART Target RX
    1: 7,  # UART Target TX
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    6: 6,
    7: 0,
    8: 1,
    17: 9,  # BatOK aka PowerGoodH
}

target_port_to_cape_v25_mapping: Mapping[int, int] = {
    0: 0,  # UART Target RX
    1: 1,  # UART Target TX
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    6: 6,
    7: 7,
    8: 8,
    9: 9,
    10: 10,
    11: 11,
    16: 12,  # powerGood Low
    17: 13,  # powerGood High
}


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
