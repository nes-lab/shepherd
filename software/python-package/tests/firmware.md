# Firmwares

## Usage

```Bash
	sudo shepherd-sheep -v program --mcu-port 1 --mcu-type nrf52  firmware_nrf52_testable.hex
	sudo shepherd-sheep -v program --mcu-port 2 --mcu-type msp430 firmware_msp430_testable.hex
	sudo shepherd-sheep target-power
	# alternatively run with "-p B" for the second target port
```


## firmware_nrf52_powered.hex

The app monitors up to eight GPIO pins for rising edges and upon detection prints the index of the pin where the edge was detected over UART. Simultaneously, it waits for incoming messages on the UART. When receiving an ASCII encoded number between 0 and the number of configured pins, the app sets the corresponding pin high for ~100us.

Edit the `pins` array and the UART pin definitions at the top of `src/main.c` to reflect your hardware.

### Functionality

- LEDs
	- blink / switch 10x at startup
	- 50 / 150 ms
	- P0_13, _14 (Target v2.1)
- UART
	- P0_06 TX, _08 RX (Target v2.1, SDK)
	- listens and answers
	- should answer when GPIOs are triggered
- GPIO
	- active: P0_20 - P0_25 (GPIO 0 to 5)
	- switch on for 100 us after receiving on UART ("(%u)\r\n")

[Source](https://github.com/nes-lab/shepherd-targets/tree/main/firmware/nrf52_testable)

## firmware_msp52_testable.hex

The firmware toggles all 3 LEDs 16 times for 100 ms and does the same for the 10 external GPIO (4 times).

### Functionality

- LEDs
    - blink / switch on 16x at startup
    - 100 ms on / 100 ms off
- GPIO
    - active: P0_20 - P0_25 (GPIO 0 to 5)
    - switch on for 100 us after receiving on UART ("(%u)\r\n")

[Source](https://github.com/nes-lab/shepherd-targets/tree/main/firmware/msp430_testable)
