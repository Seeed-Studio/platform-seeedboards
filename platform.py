# platform-unified platform entry.
#
# Zero-string core (ADR-0001): the family is resolved exclusively via
# the ChipFamily registry keyed by the manifest's build.chip_family.
# This module contains no chip/board-name literals.

import sys
from pathlib import Path

from platformio.public import PlatformBase

_REPO_ROOT = Path(__file__).resolve().parent

# families/ lives next to this file; make it importable regardless of
# the interpreter's working directory.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import families  # noqa: E402  (side-effecting: triggers registration)
from families.base import ChipFamily  # noqa: E402


class UnifiedPlatform(PlatformBase):
    def configure_default_packages(self, variables, targets):
        if not variables.get("board"):
            return super().configure_default_packages(variables, targets)

        board_name = variables.get("board")
        family = self.get_board_family(board_name)
        if family is None:
            return super().configure_default_packages(variables, targets)

        for name, version_override in family.required_packages(
            self.board_config(board_name).manifest
        ).items():
            if name not in self.packages:
                continue
            self.packages[name]["optional"] = False
            if version_override:
                self.packages[name]["version"] = version_override

        return super().configure_default_packages(variables, targets)

    def get_board_family(self, board_name):
        """Resolve the ChipFamily for a board id, or None.

        Missing build.chip_family on a repo manifest raises (fail loud);
        external manifests (user-custom boards) warn and return None.
        """
        board = PlatformBase.get_boards(self, board_name)
        if board is None:
            return None
        family_id = board.get("build.chip_family", None)
        if not family_id:
            self._warn_or_raise_missing_key(board)
            return None
        return ChipFamily.get(family_id)

    def _warn_or_raise_missing_key(self, board):
        import os

        manifest_dir = os.path.dirname(os.path.abspath(board.manifest_path))
        boards_dir = str(_REPO_ROOT / "boards")
        if os.path.normpath(manifest_dir) == os.path.normpath(boards_dir):
            raise KeyError(
                "Board '%s' is missing build.chip_family in %s -- add the "
                "routing key (see boards/ and docs/decisions/0001)."
                % (board.id, board.manifest_path)
            )
        print(
            "Warning: board '%s' declares no build.chip_family in %s; "
            "skipping family handling" % (board.id, board.manifest_path)
        )

    def get_boards(self, id_=None):
        result = super().get_boards(id_)
        if not result:
            return result
        if id_:
            return self._inject_debug_tools(result)
        for key in result:
            result[key] = self._inject_debug_tools(result[key])
        return result

    def _inject_debug_tools(self, board):
        """Family debug-tool injection; always returns the board object
        (a None return crashes core's listing)."""
        family_id = board.get("build.chip_family", None)
        family = ChipFamily.get(family_id) if family_id else None
        if family is not None:
            family.inject_debug_tools(board)
        return board

    def configure_debug_session(self, debug_config):
        board_config = getattr(debug_config, "board_config", None)
        if not board_config:
            return
        family_id = board_config.get("build.chip_family", None)
        family = ChipFamily.get(family_id) if family_id else None
        if family is not None:
            family.configure_debug_session(debug_config)
