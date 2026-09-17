# AI workflow adaptation

Status: proposed (partially implemented -- see Implementation status)

## Implementation status (2026-09-15)

Delivered per this proposal (see the two decision notes under
.agents/notes/implemented/ and their commits):

- **First batch of six subdirectory `AGENTS.md` files** (boards/,
  platform_cfg/, builder/, zephyr/, examples/, scripts/ci/); the root
  rules navigate to them.
- **First and second verified gates**: `scripts/ci/verify_boards.py`
  (manifest integrity + family/zephyr routing chains + the conscious
  board snapshot) and `scripts/ci/verify_zephyr_routing.py` (routing
  and fixes-layout closure) -- both offline, standalone-runnable, with
  positive/negative fixtures, wired into
  `.github/workflows/ci-verify.yml`; `scripts/ci/smoke_pio_boards.py`
  covers the `pio boards` listing-crash regression class.
- **`platformio-add-board` skill** established (the metadata-driven
  board-addition flow and its boundaries).
- **Notes lifecycle** exercised end-to-end with two notes moving
  proposed -> implemented.

Remaining scope (why this note stays active):

- The `platformio-pr-review` skill is not built (rollout step 3).
- The "example board/framework combinations are valid" and "CI misses
  no supported example" candidate invariants are unimplemented (they
  depend on unifying the discoverers first; that landed afterwards, so
  they are now unblocked).
- The `platformio-zephyr-integration` skill stays deferred per this
  proposal's condition (until a stable, repeated flow emerges).

## Context

`platform-seeedboards` is a PlatformIO platform package: its core risk
is integration consistency across board metadata, package selection,
build adaptation, Zephyr external dependencies, cache state, upload
behavior, and hardware validation. It differs from DeepSeek Harness's
TypeScript plugin monorepo and cannot copy that project's package
rules, bilingual documentation, per-file coverage, or model-transcript
snapshots.

The current root `AGENTS.md` already separates repository boundaries
from the development process: root rules state scope, ownership,
compatibility, and notes; the `platformio-development` skill owns the
fork-based change-and-validate steps. This proposal defines the next
steps for local rules, skills, the notes lifecycle, and automated
verification.

## Proposal

### 1. Establish a limited `AGENTS.md` layering

The root `AGENTS.md` stays the repository entry point: source of
truth, protected user contracts, task entry points, evidence
requirements, and Development Notes navigation. It does not duplicate
fork, cache, build, or PR operational steps.

First batch candidate subdirectories. Each file carries only the
directory-specific, repeatedly-missed, high-consequence constraints;
the root rules must require reading them, because launching from the
repository root does not auto-read nested `AGENTS.md` files.

| Directory | Fact to protect | First rules |
| --- | --- | --- |
| `boards/` | board ID, framework list, upload/debug/memory declarations are the public PlatformIO interface | board manifests carry only PlatformIO board capabilities; never paper over a missing manifest value with builder logic |
| `platform_cfg/` | family default packages and debug configuration | express family commonality only; board-level differences need an explicit profile or board source |
| `builder/` | framework entry and family build/artifact/upload adaptation | keep the framework vs family responsibility split; no special cases keyed on board-name strings alone |
| `zephyr/` | local board, module, fix, patch, override vs framework version correspondence | every compatibility fix states its applicable version and exit condition; never treat the package cache as the source of truth |
| `examples/` | user-copyable examples and stable doc paths | examples are regression contracts, not just CI; changes must preserve or explicitly migrate stable paths |
| `scripts/ci/` | example discovery, build selection, logs, firmware artifacts | discovery selects by declared framework/board, not fragile directory naming |

No rules per `builder/board_build/<family>` or `.github/` yet. Subdivide
further only when a parent rule cannot cover a recurring local hazard.
Each first version stays within about 20 short rules and offers safe
paths rather than blanket prohibitions.

### 2. Keep few project-specific skills

Keep `platformio-development`; new skills reuse its steps rather than
copying the text.

| Skill | Trigger | Owns | Does not own |
| --- | --- | --- | --- |
| `platformio-pr-review` | reviewing a PR, assessing a diff, analyzing CI risk | review the full diff against the real base; trace the board -> package/profile -> builder/framework -> example/CI chain; report findings by path, impact, and evidence | no fork inputs; no commits, PRs, or cache changes |
| `platformio-add-board` | adding or formalizing a board | collect board ID, framework, MCU/upload/bootloader, family, representative example, hardware evidence; check each layer; then invoke `platformio-development` for fork validation | does not invent packages, Zephyr patches, or upload strategies |

Add `platformio-zephyr-integration` only after Zephyr
package/cache/fixes changes form a stable, independent, repeated flow.
Skill frontmatter describes only user goals and triggers; the body
holds operational steps and outputs. Whether project skills
auto-discover depends on the agent runtime, so the root rules keep
explicit path references.

### 3. Adopt the four-stage Development Notes lifecycle

Use `.agents/notes/{proposed,implemented,rejected,archived}/` with
`.agents/notes/README.md` as the authority. Initially reject
DeepSeek's category subdirectories, bilingual pairing, hash sidecars,
archive manifests, and a hard "every non-trivial change needs a note"
gate.

Typical note-worthy topics: the single source of truth for
boards/profiles, Zephyr framework package reuse, cache/workspace
write boundaries, patch/override exit strategy, upload compatibility,
CI coverage strategy. Local bug fixes and mechanical formatting do
not need notes.

