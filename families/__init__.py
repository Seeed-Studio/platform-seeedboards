"""Import every family module to trigger ChipFamily registration.

Adding a family = add one import line here plus the module file; core
routing files never change (ADR-0001). This import is the only
side-effecting one in the package.

Families land one milestone at a time (docs/roadmap.md) -- the list
starts empty by design and grows with each green family PR.
"""
