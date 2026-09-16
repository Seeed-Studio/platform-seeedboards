# platform_cfg/ rules

One module per MCU family; the platform resolves the family from the
board manifest (build.family) and dispatches here.

- Keep the three-hook contract: configure_<family>_default_packages,
  _add_<family>_default_debug_tools, configure_<family>_debug_session.
- Express family commonality only. Board-level differences belong in the
  board manifest (or an explicit profile), not in id branching here.
- self.packages is shared across families in one process: never delete or
  pop another family's packages (regression test:
  tests/test_platform_family.py::TestCrossFamilyIsolation). Optional
  packages that this family does not need are simply left optional.
- Conditional per-board tool gating (upload-protocol-driven uploader
  selection) is fine; unconditional cross-family removal is not.
- Validate with `pytest tests/ -q` and a build of a representative board
  of the family through the platformio-development flow.
