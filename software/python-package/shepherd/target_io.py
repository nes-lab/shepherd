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

SWD1 CLK - jtag TCK   - always TX
SWD1 IO  - jtag TDI   - pDir1-pin / rxtx
SWD2 CLK - jtag TDO   - always TX
SWD2 IO  - jtag TMS   - pDir2-pin / rxtx

:copyright: (c) 2021 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
from periphery import GPIO

target_pin_nums = {  # pin-order from target-connector
    "gpio0": 26,
    "gpio1": 27,
    "gpio2": 46,
    "gpio3": 47,
    "gpio4": 61,
    "gpio5": 80,
    "gpio6": 81,  # v2.3 -> always RX
    "uart_rx": 14,  # v2.3 -> always RX
    "uart_tx": 15,
    "swd1_clk": 5,
    "swd1_io": 4,
    "swd2_clk": 8,
    "swd2_io": 9,
}

target_pin_dirs = {  # TODO:
    "gpio0to3": 78,
    "uart_tx": 79,
    "swd1_io": 10,
    "swd2_io": 11,
}


class TargetIO:

    gpios = {}
    pin_names = []
    pin_count = 0
    dirs = {}

    def __init__(self):
        """Initializes relevant variables.

        Args:

        """
        for name, pin in target_pin_dirs.items():
            self.dirs[name] = GPIO(pin, "out")
            self.dirs[name].write(True)  # TODO: still unused, init pins as output

        for name, pin in target_pin_nums.items():
            self.gpios[name] = GPIO(pin, "out")

        self.pin_names = list(target_pin_nums.keys())
        self.pin_count = len(self.pin_names)

    def one_high(self, num: int):
        for index in range(self.pin_count):
            self.gpios[self.pin_names[index]].write(index == num)

    # TODO: offer more helpers like get_pin_name, get_pin_count, set_pin_dir, ...
