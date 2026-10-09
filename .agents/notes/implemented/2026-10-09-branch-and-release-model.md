# Releases ship automatically on dev-to-main merges

Status: implemented

## Context

Releases used to be two manual steps: merge `dev` -> `main`, then cut and
push the `X.Y.Z` tag by hand; `release.yml` verified the tag at push time
(tag == `platform.json` `version`, tag on main) and created the Release.
The manual tag step was unguarded — a wrong tag existed and was pinnable
the moment it was pushed, with CI only able to refuse the Release after
the fact — and the step could simply be forgotten, leaving a merged main
with no release. `check_dev_version.py` (#104) established dev's side of
the discipline (dev's `version` always names the next release); this
decision completes the publishing side.

## Decision

A `dev` -> `main` PR is the release request, and merging it is the entire
release action.

- All work happens on feature branches; every PR targets `dev`; a PR merges
  only after CI is green and the change is verified.
- `release-on-merge.yml` runs `scripts/ci/check_merge_version.py` on PRs
  into main and on every push to main: `version` must be strict X.Y.Z,
  name no existing tag, and be strictly greater than every tag.
- On push to main the release job cuts tag `<version>` on the merge commit
  and creates the GitHub Release with generated notes. Pushes whose
  version is already tagged are skipped quietly.
- The old `release.yml` gates (tag == version, tag on main) hold by
  construction: CI cuts the tag from main after the check passes.
  `release.yml` and its orphaned `check_release_version.py` were removed.
- Manual `git tag` is never part of the flow.

## Alternatives considered

- Keep manual tagging with `release.yml` as gatekeeper: leaves the tag
  itself unguarded and the release dependent on a remembered second step.
- Automation that pushes the tag and lets `release.yml` create the
  Release: dead end — GITHUB_TOKEN-pushed tags trigger no workflows
  (GitHub's recursion guard), so the Release would never appear. The
  release job creates it itself instead.
- Tag protection rules (Settings -> Tags): complementary, platform-level
  enforcement, not a workflow; adopt only if rogue tags become a real
  problem.

## Consequences

- The dev -> main merge button is the publish button; merging it by
  accident publishes a release. The PR check puts a red X on the PR
  before merge, but nothing hard-blocks it (no branch protection as of
  this decision).
- A failed release job published nothing (the tag was never cut); re-run
  it. A manually pushed tag gets no Release automatically and needs one
  created by hand from the tags page — an emergency path only.
- GITHUB_TOKEN-pushed tags triggering nothing is now load-bearing: it is
  why the workflow creates the Release itself rather than delegating.

## Validation

- `check_merge_version.py` rehearsed across eight paths via
  `PLATFORM_JSON` / `GIT_TAG_LIST` stand-ins: first release against the
  real dev `platform.json` and the real tag list, next version,
  forgot-bump, both regression variants, pre-release suffix, fresh repo,
  v-prefixed tag ignored.
- The first real release doubles as the bootstrap: the first
  dev -> main merge after this lands cuts tag `1.1.0` with no manual
  steps.

## Related files

- `.github/workflows/release-on-merge.yml` (check + release jobs)
- `.github/workflows/check-dev-version.yml` (dev-side discipline, unchanged)
- `scripts/ci/check_merge_version.py`, `scripts/ci/check_dev_version.py`
- `README.md` ("Branch and release model")
