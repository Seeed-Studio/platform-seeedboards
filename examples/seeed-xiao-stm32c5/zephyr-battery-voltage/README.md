# XIAO STM32C5 Battery Voltage ADC Test

This sample reads the on-board battery voltage sense circuit and prints the
measured voltage once per second.

Hardware mapping from the schematic:

- Battery sense ADC: `BAT_Reading/PA4`, `ADC1_IN4`
- Battery sense enable: `BAT_EN/PE2`, active high
- Voltage conversion: `battery voltage = ADC sampling voltage * 2.0`

Run:

```sh
pio run -t upload
pio device monitor -b 115200
```
