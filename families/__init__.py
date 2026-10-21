"""Import every family module to trigger ChipFamily registration.

Adding a family = add one import line here plus the module file; core
routing files never change (ADR-0001). This import is the only
side-effecting one in the package.
"""

from families.esp import EspFamily  # noqa: F401  (registration side effect)
from families.renesas import RenesasFamily  # noqa: F401  (registration side effect)
from families.rpi import RpiFamily  # noqa: F401  (registration side effect)
from families.samd import SamdFamily  # noqa: F401  (registration side effect)
from families.zephyr import ZephyrFamily  # noqa: F401  (registration side effect)
