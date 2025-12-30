"""
Base Mapper Abstract Class for MIDI2NES.

Defines the interface that all NES mapper implementations must follow.
Each mapper generates its own header, linker config, and init code.
"""

from abc import ABC, abstractmethod
from typing import Tuple
import os


class BaseMapper(ABC):
    """
    Abstract base class for NES mapper implementations.

    Subclasses must implement all abstract methods to provide
    mapper-specific header, linker config, and initialization code.
    """

    @property
    @abstractmethod
    def mapper_number(self) -> int:
        """iNES mapper number (0, 1, 4, etc.)."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable mapper name (e.g., 'MMC1')."""
        pass

    @property
    @abstractmethod
    def prg_rom_size(self) -> int:
        """Total PRG-ROM size in bytes."""
        pass

    @property
    @abstractmethod
    def prg_bank_size(self) -> int:
        """Size of a single PRG bank in bytes."""
        pass

    @property
    def prg_bank_count(self) -> int:
        """Number of 16KB PRG banks."""
        return self.prg_rom_size // self.prg_bank_size

    @property
    def chr_rom_size(self) -> int:
        """CHR-ROM size in bytes (0 = use CHR-RAM)."""
        return 0  # Default to CHR-RAM

    @abstractmethod
    def generate_header_asm(self) -> str:
        """
        Generate the iNES header as CA65 assembly.

        Returns:
            Assembly code for the .segment "HEADER" section
        """
        pass

    @abstractmethod
    def generate_linker_config(self) -> str:
        """
        Generate the CC65 linker configuration.

        Returns:
            Complete nes.cfg linker configuration file content
        """
        pass

    @abstractmethod
    def generate_init_code(self) -> str:
        """
        Generate mapper initialization code.

        Returns:
            CA65 assembly code to initialize the mapper at reset
        """
        pass

    def generate_bank_switch_code(self, bank: int) -> str:
        """
        Generate code to switch to a specific bank.

        Args:
            bank: Bank number to switch to

        Returns:
            CA65 assembly code to switch banks
        """
        return ""  # Default: no bank switching (NROM)

    def generate_build_script(self, is_windows: bool = False) -> str:
        """
        Generate the build script for this mapper.

        Args:
            is_windows: True for Windows batch script, False for Unix shell

        Returns:
            Build script content
        """
        if is_windows:
            script = "@echo off\n"
            script += "ca65 main.asm -o main.o\n"
            script += "ca65 music.asm -o music.o\n"
            script += "ld65 -C nes.cfg main.o music.o -o game.nes\n"
        else:
            script = "#!/bin/bash\n"
            script += "ca65 main.asm -o main.o\n"
            script += "ca65 music.asm -o music.o\n"
            script += "ld65 -C nes.cfg main.o music.o -o game.nes\n"

        # Add any post-processing
        post_process = self.generate_post_process_commands(is_windows)
        if post_process:
            script += post_process

        return script

    def generate_post_process_commands(self, is_windows: bool = False) -> str:
        """
        Generate any post-linking ROM fixup commands.

        Some mappers need vector table fixes or other adjustments.

        Returns:
            Shell commands for post-processing, or empty string
        """
        return ""

    def get_data_capacity(self) -> int:
        """
        Return the available space for music data in bytes.

        This accounts for code overhead, leaving room for the music.
        """
        # Estimate ~2KB for code/vectors, rest is data
        return self.prg_rom_size - 2048

    def can_fit_data(self, data_size: int) -> bool:
        """
        Check if this mapper can fit the given data size.

        Args:
            data_size: Size of music data in bytes

        Returns:
            True if data fits, False otherwise
        """
        return data_size <= self.get_data_capacity()

    def __repr__(self) -> str:
        return f"{self.name}(mapper={self.mapper_number}, prg={self.prg_rom_size // 1024}KB)"
