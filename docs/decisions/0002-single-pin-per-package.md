# ADR-0002: Single pin per package name (the unification constraint)

## Context

A unified platform merges the package sets of several upstream platforms
(pioarduino, maxgerhardt's rpi fork, nordicnrf52, ...). PlatformIO gives
every package NAME exactly one version slot platform-wide — there is no
per-family versioning of `tool-cmake`, `tool-jlink`, or
`toolchain-gccarmnoneeabi`. Predecessor war stories, all validated by
build matrices:

- esp (pioarduino) ships `tool-cmake` as a tools.json **stub zip** that
  only its own expansion machinery can unpack; the Zephyr families need
  the registry package. Same name, incompatible shapes → the zephyr
  builds crashed on an empty `bin/cmake` until the pin was unified to
  the registry version.
- Toolchain lines: the Adafruit nRF52 core links only on GCC 7, the
  mbed core on GCC 8, Zephyr 4.4 on GCC 12 (GCC 14 removes CMSIS 6
  intrinsics — validated broken). One slot, three valid values →
  resolved by per-family pins inside `required_packages` over a
  platform.json range that declares all three lines.

## Decision

1. platform.json declares ONE pin (or range + optionalVersions) per
   package name — the platform-wide truth. All entries optional unless
   the package is required to bootstrap (e.g. an installer tool).
2. A family narrows a version inside `required_packages` when its
   upstream validates a different line; the narrowing is a pin override
   in the family class with a comment carrying the evidence.
3. A stub/URL package is admissible ONLY IF every family that marks it
   required can expand it. Otherwise the package moves to the registry
   (or the family vendored equivalent) before it ships.
4. Conscious-version rule: upstream upgrades never auto-apply; each bump
   re-validates every family that consumes the package.

## Consequences

- Package merges are conflict-review meetings, not mechanical unions:
   every name collision between upstreams gets an explicit decision
   recorded here.
- The `ChipFamily.required_packages` return value carries both the name
  set and optional version overrides — the interface in ADR-0001
  reflects this.
- CI must build at least one board per consuming family for any package
  pin change (that is the only evidence that catches slot collisions).

## Validation

Predecessor evidence above; this repo re-proves it on first family
onboarding.

## Related files

- `platform.json`, `families/*.py`