This mechanism is not task management: `proposed` may contain plans;
`implemented` states only shipped facts; `rejected` keeps the key
reasons; `archived` is frozen history. Agents search the relevant
active notes before designing cross-layer changes instead of reading
the whole directory every session.

### 4. Automate the stable rules

Stable rules are long-lived, machine-decidable invariants with
evidence available from the repository source of truth. Automation
turns "every reviewer and agent must remember this check" into a
repeatable local command and a CI job; it cannot replace human
judgment on architecture ownership, hardware correctness, or
requirement trade-offs.

Follow this path rather than writing a large lint up front:

1. State one invariant precisely in a note or directory rule and name
   its single source of truth.
2. Collect one real sample that should pass and one counterexample
   that should fail, confirming the rule does not misfire on currently
   supported variants.
3. Implement a fast, network-free, package-cache-free check in
   `scripts/ci/verify_<topic>.py`; add unit tests or fixtures for
   complex rules.
4. Let developers run the command standalone first; once stable, add
   the minimal GitHub Actions check.
5. Reference the command from `AGENTS.md` or the owning skill; do not
   re-surface already-stable mechanical checks as manual review
   findings.

The first batch of candidates must be validated against current
repository data before implementation:

| Candidate invariant | Source of truth | Expected check |
| --- | --- | --- |
| board manifest parses and framework declared valid | `boards/*.json`, `platform.json` | JSON integrity; every framework name exists |
| example board/framework combination valid | `examples/**/platformio.ini`, boards | example references an existing board; the chosen framework is declared by that board |
| Zephyr mapping has no dangling references | `platform.py`, `platform.json`, `zephyr/` | board/package/Zephyr board/fix paths exist and names agree |
| CI misses no supported example | `scripts/ci/` and tracked examples | every supported project is selected by at least one discoverer or has an explicit exclusion reason |

Rules not for the first automation batch: "implementation elegance",
"which layer owns an attribute", "hardware behavior correct", "no
board-name checks allowed". These need design notes, directory rules,
PR review, and real build/hardware evidence.

### 5. Phased rollout

1. **Review this proposal.** Confirm the first batch of directories,
   skills, note triggers, and candidate invariants; add no
   implementation gates yet.
2. **Build navigation.** Add the confirmed subdirectory `AGENTS.md`
   files and update the root rules' explicit navigation; check with
   one real task whether the rules are too broad or miss something.
3. **Build the workflows.** Create and validate
   `platformio-pr-review` and `platformio-add-board`; forward-test
   each skill with a real or historical task.
4. **Exercise the notes lifecycle.** Use this proposal and the next
   cross-layer decision to rehearse proposed ->
   implemented/rejected; add no categories, bilingual files, or
   archive automation until enough history accumulates.
5. **Deliver the first gate.** Pick exactly one verified candidate
   invariant, provide pass/fail samples, and wire it into CI; decide
   on continuing based on false-positive rate and maintenance cost.

## Alternatives considered

### Copy DeepSeek Harness's full mechanism wholesale

Rejected. DeepSeek's package hierarchy, plugin seam, bilingual
pairing, strict documentation budgets, 100% coverage, and model
snapshots serve its large TypeScript agent product. PlatformIO's main
risks are external toolchains, caches, board contracts, and hardware;
copying would add maintenance burden without improving the key
validation quality.

### Keep only the root `AGENTS.md`

Rejected. Root rules cannot describe the different risks of Zephyr,
board manifests, examples, and CI without becoming overlong; future
agents also struggle to obtain local constraints in the relevant
directories.

### Create an `AGENTS.md` for every directory immediately

Rejected. Premature subdivision creates duplication and hollow rules.
The first batch covers only directories with clear boundaries and
high integration risk; the rest wait for real maintenance need.

### Turn every check into CI lint

Rejected. Only rules that are definite, stable, and constructible
into counterexamples suit gates; architecture trade-offs, business
priorities, and hardware behavior still need review, notes, and
real-device evidence.

## Consequences

This proposal shifts how agents work from "the root prompt contains
every requirement" to "root rules navigate to local rules and task
skills". The cost is maintaining a few entry files and searching notes
before design; the benefit is that local knowledge no longer crowds
out global context, high-risk flows such as fork/cache are not
misapplied to read-only tasks, and long-term decisions remain
discoverable by later work.

Implementing the first automated gate requires confirming the real
boundaries of the current manifests, examples, and Zephyr mappings.
Until that happens, any check is guesswork and must not gate CI.

## Validation

Before this proposal proceeds to implementation:

1. Confirm the first subdirectory batch covers the actual high-risk
   boundaries and does not freeze temporary implementation details
   into permanent rules.
2. Confirm the two new skills' triggers and outputs do not overlap
   and can be referenced explicitly from the current agent setups.
3. Pick one candidate stable rule, prove its source of truth,
   positive sample, and counterexample, then approve implementation.
4. Use one real board or Zephyr change to verify an agent can locate
   the root rule, the target directory rule, the related note, and
   the correct skill without reading unrelated files.

## Related files

- [`AGENTS.md`](../../../AGENTS.md)
- [`platformio-development`](../../skills/platformio-development/SKILL.md)
- [`Development Notes`](../README.md)
- [`Board family routing single source`](../implemented/2026-09-15-board-family-routing-single-source.md)
