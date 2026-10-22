# Contributing

Thanks for improving platform-seeed. The repository has strict
layering; most changes land in exactly one layer.

## Before you start

- Read [AGENTS.md](../AGENTS.md) — the five principles, ownership
  table, commit rules, and validation loop are binding. `CLAUDE.md`
  symlinks to it; agents read the same rules.
- Read the [architecture](architecture.md) section covering your change
  and the governing ADRs under [decisions/](decisions/).

## The CI gate

A family PR merges only when its CI matrix is green. `verify_examples.py`
requires at least one demo env for every board/framework pair, and the
per-framework workflows build every env. Arduino/Zephyr smoke projects carry
blink + uart; ESP-IDF carries blink. Canonical/per-protocol/per-fix demos
remain release criteria (ADR-0005 amendment), not something the current
matrix silently drops. Any `platform.json` change runs the full cross-family
matrix.

## Development loop

1. Offline gates (seconds):
   ```bash
   pytest tests/ -q                      # console script, never python -m pytest
   python scripts/ci/verify_boards.py
   python scripts/ci/verify_core.py
   python scripts/ci/verify_zephyr_routing.py
   python scripts/ci/verify_platform.py
   python scripts/ci/verify_examples.py
   python scripts/ci/verify_workflows.py
   ```
2. For build-behavior changes: build the affected boards through the
   local-checkout override, `pio run -t clean` first, with a FRESH
   platform cache (delete the cached platform dir — path installs
   dedupe by name and reuse stale copies). Zephyr fixes run in a per-build
   framework view (ADR-0006); remove `$PROJECT_CORE_DIR/zephyr-views` if a
   view is suspected stale.
3. Shared-package discipline: same-named packages from different
   upstreams collide (one version slot per name platform-wide,
   ADR-0002); interrupted downloads leave damaged packages. Delete and
   re-download on suspicion.
4. Hardware upload/debug is never claimed without device evidence;
   write "not performed" otherwise.

## Commits and PRs

Conventional commits (`feat(samd): ...`, `fix(zephyr): ...`); one
reviewable unit per commit; body explains why before what; validation
evidence (what ran locally, what is left to CI) in the message; no
co-author trailers; English only. PRs use the Why / What Changed /
Validation template.
