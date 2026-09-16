# scripts/ci/ rules

- Build wrappers select projects by declared framework
  (filter_by_framework), never by directory-name prefix.
- Verify gates (verify_*.py) are offline, standalone, fast, and
  package-cache-free; stdlib only unless unavoidable. Developers must be
  able to run each gate directly: `python scripts/ci/verify_<topic>.py`.
- Every gate rule ships with a passing sample and a failing
  counterexample under tests/ (fixture trees); a rule without both is not
  ready to gate CI.
- New gates are added to .github/workflows/ci-verify.yml explicitly, one
  step per gate.
- snapshots inside gates (e.g. SUPPORTED_BOARD_IDS) are deliberate
  forcing functions: adding/removing their subject requires updating the
  snapshot in the same change, and the gate failure message must explain
  that.
- The shared helpers live in _examples_build_lib.py (local platform
  override, per-env builds, logs); wrappers stay thin.
- NOTE for local runs: use the pytest console script from the repo root;
  `python -m pytest` puts the repo root on sys.path and platform.py
  shadows the stdlib platform module (breaks platformio's imports).
