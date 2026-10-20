# Zephyr framework entry.
#
# Zero-string (ADR-0001): routes exclusively through ChipFamily.get();
# the family decides the framework script path.

from SCons.Script import DefaultEnvironment

import families  # side-effecting: registration
from families.base import ChipFamily

env = DefaultEnvironment()
board = env.BoardConfig()

family = ChipFamily.get(board.get("build.chip_family", None))
if family is None:
    raise RuntimeError(
        "Board '%s' declares no build.chip_family (ADR-0001)." % board.id
    )

family.configure_env(env, board)
env.SConscript(family.zephyr_script(env, board), exports="env")
