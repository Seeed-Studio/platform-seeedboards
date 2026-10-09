# PlatformIO Platform Rules

## Repository role

This repository is the source of the Seeed Studio PlatformIO platform. The Git revision is the source of truth; a PlatformIO package cache, `.pio/` directory, generated firmware, or machine-local path is never a completed repository change.

## Task entry points

- Before modifying board metadata, `platform.json`, `platform.py`, `platform_cfg/`, `builder/`, `zephyr/`, examples, or CI build scripts, read and follow [platformio-development](.agents/skills/platformio-development/SKILL.md).
- Read-only investigation, design discussion, documentation-only work, and code review do not require the fork-validation inputs from that skill unless they also change PlatformIO behavior.
- Read the relevant note in [`.agents/notes/`](.agents/notes/README.md) before changing board/profile ownership, Zephyr architecture, package-cache behavior, or compatibility fixes.

## Branch and release model

- All in-progress work happens on feature branches (`fix/*`, `feat/*`, `refactor/*`, `docs/*`, `chore/*`). Never commit directly to `dev` or `main`, and never point a feature PR at `main`.
- Every PR targets `dev` and merges only after CI is green and the change is verified.
- Shipping a version is exactly one action: a `dev` -> `main` PR. Merging it *is* the release — `release-on-merge.yml` checks `platform.json`'s `version` on the PR, cuts the `X.Y.Z` tag on the merge commit, and publishes the Release. Never create tags by hand.
- `version` on `dev` always names the *next* release (strict `X.Y.Z`, greater than every existing tag). Right after a release ships, the next change merged into `dev` must bump `version` past the new tag as its own small commit; `check-dev-version.yml` fails every dev push until then.
- A failed release job published nothing (the tag was never cut) — re-run it instead of hand-pushing tags. See [`.agents/notes/implemented/2026-10-09-branch-and-release-model.md`](.agents/notes/implemented/2026-10-09-branch-and-release-model.md).

## Ownership and compatibility

| Concern | Owning location |
| --- | --- |
| Platform packages and framework entry points | `platform.json`, `platform.py` |
| PlatformIO board capabilities | `boards/<board-id>.json` |
| Zephyr board definitions | `zephyr/<family>/boards/seeed/<board>/` |
| Family package/debug defaults | `platform_cfg/` |
| Family build, artifact, and upload adaptation | `builder/board_build/<family>/` |
| Generic tool code with no chip-family knowledge | `builder/tools/` |
| Framework integration and version-specific compatibility | `builder/frameworks/`, `zephyr/` |
| User-facing regression coverage | `examples/`, `scripts/ci/`, `.github/workflows/` |

- Keep a change in its owning layer. Do not solve a board-specific problem by adding a board-name special case to a generic builder when board metadata, a profile, or a Zephyr board definition owns the value.
- `builder/tools/` admits only utilities that know nothing about a chip family, vendor, or board (today: the generic UF2 helpers `uf2conv.py`/`uf2upload.py`). Code bound to a family — VID:PID tables, upload semantics, manifest schema — belongs in `builder/board_build/<family>/` beside the family builder that invokes it.
- Each `zephyr/<family>` is a standalone Zephyr board root, and `zephyr/nrf` is the Board Root the wiki tells nRF Connect users to add. It may only contain boards whose SoC and drivers exist unpatched in the target SDK; a board that needs `zephyr/fixes.yml` fixes belongs in its own family root (e.g. `zephyr/stm32`) and reaches the framework only via the builder copy step. See [`.agents/notes/implemented/2026-10-08-zephyr-family-board-roots.md`](.agents/notes/implemented/2026-10-08-zephyr-family-board-roots.md).
- Preserve existing board IDs, example paths, framework choices, upload/debug behavior, package versions, and firmware formats unless the requested change explicitly alters that contract.
- Do not add speculative board, framework, package, or compatibility behavior without a current consumer and representative validation.

## Evidence and completion claims

- Run the narrowest meaningful validation for the changed behavior. A successful local package-cache build is not fork-based acceptance evidence.
- Report only commands actually run, the PlatformIO package path used, and remaining risk. State hardware validation as not performed unless tool output or developer-supplied results establish it.
- Before preparing a PR, keep the current branch checked out, group changes into coherent reviewable commits, and use `--force-with-lease` rather than raw `--force` for an authorized history rewrite.

## Development notes

- [`.agents/notes/`](.agents/notes/README.md) records durable investigation results, design proposals, decisions, alternatives, and validation intent. It is not a build log or a task checklist.
- Before designing or changing a cross-layer concern, search this directory for the owning or related note. This is required for board/profile ownership, Zephyr/package-cache behavior, upload compatibility, and CI strategy.
- Add or update a note when the decision will guide later work. Do not create one for a local mechanical edit. Follow the naming and status rules in the notes README.
