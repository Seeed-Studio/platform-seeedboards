# builder/main.py -- thin entry: family lookup, env config, delegation.
#
# Zero-string (ADR-0001): the family is resolved exclusively via
# ChipFamily.get(); no chip/board-name literals in this file.

from SCons.Script import DefaultEnvironment

import families  # side-effecting: triggers registration
from families.base import ChipFamily

env = DefaultEnvironment()
board = env.BoardConfig()

family = ChipFamily.get(board.get("build.chip_family", None))

if family is None:
    raise RuntimeError(
        "Board '%s' declares no build.chip_family; cannot route the build. "
        "See docs/decisions/0001-chipfamily-registry.md." % board.id
    )

family.configure_env(env, board)

for hook in family.get_build_hooks():
    hook_type = hook.get("type")
    if hook_type == "pre":
        env.AddPreAction(hook["target"], hook["callback"])
    elif hook_type == "post":
        env.AddPostAction(hook["target"], hook["callback"])
    elif hook_type == "middleware":
        env.AddBuildMiddleware(hook["callback"], hook.get("pattern", "*"))
    else:
        raise RuntimeError("unknown hook type %r in %s" % (hook_type, family))

# Delegate to the family's build script (adapted from upstream or
# SConscript'ing a package-shipped script -- ADR-0004 reuse ladder).
build_script = family.build_script(env, board)
env.SConscript(build_script, exports="env")
