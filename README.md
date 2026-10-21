# platform-seeed

A multi-chip PlatformIO platform: one `platform =` address, every chip
family plugged in as data + classes, upstream platforms reused by
reference instead of copy.

Switch boards, not platforms:

```ini
[env:xiao]
platform = https://github.com/<org>/platform-seeed.git
board = <board-id>
framework = <arduino | espidf | zephyr>
```

## What this is

- **For users**: build for any supported board with a single platform
  entry; board manifests carry everything PlatformIO needs.
- **For contributors**: chip families are pluggable modules — a new
  family lands as files, without touching the routing core. Upstream
  platforms are reused via version pins, imports, or build-script
  delegation; framework-package gaps are covered by per-board fixes
  that expire as upstream catches up.
- **For agents**: the repository is governed by
  [AGENTS.md](AGENTS.md) (principles, ownership, commit rules,
  validation loop) — read it first.

## Status

In development — all board families are buildable and CI-gated (23 boards):

| Family | Boards | Framework |
| --- | --- | --- |
| SAMD | XIAO SAMD21 | Arduino |
| ESP32 | XIAO ESP32-C3 / C5 / C6 / S3-Plus / S3-Sense | Arduino |
| Zephyr | XIAO nRF54L15 / nRF54LM20A / nRF54LM20B / STM32C5 | Zephyr |
| RP2040/RP2350 | XIAO RP2040 / RP2350 | Arduino (earlephilhower) |
| Renesas RA | XIAO RA4M1 | Arduino |
| Silicon Labs | XIAO MG24 / MG24 Sense | Arduino |
| nRF52 | XIAO nRF52840 line (Adafruit + mbed cores, 8 variants) | Arduino |

Every demo of every board builds green in CI before a family merges
([merge gate](docs/decisions/0005-ci-merge-gate.md)); the current
matrix is 46 environments (38 Arduino + 8 Zephyr). Until the first
release, use the production predecessor:
[Seeed-Studio/platform-seeedboards](https://github.com/Seeed-Studio/platform-seeedboards).

## Documentation

- [Architecture](docs/architecture.md) — the implementation handbook
- [Decision records](docs/decisions/) — binding ADRs
- [Roadmap](docs/roadmap.md) — implementation order
- [Contributing](docs/contributing.md) — change workflow and CI gates

## License

Apache-2.0 — see [LICENSE](LICENSE).
