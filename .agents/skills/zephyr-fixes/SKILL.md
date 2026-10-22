---
name: zephyr-fixes
description: Re-evaluate a board's Zephyr fixes after a framework bump -- read the drift the baselines report, delete upstreamed fixes, refresh the rest, re-cut fixes.baseline, prove with the zephyr matrix (ADR-0003).
---

# Re-evaluate Zephyr fixes after a framework bump

Apply `AGENTS.md` first. Fixes are the visible, shrinking delta
between vanilla Zephyr and what a board needs (ADR-0003). A framework
pin bump changes the tarball under them, and the mechanism TELLS you
what drifted -- trust it, do not skip it.

## 1. Read the drift

Build the board once after the bump. For each file under
`zephyr/boards/arm/<board>/fixes/`:

- **Override with a baseline mismatch** -- a warning: the vanilla file
  this override replaces no longer matches what it was cut against.
- **Patch with failed hunks** -- a hard error carrying the baseline
  context: the vanilla file moved under the hunks.

No message = the fix still applies cleanly against the new vanilla.

## 2. Re-evaluate each drifted fix

For every drifted file, open the NEW vanilla version inside the
framework package (`~/.platformio/packages/framework-zephyr-*/`) and
decide:

- **Upstream caught up** (the change landed vanilla): delete the fix
  file and its baseline line. This is the intended end state.
- **Still needed**: re-cut the fix against the new vanilla --
  regenerate the diff for patches, re-extract the full file for
  overrides, keeping the provenance header (source, upstream link,
  validated version, exit condition).

Never "fix the mismatch" by editing the baseline to match the old
tarball: baselines point at VANILLA upstream content only.

## 3. Re-cut baselines

For every fix that stays or changes, recompute the pristine sha256
from the NEW vanilla file and update `fixes.baseline`. Do **not** hash
the installed package or a build view: both may already contain applied
fixes (ADR-0006). Extract the pinned tarball into a scratch directory
(or install into a scratch PlatformIO core dir) and hash that file.

The two-way correspondence between fix files and baseline entries is
enforced by `verify_zephyr_routing.py` -- run it (T0).

## 4. Prove it

The **validate** skill's zephyr matrix, every board, green. A fix
without a current consumer dies (delete it): dead fixes are how the
magic-tarball problem comes back.
