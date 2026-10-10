"""Single source of truth for ESP32 chip-family membership lists.

Adding a chip to this platform means joining the tuples here instead of
editing per-site hardcoded lists across the package config and the ESP
builders; every consumer imports from this module and keeps no local
copy. Semantics:

- ``XTENSA_MCUS``: main CPU is Xtensa (toolchain-xtensa-esp-elf).
- ``RISCV_MCUS``: main CPU is RISC-V (toolchain-riscv32-esp). These
  chips have no classic ULP coprocessor (LP-core instead), so the
  esp32ulp toolchain is dropped for them.
- ``RISCV_TOOLCHAIN_MCUS``: every chip that must install the
  toolchain-riscv32-esp package — the RISC-V chips plus ESP32-S2/S3,
  whose ULP coprocessor is RISC-V based.
- ``BOOTLOADER_OFFSET_0X2000_MCUS``: chips whose ROM places the
  bootloader image at 0x2000 (same layout class). Everything else uses
  0x1000 (esp32, esp32s2) or the 0x0 default.

Deliberately NOT consolidated here (different semantics, small and
chip-specific): the esp-builtin USB-JTAG debug tool list, the
ULP-RISC-V exclusion tuple in espidf.py, and the Arduino upload
pre-action.
"""

XTENSA_MCUS = ("esp32", "esp32s2", "esp32s3")

RISCV_MCUS = (
    "esp32c2",
    "esp32c3",
    "esp32c5",
    "esp32c6",
    "esp32h2",
    "esp32p4",
    "esp32s31",
)

RISCV_TOOLCHAIN_MCUS = ("esp32s2", "esp32s3") + RISCV_MCUS

BOOTLOADER_OFFSET_0X2000_MCUS = ("esp32c5", "esp32p4", "esp32s31")
