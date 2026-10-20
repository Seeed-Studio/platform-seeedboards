"""Family config class registry.

Each architecture family implements ``FamilyConfig``; ``FAMILY_CONFIGS``
maps the ``build.family`` board-manifest value to its class. Adding a
family = one subclass plus one registry entry; an unknown family fails
loudly here with the list of valid values (``get_family_config``).
"""

from platform_cfg.base import FamilyConfig  # noqa: F401
from platform_cfg.esp_cfg import EspConfig
from platform_cfg.nrf_cfg import NrfConfig
from platform_cfg.renesas_cfg import RenesasConfig
from platform_cfg.rpi_cfg import RpiConfig
from platform_cfg.samd_cfg import SamdConfig
from platform_cfg.siliconlab_cfg import SiliconlabConfig
from platform_cfg.stm32_cfg import Stm32Config

FAMILY_CONFIGS = {
    "esp": EspConfig,
    "nrf": NrfConfig,
    "renesas": RenesasConfig,
    "rpi": RpiConfig,
    "samd": SamdConfig,
    "siliconlab": SiliconlabConfig,
    "stm32": Stm32Config,
}


def get_family_config(family, platform):
    try:
        cls = FAMILY_CONFIGS[family]
    except KeyError:
        raise ValueError(
            "unknown build.family '%s'; valid: %s"
            % (family, sorted(FAMILY_CONFIGS))
        ) from None
    return cls(platform)
