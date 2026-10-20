# platform-unified — agent and contributor rules

This repository implements the multi-chip unified PlatformIO platform:
one `platform =` address, families plugged in as data + classes, upstream
reused wherever it can be. **Documentation precedes code**: no behavior
lands before its design exists under `docs/`, and no design is edited
without re-reading the ADRs it touches.

## Five principles (binding)

1. **Data/logic separation** — board facts live in `boards/*.json`;
   behavior lives in `families/<family>.py`. Never paper over a missing
   manifest value with builder logic.
2. **Open-closed families** — adding a family adds files
   (`families/<chip>.py` + one import line) and touches no core routing.
3. **Zero-string routing** — `platform.py` and `builder/main.py` contain
   no chip/board-name literals; they consult the `ChipFamily` registry
   keyed by the manifest's `build.chip_family`.
4. **Single pin per package name** — PlatformIO gives every package name
   exactly one version slot platform-wide. When two upstreams pin the
   same tool differently, unify consciously and validate BOTH families'
   builds (ADR-0002). Stub/URL packages are allowed only if every family
   that requires the package can expand it.
5. **Upstream by reference, gaps by fixes** — reuse upstream via version
   pins, imports, SConscript delegation, or forks; when a *framework
   package content* gap must be patched, use the board-directory fixes
   mechanism with baseline drift detection (ADR-0003). Never silently
   modify a package cache.

## Ownership

| Concern | Owning location |
| --- | --- |
| Package declarations + version pins | `platform.json` |
| Lifecycle entry / registry lookup | `platform.py` |
| Family behavior (packages, flags, upload, debug) | `families/<family>.py` |
| Build entry, hook registration, delegation | `builder/main.py`, `builder/frameworks/` |
| Board facts incl. `build.chip_family` | `boards/<board-id>.json` |
| Framework-package fixes | `zephyr/boards/arm/<board>/fixes/` (or per-framework equivalent) |
| Regression contracts | `examples/`, `scripts/ci/`, `.github/workflows/` |

Keep a change in its owning layer. Preserve the public contract (board
ids, framework names, package versions, upload/debug behavior, firmware
formats) unless a decision record explicitly alters it.

## Validation loop (inline, machine-enforced where possible)

Before every commit, run everything locally runnable; state anything not
runnable with the reason in the commit message:

1. Offline gates (seconds):
   ```bash
   pytest tests/ -q                      # console script, never python -m pytest
   python scripts/ci/verify_boards.py    # once implemented
   python scripts/ci/smoke_pio_boards.py
   ```
2. Build behavior: build the affected boards through the local-checkout
   override, `pio run -t clean` first, with a FRESH platform cache
   (delete the cached platform dir — path installs dedupe by name and
   reuse stale copies).
3. Shared-package discipline: same-named packages from different
   upstreams collide; interrupted downloads leave damaged packages that
   fail builds in confusing ways. Delete and re-download on suspicion.
4. Hardware upload/debug is never claimed without device evidence.

## Decision records

Cross-layer decisions are ADRs under `docs/decisions/NNNN-topic.md`
(Context / Decision / Consequences). Read the relevant ADRs before
changing routing, package policy, fixes strategy, or CI; add one when a
new decision of that class is made. Supersede explicitly, never silently.
