# SYNC_PROCESS between kernel-module & PRU

## Main Goal

- synchronize system time with pru
- adapting period length of loop (like PLL)

## Mechanism High level

- Kernel sends pseudo-interrupt to PRU for taking a timestamp
  - kernel does this to a specific time
  - while pru should be idle, but period is almost over, TODO
- PRU sends current period-counter1 and switches to "reply pending"
- Kernel TODO
- PRU waits for response message (every cmp1-reset)
  - hard set next buffer-timestamp

## Kernel



## PRU1

PRU1
receive_sync_reply()
send_sync_request()
