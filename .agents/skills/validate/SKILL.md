---
name: validate
description: Run this platform's validation tiers in order -- offline gates first, then per-framework demo matrices; the same commands CI runs and the ADR-0005 merge gate consumes.
---

# Validate the platform

Apply the repository rules in `AGENTS.md` first. Validation is tiered
(ADR-0004); never claim a change is done on a lower tier than its
 blast radius requires.

## T0 -- offline gates (seconds, no packages, no network)

```
pytest tests/ -q                      # run as the console script; python -m
                                      # would shadow the stdlib platform module
python3 scripts/ci/verify_boards.py   # manifest snapshot + schema + family registry
python3 scripts/ci/verify_core.py     # zero-string routing + platform.json
python3 scripts/ci/verify_zephyr_routing.py  # routing closure + fixes layout
python3 scripts/ci/verify_platform.py # family/package/debug runtime contract
python3 scripts/ci/verify_examples.py # every board/framework has a demo; URL pin
python3 scripts/ci/verify_workflows.py # YAML, permissions, v3 push branches
```

Any failure blocks everything below. Gate errors name the file and the
rule; fix the cause, never the gate.

## T1/T2 -- demo matrices (per framework)

Every demo of every board must build (ADR-0005). The wrapper rewrites
platform URLs to the local checkout and builds each env in its own
process:

```
python3 scripts/ci/build_examples.py --framework arduino --clean
python3 scripts/ci/build_examples.py --framework zephyr --clean
python3 scripts/ci/build_examples.py --framework espidf --clean
# one board/env while iterating:
python3 scripts/ci/build_examples.py --framework arduino --clean \
    --only-env seeed-xiao-samd
```

Current scale: 45 + 17 + 5 = 67 environments. `RESULT: ALL GREEN` (exit 0)
is the only pass state.

Rules of engagement:

- A stale `~/.platformio/platforms/seeed` (local-path platforms are
  installed once and never refreshed) produces `UnknownBoard` after you
  add boards or edit routing: `rm -rf ~/.platformio/platforms/seeed`
  and rerun.
- Zephyr fixes run in a per-build framework view under
  `$PROJECT_CORE_DIR/zephyr-views` (ADR-0006), not in the installed
  package. Inspect/prune it with
  `python3 scripts/ci/clean_zephyr_views.py --keep 3` (add `--dry-run`
  first). If hardlinks are unavailable the build logs a warning and copies
  the package instead.
- First-time framework builds download gigabytes (ESP-IDF ~2 GB,
  Zephyr tarballs + west deps); budget minutes-to-tens-of-minutes and
  prefer a background run.
- A `platform.json` pin change re-runs ALL frameworks, not just the
  family you touched (ADR-0002 single-slot rule).

## T3 -- hardware

Compile-green is not board-green: flashing (picotool / esptool /
nrfutil-mcumgr / UF2 / dfu-util / bossac) and debug sessions are
validated on physical boards before a release, per family.
