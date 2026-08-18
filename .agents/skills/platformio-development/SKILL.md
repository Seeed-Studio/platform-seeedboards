---
name: platformio-development
description: Develop and validate behavior-changing work in the Seeed Studio PlatformIO platform through a developer-provided fork branch. Use when implementing or debugging board metadata, platform.py, SCons builders, framework integration, examples, CI scripts, or PlatformIO package-cache synchronization.
---

# PlatformIO Development

Apply the repository rules in `AGENTS.md` first. This skill defines the fork-based implementation and validation procedure for a PlatformIO behavior change.

1. Before editing, require the developer to provide: fork URL, fork branch, sample directory, and PlatformIO environment. If any item is absent, ask for it and do not start implementation.
2. Identify the protected contract and the owning layer before choosing an implementation: board ID, framework selection, package version, upload/debug behavior, example path, or firmware artifact. Select the smallest sample and environment that exercise it.
3. Temporarily change the target sample's `platformio.ini` so its `platform` entry references the declared fork and branch. Do not commit this test-only override or any local absolute path; restore it before preparing the upstream pull request.
4. Make each coherent repository change on the local branch, inspect the diff, and commit the repository source changes locally. Push that commit to the declared fork branch before treating a fork-based sample build as validation. If pushing is not authorized, stop and report that remote-fork validation cannot proceed.
5. Run `pio system info` and `pio pkg list -d <sample> --only-platforms -v`. Synchronize only the package-cache instance selected by that sample, and align it with the exact pushed fork revision. Do not guess a cache path, update a different cached platform, or use a broad recursive overwrite.
6. Every time a sample compiles new firmware, run `pio run -d <sample> -e <environment> -t clean` first, then run the sample build. Validate changed JSON with `python -m json.tool <file>` and changed Python/SCons with `python -m compileall -q <paths>`.
7. Treat a fix as valid only when a first-time PlatformIO user can fetch the declared fork branch and build the sample without local-only patches or fixed paths. If this cannot be demonstrated, state the missing validation and do not call the fix verified.
8. Only after the developer explicitly confirms validation passed, manage the commit history before proposing a PR:
   - keep the current branch checked out; do not create, rename, or switch branches;
   - inspect the commits since the PR base and group changes by functional unit, such as one bug fix, one board/config change, one test/example change, or one documentation change;
   - remove build-only, cache-only, and repeated verification commits from the final story by squashing or folding them into the functional commit they validate;
   - show the proposed final commit list and obtain confirmation when a commit cannot be assigned unambiguously;
   - rewrite only the current branch history with interactive rebase or an equivalent local operation;
   - fetch the current remote branch OID before publishing and update the fork with `--force-with-lease`, never raw `--force`;
   - re-check that the fork branch and selected PlatformIO package cache resolve to the final pushed commit.
9. After the history is clean and the final fork revision is confirmed, ask for the pull-request base branch if it is unknown, then provide a prefilled PR compare URL and PR title/body. Use `https://github.com/Seeed-Studio/platform-seeedboards/compare/<base>...<fork-owner>:<branch>?quick_pull=1&title=<url-encoded-title>&body=<url-encoded-body>`; do not create the PR unless asked.
