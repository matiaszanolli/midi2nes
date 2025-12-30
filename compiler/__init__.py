"""
NES ROM Compiler module for MIDI2NES.

Provides ROM compilation using the CC65 toolchain.

Usage:
    from compiler import compile_rom, ROMCompiler

    # Simple usage (backwards compatible with main.py)
    success = compile_rom(project_dir, output_rom)

    # Full control
    compiler = ROMCompiler(verbose=True)
    compiler.compile(project_dir, output_rom)
"""

from .compiler import ROMCompiler, compile_rom
from .cc65_wrapper import CC65Wrapper

__all__ = [
    "ROMCompiler",
    "compile_rom",
    "CC65Wrapper",
]
