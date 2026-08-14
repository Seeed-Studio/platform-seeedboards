# PlatformIO Development Rules

- For any change to board metadata, PlatformIO configuration, Python/SCons builders, framework integration, examples, or CI scripts, invoke `$platformio-development` before editing.
- Do not start implementation until the developer provides the fork URL, fork branch, sample directory, and PlatformIO environment to validate. Keep the Git repository and declared fork branch aligned; a PlatformIO package-cache edit is never a completed repository change.
- Before declaring the task complete, report only commands actually run, the PlatformIO package path used, and remaining risk. Report hardware behavior only from tool output or results supplied by the developer; otherwise state that hardware validation was not performed.
- Before preparing a PR, keep the current branch checked out and reorganize validation commits into coherent, independently reviewable functional units. Preserve the final fork branch name and use lease-protected history updates only.
