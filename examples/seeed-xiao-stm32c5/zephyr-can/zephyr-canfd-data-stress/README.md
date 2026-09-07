# XIAO STM32C5 CAN FD Data-Phase Stress Sample

This sample measures CAN FD data-phase reliability and throughput between a
XIAO STM32C5 and another CAN FD node, such as a USB-to-CAN FD adapter. It can
transmit, receive, run bidirectionally, or use internal loopback. The default
standard identifier is `0x504`, with a maximum payload of 64 bytes.

## Hardware setup

```text
Adapter CANH ---- XIAO CANH
Adapter CANL ---- XIAO CANL
Adapter GND  ---- XIAO GND
```

- Use one 120-ohm termination resistor at each physical end of the bus.
- Use twisted-pair cable and maintain a linear topology.
- FDCAN2 uses the on-board transceiver (`RX=PB5`, `TX=PB13`); PB14 controls
  transceiver standby through the board devicetree.
- The adapter and XIAO must use identical nominal and data timing.

High data rates are sensitive to cable length, transceiver delay, termination,
sample point, and transmitter delay compensation. Establish communication at a
lower rate before testing the required limit.

## Build and flash

```powershell
cd examples\seeed-xiao-stm32c5\zephyr-can\zephyr-canfd-data-stress
pio run
```

Build artifacts are written under `.pio\build\seeed-xiao-stm32c5\`. Flash
`firmware.uf2` through the UF2 bootloader, then open the USB CDC ACM port at
115200 baud.

The terminal should display:

```text
XIAO STM32C5 CAN FD data phase stress
Use shell command: cfd start tx 500000 2000000 64 30 0 fd-brs
```

## Commands

```text
cfd start <tx|rx|bidi|loop> [nominal] [data] [bytes] [seconds] [fps] [can|fd|fd-brs] [pattern]
cfd stop
cfd status
cfd id [000..7ff]
cfd clock
cfd regs
```

Modes:

- `tx`: transmit generated traffic.
- `rx`: receive and validate traffic.
- `bidi`: transmit and receive concurrently.
- `loop`: use controller loopback for local validation.

Formats:

- `can`: Classic CAN, up to 8 payload bytes.
- `fd`: CAN FD without bit-rate switching.
- `fd-brs`: CAN FD with the configured data-phase rate.

Patterns are `fixed`, `fixed-8`, `fixed-64`, `alt-8-64`, and `mix-canfd`.
An `fps` value of `0` transmits without application-level rate limiting.

## Initial validation

Check the reported clock and registers before testing the physical bus:

```text
cfd clock
cfd regs
cfd start loop 500000 0 8 5 100 can
cfd start loop 500000 2000000 64 5 100 fd-brs
```

Then validate the external link incrementally:

```text
cfd start tx 500000 0 8 30 100 can
cfd start tx 500000 500000 64 30 100 fd
cfd start tx 500000 1000000 64 30 100 fd-brs
cfd start tx 500000 2000000 64 30 0 fd-brs
cfd start tx 500000 4000000 64 30 0 fd-brs
cfd start tx 500000 5000000 64 30 0 fd-brs
```

Only test 6 or 8 Mbit/s after the lower-rate tests pass and the controller,
transceiver, cable, and adapter support the selected timing.

For receive testing, start the XIAO first and then transmit matching CAN FD
frames from the adapter:

```text
cfd start rx 500000 2000000 64 30 0 fd-brs
```

For concurrent traffic:

```text
cfd start bidi 500000 2000000 64 60 0 fd-brs
```

## Host adapter operation

In the adapter software:

1. Select the connected device and the wired CAN channel.
2. Configure the same nominal bit rate, data bit rate, CAN FD mode, BRS state,
   and compatible sample points.
3. Start the channel before beginning a XIAO transmit test.
4. Confirm that identifier, FD/BRS flags, DLC, payload, and receive count match
   the requested test.
5. For XIAO receive tests, transmit standard-ID frames using the selected XIAO
   identifier and timing.

Adapter-specific channel names and controls vary by software version. Refer to
the adapter documentation for exact timing and channel configuration.

## Statistics and acceptance criteria

`cfd status` and the final summary report transmitted and received frames,
callback errors, sequence gaps, payload errors, throughput, controller state,
and protocol error counters. The detailed field definitions and recommended
acceptance criteria are in `C5-CAN_TEST_GUIDE.md`.

A valid link test should remain error-active, report no transmit failures,
sequence gaps, payload errors, or receive overruns, and should not accumulate
ACK, bit, CRC, form, or stuff errors.

## Troubleshooting

- No frames at the host: verify CANH/CANL/GND, termination, channel selection,
  FD/BRS settings, bit timing, and that the adapter channel is started.
- Repeated ACK errors: ensure another active node is present and configured to
  acknowledge the same frame format and timing.
- Lower rates pass but higher rates fail: shorten the cable, verify termination
  and transceiver capability, review the sample point, and confirm transmitter
  delay compensation.
- `rx` increases while `checked` does not: the incoming frames do not use the
  sample's expected identifier or payload pattern.
- `invalid nominal bitrate`: enter plain integer bit rates, for example
  `500000`, rather than abbreviations such as `500k`.
