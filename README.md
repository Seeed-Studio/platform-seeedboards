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

Early-stage. The design is settled
([architecture](docs/architecture.md)) and implementation is starting
([roadmap](docs/roadmap.md)); no boards are buildable yet. Until the
first release, use the production predecessor:
[Seeed-Studio/platform-seeedboards](https://github.com/Seeed-Studio/platform-seeedboards).

## Documentation

- [Architecture](docs/architecture.md) — the implementation handbook
- [Decision records](docs/decisions/) — binding ADRs
- [Roadmap](docs/roadmap.md) — implementation order
- [Contributing](docs/contributing.md) — change workflow and CI gates

## License

Apache-2.0 — see [LICENSE](LICENSE).
