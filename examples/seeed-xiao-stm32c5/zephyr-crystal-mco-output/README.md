# XIAO STM32C5 Crystal MCO Output Test

This sample starts the external crystal oscillators and routes them to STM32C5 MCO pins:

| Clock | MCO | MCU pin | Board net | Expected output |
| --- | --- | --- | --- | --- |
| LSE | MCO1 | PH2 | PH2-BOOT0 | 32.768 kHz |
| HSE | MCO2 | PA9 | D6 / UART_TX | 48 MHz |

The board LED blinks while the application is running. A steady 1 Hz blink means both
oscillators became ready before MCO was configured. A fast blink means one of the
oscillators did not report ready.

PA9 is used by MCO2 in this test, so the UART console is disabled.
