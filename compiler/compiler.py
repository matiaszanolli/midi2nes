"""
NES ROM Compiler for MIDI2NES.

Compiles assembly files into NES ROM files using the CC65 toolchain.
"""

import os
import shutil
import subprocess
import traceback
from pathlib import Path
from typing import Optional

from .cc65_wrapper import CC65Wrapper
from core.exceptions import CompilationError, ValidationError
from mappers.base import BaseMapper


class ROMCompiler:
    """
    Compiles NES projects into ROM files.

    Handles the full compilation process:
    1. Validate project structure
    2. Assemble source files
    3. Link into ROM
    4. Verify output
    """

    # Minimum valid ROM size (header + some content) -- used only when the
    # mapper that produced the project is unknown; see compile()'s mapper arg.
    MIN_ROM_SIZE = 32768
    INES_HEADER_SIZE = 16

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

    def _run_post_process(self, commands: str, working_dir: Path) -> None:
        """Run a mapper's post-link fixup commands (#214/MAP-3).

        `commands` is a shell-script snippet in the same format
        BaseMapper.generate_build_script embeds into build.sh/build.bat, so it
        runs the same way here: as shell text, from the project directory
        (matching where build.sh's relative `game.nes` path resolves).

        `shell=True` is inherent to this contract — the snippet is multi-line
        shell script (`set -e`, `if %errorlevel% ...`), not an argv list, so it
        cannot be run without a shell. Safety therefore rests on the invariant
        that `commands` is a static compile-time constant produced by
        BaseMapper.generate_post_process_commands (see its SECURITY INVARIANT and
        the mapper post-process regression test), never user/runtime-derived
        text. Do not pass caller-influenced strings here (#263).
        """
        try:
            result = subprocess.run(
                commands,
                shell=True,  # nosec B602 — static mapper-constant text only (#263)
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            raise CompilationError(
                "Mapper post-process commands timed out",
                tool="post-process",
                exit_code=-1,
            )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            raise CompilationError(
                f"Mapper post-process step failed: {error_msg}",
                tool="post-process",
                exit_code=result.returncode,
            )

    def compile(
        self,
        project_dir: Path,
        output_path: Path,
        validate: bool = True,
        mapper: Optional[BaseMapper] = None,
    ) -> bool:
        """
        Compile a NES project into a ROM.

        Args:
            project_dir: Path to the NES project directory
            output_path: Where to save the compiled ROM
            validate: Whether to validate the project first
            mapper: The mapper the project was prepared with. When given, the
                generated ROM is validated against its exact declared PRG
                size instead of the flat MIN_ROM_SIZE floor (#28/M-8) -- a
                flat 32768-byte floor only catches a truncated NROM (32KB)
                image; it silently passes a truncated MMC3 (512KB) or MMC1
                (128KB) image that is still >= 32768 bytes.

        Returns:
            True on success

        Raises:
            CompilationError: If compilation fails
            ValidationError: If project is invalid
        """
        # Resolve to an absolute path up front (#316/MAP-2026-07-18-1): the
        # ca65/ld65 invocations below pass `project_dir / "main.asm"` as the
        # source arg *and* `project_dir` as the subprocess cwd. With a relative
        # project_dir (e.g. `main.py compile nes_project out.nes`, the exact
        # form CLAUDE.md documents) that doubles into `nes_project/nes_project/
        # main.asm` and ca65 fails with a confusing file-not-found. Absolute
        # paths make the source args independent of cwd.
        project_dir = Path(project_dir).resolve()
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

        # Run the mapper's post-link fixup, if any, so this path and
        # build.sh/build.bat (NESProjectBuilder._create_build_script ->
        # BaseMapper.generate_build_script) stay behaviorally identical for
        # every mapper (#214/MAP-3) -- this compiler previously had no mapper
        # reference at this point and silently skipped the step entirely.
        if mapper is not None:
            is_windows = os.name == 'nt'
            post_process = mapper.generate_post_process_commands(is_windows)
            if post_process:
                if self.verbose:
                    print("  Running mapper post-process commands...")
                self._run_post_process(post_process, project_dir)

        rom_size = rom_path.stat().st_size
        if mapper is not None:
            expected_size = mapper.prg_rom_size + self.INES_HEADER_SIZE
            if rom_size != expected_size:
                raise CompilationError(
                    f"Generated ROM size ({rom_size:,} bytes) does not match "
                    f"the expected {mapper.name} size ({expected_size:,} "
                    f"bytes = {mapper.prg_rom_size:,}-byte PRG-ROM + "
                    f"{self.INES_HEADER_SIZE}-byte header). Something went "
                    "wrong during linking."
                )
        elif rom_size < self.MIN_ROM_SIZE:
            raise CompilationError(
                f"Generated ROM is too small ({rom_size:,} bytes). "
                "Something went wrong during linking."
            )

        if self.verbose:
            print(f"  Generated ROM size: {rom_size:,} bytes ({rom_size / 1024:.1f} KB)")

        # Copy to output location
        shutil.copy(rom_path, output_path)

        return True


def compile_rom(project_dir: Path, rom_output: Path, verbose: bool = False,
                 mapper: Optional[BaseMapper] = None) -> bool:
    """
    Convenience function to compile a NES project to ROM.

    This is a drop-in replacement for the original compile_rom function
    in main.py, maintaining backwards compatibility.

    Args:
        project_dir: Path to the NES project directory
        rom_output: Where to save the compiled ROM
        verbose: Whether to print detailed progress
        mapper: The mapper the project was prepared with, for an exact ROM
            size check (#28/M-8). See ROMCompiler.compile.

    Returns:
        True on success, False on failure (prints error messages)
    """
    try:
        compiler = ROMCompiler(verbose=verbose)
        return compiler.compile(project_dir, rom_output, mapper=mapper)
    except CompilationError as e:
        print(f"[ERROR] {e}")
        return False
    except ValidationError as e:
        print(f"[ERROR] {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Compilation failed: {e}")
        # The two typed exceptions above cover every anticipated failure
        # (bad project, bad build output); reaching here means something
        # genuinely unexpected happened, so surface the traceback under
        # --verbose instead of losing its origin (#32/M-9).
        if verbose:
            traceback.print_exc()
        return False
