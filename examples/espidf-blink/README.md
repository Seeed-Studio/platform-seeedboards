# espidf-blink

Minimal ESP-IDF blink used as the CI smoke test for the `espidf` framework
path (`builder/frameworks/espidf.py`). Five environments cover both toolchain
families: RISC-V (`c3`, `c5`, `c6`) and Xtensa (`s3-plus`, `s3-sense`).
Built by `scripts/ci/build_examples.py --framework espidf` via
`.github/workflows/build-espidf-examples.yml`.

Per-env flash/partition overrides live in `sdkconfig.defaults.<env>`; the
generated `sdkconfig.<env>` files are intentionally not committed (they are
platform-version-specific output, not source).
