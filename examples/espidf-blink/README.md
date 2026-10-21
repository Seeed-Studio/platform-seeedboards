# espidf-blink

Minimal ESP-IDF blink used as the CI smoke test for the `espidf` framework
path (`builder/frameworks/espidf.py`, previously uncovered by any example).
Two environments cover both toolchain families: RISC-V (`seeed-xiao-esp32-c3`)
and Xtensa (`seeed-xiao-esp32-s3-sense`). Built by
`scripts/ci/build_espidf_examples.py` via
`.github/workflows/build-espidf-examples.yml`.
