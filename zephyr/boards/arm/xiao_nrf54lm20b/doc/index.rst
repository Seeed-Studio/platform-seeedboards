.. _xiao_nrf54lm20b:

XIAO nRF54LM20B
###############

Overview
========

The XIAO nRF54LM20B is a compact development board from Seeed Technology based on the
Nordic nRF54LM20B SoC. The nRF54LM20B is identical to the nRF54LM20A silicon except for
the absence of the NPU (Neural Processing Unit).

Hardware
========

- Nordic nRF54LM20B SoC (ARM Cortex-M33 + RISC-V FLPR core)
- 512 KB SRAM
- 2 MB RRAM (code flash)
- 128 Mbit SPI NOR flash (PY25Q128HA)
- Bluetooth LE (SoftDevice Controller)
- IEEE 802.15.4
- NFC
- USB HS
- nPM1300 PMIC with battery charging
- LSM6DS3TR-C 6-axis IMU
- MSM261DGT006 PDM microphone
- RGB LED
- User button
- XIAO 28-pin header (D0-D27, with ADC, I2C, SPI, UART)

Supported Features
==================

- ADC
- Counter
- DMIC
- GPIO
- I2C
- I2S
- PWM
- SPI
- Watchdog
- Bluetooth LE
- IEEE 802.15.4
- USB

Connections and IOs
===================

LEDs
----

- Red LED   : P1.22 (GPIO1.22, active high)
- Blue LED  : P1.23 (GPIO1.23, active high)
- Green LED : P1.24 (GPIO1.24, active high)

Push Buttons
------------

- Button 0  : P0.09 (GPIO0.09, active low with pull-up)

Serial Port
-----------

- Console UART (UART20): TX=P1.11, RX=P1.10
- XIAO UART (UART21):   TX=P1.08, RX=P1.09

I2C
---

- XIAO I2C (I2C22): SDA=P1.03, SCL=P1.07
- IMU I2C (I2C30):  SDA=P0.08, SCL=P0.07

SPI
---

- XIAO SPI (SPI23): SCK=P1.04, MOSI=P1.06, MISO=P1.05
- Flash SPI (SPI00): SCK=P2.01, MOSI=P2.02, MISO=P2.04, CS=P2.05

Programming and Debugging
=========================

This board supports the following debug interfaces:

- OpenOCD via CMSIS-DAP (SWD)
- J-Link
- nrfutil

Flashing
--------

Using OpenOCD with CMSIS-DAP:

.. code-block:: console

   west flash --runner openocd

Using nrfutil:

.. code-block:: console

   west flash --runner nrfutil

Debugging
---------

.. code-block:: console

   west debug --runner openocd
