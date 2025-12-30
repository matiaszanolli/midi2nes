"""
NES ROM Compiler for MIDI2NES.

Compiles assembly files into NES ROM files using the CC65 toolchain.
"""

import shutil
from pathlib import Path
from typing import Optional

from .cc65_wrapper import CC65Wrapper
from core.exceptions import CompilationError, ValidationError


class ROMCompiler:
    """
    Compiles NES projects into ROM files.

    Handles the full compilation process:
    1. Validate project structure
    2. Assemble source files
    3. Link into ROM
    4. Verify output
    """

    # Minimum valid ROM size (header + some content)
    MIN_ROM_SIZE = 32768

    def __init__(self, verbose: bool = False):
        """
        Initialize the ROM compiler.

        Args:
            verbose: If True, print detailed progress
        """
        self.verbose = verbose
        self.cc65 = CC65Wrapper(verbose=verbose)

    def validate_project(self, project_dir: Path) -> bool:
        """
        Validate that a project directory has all required files.

        Args:
            project_dir: Path to the NES project directory

        Returns:
            True if valid

        Raises:
            ValidationError: If required files are missing
        """
        required_files = ["main.asm", "music.asm", "nes.cfg"]
        missing = []

        for filename in required_files:
            if not (project_dir / filename).exists():
                missing.append(filename)

        if missing:
            raise ValidationError(
                f"Missing required project files in {project_dir}",
                checks_failed=missing,
            )

        return True

    def compile(
        self,
        project_dir: Path,
        output_path: Path,
        validate: bool = True,
    ) -> bool:
        """
        Compile a NES project into a ROM.

        Args:
            project_dir: Path to the NES project directory
            output_path: Where to save the compiled ROM
            validate: Whether to validate the project first

        Returns:
            True on success

        Raises:
            CompilationError: If compilation fails
            ValidationError: If project is invalid
        """
        project_dir = Path(project_dir)
        output_path = Path(output_path)

        # Check toolchain availability
        if self.verbose:
            print("  Checking CC65 toolchain...")
        self.cc65.check_toolchain()

        # Validate project structure
        if validate:
            self.validate_project(project_dir)

        # Compile main.asm
        if self.verbose:
            print("  Compiling main.asm...")
        self.cc65.assemble(
            project_dir / "main.asm",
            project_dir / "main.o",
            project_dir,
        )

        # Compile music.asm
        if self.verbose:
            print("  Compiling music.asm...")
        self.cc65.assemble(
            project_dir / "music.asm",
            project_dir / "music.o",
            project_dir,
        )

        # Link ROM
        if self.verbose:
            print("  Linking ROM...")
        rom_path = project_dir / "game.nes"
        self.cc65.link(
            [project_dir / "main.o", project_dir / "music.o"],
            rom_path,
            project_dir / "nes.cfg",
            project_dir,
        )

        # Verify the generated ROM
        if not rom_path.exists():
            raise CompilationError("Generated ROM file not found")

        rom_size = rom_path.stat().st_size
        if rom_size < self.MIN_ROM_SIZE:
            raise CompilationError(
                f"Generated ROM is too small ({rom_size:,} bytes). "
                "Something went wrong during linking."
            )

        if self.verbose:
            print(f"  Generated ROM size: {rom_size:,} bytes ({rom_size / 1024:.1f} KB)")

        # Copy to output location
        shutil.copy(rom_path, output_path)

        return True


def compile_rom(project_dir: Path, rom_output: Path, verbose: bool = False) -> bool:
    """
    Convenience function to compile a NES project to ROM.

    This is a drop-in replacement for the original compile_rom function
    in main.py, maintaining backwards compatibility.

    Args:
        project_dir: Path to the NES project directory
        rom_output: Where to save the compiled ROM
        verbose: Whether to print detailed progress

    Returns:
        True on success, False on failure (prints error messages)
    """
    try:
        compiler = ROMCompiler(verbose=verbose)
        return compiler.compile(project_dir, rom_output)
    except CompilationError as e:
        print(f"[ERROR] {e}")
        return False
    except ValidationError as e:
        print(f"[ERROR] {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Compilation failed: {e}")
        return False
