"""
Mapper Factory for MIDI2NES.

Provides mapper selection with auto-detection based on data size.
"""

from typing import Optional, Type
from .base import BaseMapper
from .nrom import NROMMapper
from .mmc1 import MMC1Mapper
from .mmc3 import MMC3Mapper


class MapperFactory:
    """
    Factory for creating mapper instances.

    Supports auto-selection based on data size and explicit mapper selection.
    """

    # Default mappers in order of size (smallest first)
    _default_mappers = [
        ("nrom", NROMMapper),
        ("mmc1", MMC1Mapper),
        ("mmc3", MMC3Mapper),
    ]

    # Custom mapper registry
    _custom_mappers: dict[str, Type[BaseMapper]] = {}

    @classmethod
    def register(cls, name: str, mapper_class: Type[BaseMapper]) -> None:
        """
        Register a custom mapper.

        Args:
            name: Mapper name (lowercase)
            mapper_class: Mapper class implementing BaseMapper
        """
        cls._custom_mappers[name.lower()] = mapper_class

    @classmethod
    def unregister(cls, name: str) -> bool:
        """
        Unregister a custom mapper.

        Args:
            name: Mapper name to remove

        Returns:
            True if removed, False if not found
        """
        return cls._custom_mappers.pop(name.lower(), None) is not None

    @classmethod
    def get_mapper(cls, name: str) -> BaseMapper:
        """
        Get a mapper instance by name.

        Args:
            name: Mapper name ('nrom', 'mmc1', 'mmc3', or custom)

        Returns:
            Mapper instance

        Raises:
            ValueError: If mapper name is unknown
        """
        name_lower = name.lower()

        # Check custom mappers first
        if name_lower in cls._custom_mappers:
            return cls._custom_mappers[name_lower]()

        # Check default mappers
        for mapper_name, mapper_class in cls._default_mappers:
            if mapper_name == name_lower:
                return mapper_class()

        available = cls.list_mappers()
        raise ValueError(f"Unknown mapper: {name}. Available: {', '.join(available)}")

    @classmethod
    def auto_select(cls, data_size: int) -> BaseMapper:
        """
        Automatically select the smallest mapper that fits the data.

        Args:
            data_size: Size of music data in bytes

        Returns:
            Mapper instance that can fit the data

        Raises:
            ValueError: If data is too large for any mapper
        """
        # Try default mappers in order of size
        for mapper_name, mapper_class in cls._default_mappers:
            mapper = mapper_class()
            if mapper.can_fit_data(data_size):
                return mapper

        # Try custom mappers
        for mapper_class in cls._custom_mappers.values():
            mapper = mapper_class()
            if mapper.can_fit_data(data_size):
                return mapper

        # Nothing fits
        largest = cls._default_mappers[-1][1]()
        raise ValueError(
            f"Data size ({data_size} bytes) exceeds largest mapper capacity "
            f"({largest.get_data_capacity()} bytes)"
        )

    @classmethod
    def list_mappers(cls) -> list[str]:
        """
        List all available mapper names.

        Returns:
            List of mapper names
        """
        names = [name for name, _ in cls._default_mappers]
        names.extend(cls._custom_mappers.keys())
        return names

    @classmethod
    def get_mapper_info(cls) -> list[dict]:
        """
        Get information about all available mappers.

        Returns:
            List of dicts with mapper info
        """
        info = []

        for name, mapper_class in cls._default_mappers:
            mapper = mapper_class()
            info.append({
                "name": name,
                "mapper_number": mapper.mapper_number,
                "prg_size_kb": mapper.prg_rom_size // 1024,
                "capacity_kb": mapper.get_data_capacity() // 1024,
                "custom": False,
            })

        for name, mapper_class in cls._custom_mappers.items():
            mapper = mapper_class()
            info.append({
                "name": name,
                "mapper_number": mapper.mapper_number,
                "prg_size_kb": mapper.prg_rom_size // 1024,
                "capacity_kb": mapper.get_data_capacity() // 1024,
                "custom": True,
            })

        return info


def get_mapper(name_or_auto: str = "auto", data_size: int = 0) -> BaseMapper:
    """
    Convenience function to get a mapper.

    Args:
        name_or_auto: Mapper name or "auto" for auto-selection
        data_size: Data size in bytes (required for auto-selection)

    Returns:
        Mapper instance
    """
    if name_or_auto.lower() == "auto":
        if data_size <= 0:
            # Default to MMC1 for backwards compatibility
            return MapperFactory.get_mapper("mmc1")
        return MapperFactory.auto_select(data_size)
    return MapperFactory.get_mapper(name_or_auto)
