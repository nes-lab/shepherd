# -*- coding: utf-8 -*-

"""
shepherd.target_io
~~~~~
Lib to talk to the targets. there are 5x GPIO, 1x UART and a SWD / xxx Port
All IO is auto-directional, low-power, and good for several MBit


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
    "uart_tx": 15,
    "uart_rx": 14,
    "swd_clk": 5,
    "swd_io": 4,
}


class TargetIO(object):

    gpios = {}
    pin_names = []
    pin_count = 0

    def __init__(self):
        """Initializes relevant variables.

        Args:

        """
        for name, pin in target_pin_nums.items():
            self.gpios[name] = GPIO(pin, "out")

        self.pin_names = list(target_pin_nums.keys())
        self.pin_count = len(self.pin_names)

    def one_high(self, num: int):
        for index in range(self.pin_count):
            self.gpios[self.pin_names[index]].write(index == num)
