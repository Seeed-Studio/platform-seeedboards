---
name: platformio-development
description: Develop and validate behavior-changing work in the Seeed Studio PlatformIO platform through a stable developer fork branch and one synchronized local package-cache instance. Use when implementing or debugging board metadata, platform.py, SCons builders, framework integration, examples, CI scripts, or PlatformIO package-cache synchronization.
---

# PlatformIO Development

Apply the repository rules in `AGENTS.md` first. This skill ensures that platform source changes are applied correctly and consistently to the local PlatformIO package cache, and that local development uses one clear platform environment rather than multiple inconsistent copies.

1. Before editing, require the developer to provide: fork URL, a new branch based on the fork's `main`, sample directory, PlatformIO environment, and the local fork checkout path. If any item is absent, ask for it and do not start implementation. Keep the fork URL and branch stable for the whole development task.
2. Identify the protected contract and the owning layer before choosing an implementation: board ID, framework selection, package version, upload/debug behavior, example path, or firmware artifact. Select the smallest sample and environment that exercise it.
3. Temporarily change the target sample's `platformio.ini` so its `platform` entry references the stable fork URL and branch, for example `https://github.com/<fork-owner>/platform-seeedboards.git#<branch>`. Do not use a changing commit SHA in this inner loop: each new Git commit reference creates a new `@src-<hash>` directory under the PlatformIO platforms cache. Do not commit this test-only override or any local absolute path; restore it before preparing the upstream pull request.
4. Bootstrap the package once, then discover the selected package directory with `pio system info` and `pio pkg list -d <sample> --only-platforms -v`. Record that exact directory under `C:\Users\seeed\.platformio\platforms`; never guess from a directory name and never select a different `@src-*` copy.
5. Immediately after changing any platform source file, apply the same change to the selected local PlatformIO platform package. Keep the fork checkout and that one cached package aligned before compiling. Do not modify other platform-cache copies, run `pio pkg update`, or change the fork branch/commit reference during the development loop.
6. Every time a sample compiles new firmware, run `pio run -d <sample> -e <environment> -t clean` after synchronization, then run the sample build.
7. When the developer explicitly asks to stage, commit, push, and create or update a GitHub pull request, invoke the `yeet` skill. It owns the Git and PR workflow.
