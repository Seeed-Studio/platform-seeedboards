Copy the following files into this directory:

1. USB_DFU.hex        — Merged system HEX (mcuboot + loader + app) from NCS build
   Source: D:\workspace\aaamemory\xiao\20b\firmware\release_xiao_nrf54lm20b_testplan\usb_dfu\USB_DFU.hex

2. keyfile.json       — KMU public key (root-ed25519)
   Source: D:\workspace\aaamemory\xiao\20b\firmware\release_xiao_nrf54lm20b_testplan\usb_dfu\keyfile.json
   (or: D:\workspace\xiao_nrf54lm20b_usb_dfu_test\keyfile.json)

3. app.signed.bin    — PIO app (from: pio run -e seeed-xiao-nrf54lm20b)
   Source: .pio/build/seeed-xiao-nrf54lm20b/zephyr/zephyr.signed.bin
   (or omit — pass -AppBin <path> at runtime)
