# ADR-0001: ChipFamily class registry for zero-string routing

## Context

The predecessor repositories routed boards to families through substring
if-chains (four divergent copies, one per dispatch site — the proven
failure mode) and then through manifest keys plus per-family cfg modules
(dynamic import by naming convention, three-hook contract). Both worked;
the class-registry design in `docs/architecture.md` removes the last
string coupling by making the family the unit of registration.

PlatformIO's extension points are fixed by core: `platform.py`
(`configure_default_packages` / `get_boards` / `configure_debug_session`),
one `builder/main.py` entry, and framework scripts from `platform.json`.
The design must live inside those seams.

## Decision

1. `families/base.py` defines `ChipFamily` with
   `__init_subclass__`-driven auto-registration: each subclass declares
   `family_ids` and lands in `ChipFamily._registry`. `families/__init__.py`
   imports every family module (one line per family) to trigger
   registration.
2. `platform.py` resolves the family exclusively via
   `ChipFamily.get(board_config["build.chip_family"])` — no chip-name
   literals anywhere in the core.
3. `builder/main.py` resolves the same way, calls
   `family.configure_env(env, board)`, registers `family.get_build_hooks()`
   via `AddPreAction` / `AddPostAction` / `AddBuildMiddleware`, then
   delegates to the upstream framework script via `SConscript`.
4. The interface is SIX methods, not four — the debug side is not
   optional in practice (every upstream platform implements it):
   ```python
   class ChipFamily(ABC):
       family_ids: tuple[str, ...]
       def required_packages(self, board) -> set[str]         # packages to activate
       def build_flags(self, board) -> list[str]
       def upload_protocol(self, board) -> str
       def inject_debug_tools(self, board) -> None            # ~80 lines/family upstream
       def configure_debug_session(self, debug_config) -> None
       def get_build_hooks(self) -> list[dict]                # pre/post/middleware
       def configure_env(self, env, board) -> None            # optional override
   ```
   Upload *action construction* (commands, signing, touch sequences)
   stays in the family's build script or hooks — a protocol string is
   never the whole story.

## Consequences

- Adding a family = one module + one import line + manifest keys; core
  files stay untouched (the self-check is machine-enforceable via grep
  gates).
- Registration happens at import time; `families/__init__.py` is the
  only side-effecting import. Debugging is one `ChipFamily._registry`
  dump away.
- This is a fresh implementation of a proven layer — the predecessor's
  module-convention version shipped 23 boards across 7 families, so the
  risk is bounded and the migration path (wrap a cfg module in a class)
  is mechanical.

## Validation

Per-milestone build matrices through the local-checkout override (see
AGENTS.md), plus a `verify_no_string_routing` gate scanning platform.py
and builder/main.py for chip/board-name literals.

## Related files

- `docs/architecture.md`
- `families/base.py` (to be implemented)
