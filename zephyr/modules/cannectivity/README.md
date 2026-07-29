# CANnectivity — slimmed vendoring (gs_usb USB<->CAN class)

This is a slimmed vendoring of the upstream CANnectivity project, kept only to
provide the `gs_usb` USB device class driver (new stack, `device_next`) used by
the XIAO STM32C5 CAN-USB bridge sample at
`examples/seeed-xiao-stm32c5/zephyr-can/zephyr-can-bridge-gsusb/`.

What's kept: the `device_next` gs_usb class driver + its public header, the DTS
binding, and the module/Kconfig/CMake plumbing.

What was dropped from upstream: the sample app, other boards' overlays, host
tests, docs, scripts, the udev rules, and the deprecated classic (`device`) USB
stack path.

Upstream: https://github.com/cannectivity/cannectivity
License: Apache-2.0 (see `LICENSE`).
