# Zephyr framework patches

Small fixes for the pinned PlatformIO `framework-zephyr` package belong in
`zephyr/patches/framework-zephyr/` as numbered unified diff files:

```text
0001-short-description.patch
0002-short-description.patch
```

The PlatformIO Zephyr builder applies these patches to `framework-zephyr` before
running Zephyr's own build scripts. Patches are applied in filename order and are
idempotent: if a hunk is already present, it is skipped.

Use this patch directory for small, reviewable fixes. Use `zephyr/overrides/`
only when carrying a whole-file backport is unavoidable.
