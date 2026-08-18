# Development Notes

Development Notes preserve decisions and investigation results that will matter after the current task ends. They give a future developer or agent the reason for a design choice, the alternatives that lost, and the validation needed to change it safely.

## Read before deciding

Search this directory before proposing or changing board/profile ownership, Zephyr package or cache behavior, patches and overrides, upload compatibility, generated firmware behavior, or CI strategy. A related active note is current guidance unless a later note states that it supersedes the decision.

## Write when the result will last

Create or update a note for a cross-layer design decision, a compatibility policy, a significant investigation result, or a proposal that needs later review. Do not use notes for copied command output, daily progress, temporary debugging, or a mechanical one-file change.

## Lifecycle and layout

Each active note lives under one lifecycle directory and is named `YYYY-MM-DD-short-topic.md`.

- `proposed/` — a design proposal or plan awaiting review or implementation.
- `implemented/` — a current decision that shipped; keep factual paths and names aligned with the code.
- `rejected/` — a proposal that was declined; retain the reason only while it prevents a plausible repeated mistake.
- `archived/` — a frozen historical implemented decision. Never edit it or treat it as current authority.

Start substantial future work in `proposed/`. When it ships, move it to `implemented/`, change `Status: proposed` to `Status: implemented`, and rewrite future-tense proposal text as the current decision and its consequences. Move a declined proposal to `rejected/` and state the reason on its status line. Archive an implemented note only when its rationale is historical rather than current guidance; add `Archived: YYYY-MM-DD` below its status before moving it.

When a newer decision fully replaces an older active one, cross-link both notes and archive the older one if its rationale is only historical. Keep partially superseded notes active and state the surviving scope. Do not add categories, bilingual pairing, or automated archive checks until the note corpus demonstrates that they are needed.

## Template

```markdown
# <Title>

Status: proposed

## Context

## Proposal

## Alternatives considered

## Consequences

## Validation

## Related files
```

Use `Decision` instead of `Proposal` in an implemented note. Keep the prose about durable behavior and trade-offs; link to source files and tests instead of pasting logs or task narration.
