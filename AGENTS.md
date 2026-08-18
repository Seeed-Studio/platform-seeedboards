# PlatformIO Platform Rules

## Repository role

This repository is the source of the Seeed Studio PlatformIO platform. The Git revision is the source of truth; a PlatformIO package cache, `.pio/` directory, generated firmware, or machine-local path is never a completed repository change.

## Task entry points

- Before modifying board metadata, `platform.json`, `platform.py`, `platform_cfg/`, `builder/`, `zephyr/`, examples, or CI build scripts, read and follow [platformio-development](.agents/skills/platformio-development/SKILL.md).
- Read-only investigation, design discussion, documentation-only work, and code review do not require the fork-validation inputs from that skill unless they also change PlatformIO behavior.
- Read [docs/REFACTORING_PIO.md](docs/REFACTORING_PIO.md) before changing board/profile ownership, Zephyr architecture, package-cache behavior, or compatibility fixes.

## Ownership and compatibility

| Concern | Owning location |
| --- | --- |
| Platform packages and framework entry points | `platform.json`, `platform.py` |
| PlatformIO board capabilities | `boards/<board-id>.json` |
| Family package/debug defaults | `platform_cfg/` |
| Family build, artifact, and upload adaptation | `builder/board_build/<family>/` |
| Framework integration and version-specific compatibility | `builder/frameworks/`, `zephyr/` |
| User-facing regression coverage | `examples/`, `scripts/ci/`, `.github/workflows/` |

- Keep a change in its owning layer. Do not solve a board-specific problem by adding a board-name special case to a generic builder when board metadata, a profile, or a Zephyr board definition owns the value.
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
