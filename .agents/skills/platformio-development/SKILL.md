---
name: platformio-development
description: Develop and validate changes in the Seeed Studio PlatformIO platform repository through a developer-provided fork branch. Use when implementing or debugging board metadata, platform.py, SCons builders, framework integration, examples, CI scripts, or PlatformIO package-cache synchronization.
---

# PlatformIO Development

The Git repository is the source of truth. The developer's fork branch is the only allowed source for sample validation; a local cache edit alone is never a fix.

1. Before editing, require the developer to provide: fork URL, fork branch, sample directory, and PlatformIO environment. If any item is absent, ask for it and do not start implementation.
2. Temporarily change the target sample's `platformio.ini` so its `platform` entry references the declared fork and branch. Do not commit this test-only override or any local absolute path; restore it before preparing the upstream pull request.
3. Make each coherent repository change on the local branch, inspect the diff, and commit the repository source changes locally. Push that commit to the declared fork branch before treating a fork-based sample build as validation. If pushing is not authorized, stop and report that remote-fork validation cannot proceed.
4. Run `pio system info` and `pio pkg list -d <sample> --only-platforms -v`. Synchronize only the package-cache instance selected by that sample, and align it with the exact pushed fork revision. Do not guess a cache path, update a different cached platform, or use a broad recursive overwrite.
5. Every time a sample compiles new firmware, run `pio run -d <sample> -e <environment> -t clean` first, then run the sample build. Validate changed JSON with `python -m json.tool <file>` and changed Python/SCons with `python -m compileall -q <paths>`.
6. Treat a fix as valid only when a first-time PlatformIO user can fetch the declared fork branch and build the sample without local-only patches or fixed paths. Cache state is not acceptance evidence. If this cannot be demonstrated, state the missing validation and do not call the fix verified.
7. Do not claim hardware behavior without tool output or developer-provided results. Otherwise state that hardware validation was not performed.
8. Only after the developer explicitly confirms validation passed, manage the commit history before proposing a PR:
   - keep the current branch checked out; do not create, rename, or switch branches;
   - inspect the commits since the PR base and group changes by functional unit, such as one bug fix, one board/config change, one test/example change, or one documentation change;
   - remove build-only, cache-only, and repeated verification commits from the final story by squashing or folding them into the functional commit they validate;
   - show the proposed final commit list and obtain confirmation when a commit cannot be assigned unambiguously;
   - rewrite only the current branch history with interactive rebase or an equivalent local operation;
   - fetch the current remote branch OID before publishing and update the fork with `--force-with-lease`, never raw `--force`;
   - re-check that the fork branch and selected PlatformIO package cache resolve to the final pushed commit.
9. After the history is clean and the final fork revision is confirmed, ask for the pull-request base branch if it is unknown, then provide a prefilled PR compare URL and PR title/body. Use `https://github.com/Seeed-Studio/platform-seeedboards/compare/<base>...<fork-owner>:<branch>?quick_pull=1&title=<url-encoded-title>&body=<url-encoded-body>`; do not create the PR unless asked.
