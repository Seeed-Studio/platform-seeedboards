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

A family PR merges only when the family's **entire demo matrix** is
green in CI: every demo of every board (ADR-0005). Each board carries
at least blink + uart + one framework-canonical demo; each family
exercises every upload protocol, debug injection, and fix it ships.
Any `platform.json` change runs the full cross-family matrix.

## Development loop

1. Offline gates (seconds):
   ```bash
   pytest tests/ -q                      # console script, never python -m pytest
   python scripts/ci/verify_boards.py
   python scripts/ci/verify_families.py
   ```
2. For build-behavior changes: build the affected boards through the
   local-checkout override, `pio run -t clean` first, with a FRESH
   platform cache (delete the cached platform dir — path installs
   dedupe by name and reuse stale copies).
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
