"""
NES Mapper implementations for MIDI2NES.

Provides an abstraction layer for different NES mappers:
- NROM (Mapper 0): 32KB, no bank switching
- MMC1 (Mapper 1): 128KB, bank switching
- MMC3 (Mapper 4): 512KB, advanced bank switching

Usage:
    from mappers import get_mapper, MapperFactory

    # Auto-select based on data size
    mapper = get_mapper("auto", data_size=50000)

    # Or explicitly choose a mapper
    mapper = get_mapper("mmc1")

    # Generate ROM components
    header = mapper.generate_header_asm()
    config = mapper.generate_linker_config()
    init = mapper.generate_init_code()

Extending with custom mappers:
    from mappers import MapperFactory, BaseMapper

    class MyMapper(BaseMapper):
        # Implement required methods
        ...

    MapperFactory.register("mymap", MyMapper)
"""

from .base import BaseMapper
from .nrom import NROMMapper
from .mmc1 import MMC1Mapper
from .mmc3 import MMC3Mapper
from .factory import MapperFactory, get_mapper

__all__ = [
    # Base class
    "BaseMapper",
    # Implementations
    "NROMMapper",
    "MMC1Mapper",
    "MMC3Mapper",
    # Factory
    "MapperFactory",
    "get_mapper",
]
