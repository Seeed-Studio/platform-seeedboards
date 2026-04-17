# UART21 Demo for XIAO nRF54LM20A

This demo shows how to use UART21 for serial communication on the XIAO nRF54LM20A board.

## Pin Configuration

| Function | Pin  | GPIO   |
|----------|------|--------|
| TX       | P1.8 | GPIO1.8|
| RX       | P1.9 | GPIO1.9|

## Features

- Baud rate: 1000000
- 8 data bits, no parity, 1 stop bit (8N1)
- Uses Zephyr's asynchronous UART API
- Echoes received characters
- Sends periodic heartbeat messages

## Building and Flashing

### Using PlatformIO

```bash
pio run -t upload
pio device monitor
```

### Using West (Zephyr)

```bash
cd zephyr
west build -b xiao_nrf54lm20a/nrf54lm20a/cpuapp
west flash
```

## Usage

1. Connect a USB-to-serial adapter to the UART21 pins:
   - Adapter TX -> Board P1.9 (RX)
   - Adapter RX -> Board P1.8 (TX)
   - GND -> GND

2. Open a serial terminal at 1000000 baud

3. Type any text and press Enter to see it echoed back

4. The board will send heartbeat messages every 5 seconds

## Console Output

Logging output is available on UART20 (the default console):
- TX: P1.11
- RX: P1.10

Connect a second USB-to-serial adapter or use the built-in USB CDC-ACM if available.
