# platform-unified

Multi-chip unified PlatformIO platform: one `platform =` address, chip
families as pluggable data + classes, upstream reused by reference.

**Status: docs-first scaffold.** No code yet — by design. The founding
documents are the contract every later commit implements:

- [AGENTS.md](AGENTS.md) — five binding principles, ownership, inline
  validation loop
- [docs/architecture.md](docs/architecture.md) — the implementation
  handbook (amended design; all flows)
- [docs/decisions/](docs/decisions/) — ADRs:
  [0001 ChipFamily registry](docs/decisions/0001-chipfamily-registry.md),
  [0002 single pin per package](docs/decisions/0002-single-pin-per-package.md),
  [0003 fixes mechanism](docs/decisions/0003-fixes-mechanism.md),
  [0004 reuse ladder + validation tiers](docs/decisions/0004-reuse-ladder-and-validation-tiers.md)

## Implementation order

1. `families/base.py` — the registry (ADR-0001)
2. Offline gates + tests (ADR-0004 T0) — before any family
3. `platform.py` / `builder/main.py` zero-string core
4. First family (recommended: samd — smallest, upstream exists)
5. Second family with a package collision (esp) — proves ADR-0002
6. Zephyr family + fixes mechanism — proves ADR-0003

Apache-2.0.
