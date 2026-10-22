# .agents — agent-facing assets

Tool-agnostic home for coding-agent material; `.claude` is a symlink
to this directory so Claude Code discovers the same skills natively.

```
skills/
  add-board/       board = data: manifest + demo envs + snapshot + matrix
  add-family/      new ChipFamily module, family-owned builder, packages
  sync-upstream/   absorb upstream releases / restructures / board data
  validate/        the validation tiers: offline gates + demo matrices
  zephyr-fixes/    re-evaluate fixes on a framework bump (ADR-0003)
```

Skills encode the maintenance loops this repository already runs;
they point at the binding documents (`AGENTS.md`, `docs/decisions/`)
instead of duplicating them. When a loop changes, change the skill and
the ADR it cites together.
