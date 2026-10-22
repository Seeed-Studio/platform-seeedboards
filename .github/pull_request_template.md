## Why

<!-- The problem this PR solves. Link the issue or ADR if one exists. -->

## What changed

<!-- The net change, by layer: boards / families / builder / CI / docs. -->

## Validation

<!-- What you actually ran locally, and what is left to CI. -->

- [ ] `pytest tests/ -q`
- [ ] `python scripts/ci/verify_boards.py`
- [ ] `python scripts/ci/verify_core.py`
- [ ] `python scripts/ci/verify_zephyr_routing.py`
- [ ] `python scripts/ci/verify_platform.py`
- [ ] `python scripts/ci/verify_examples.py`
- [ ] `python scripts/ci/verify_workflows.py`
- [ ] T1/T2 build: boards/envs:
- [ ] Hardware upload/debug: performed / not performed (reason):

## Checklist

- [ ] Board facts live in `boards/*.json`; behavior lives in `families/`.
- [ ] No new chip/board-name literals in `platform.py` / `builder/main.py`.
- [ ] New package names are declared in `platform.json` and activated by a family.
- [ ] Docs/ADRs updated with the code (no behavior lands before its design).