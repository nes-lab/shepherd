# firmware_nrf52_powered.hex

functionality

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