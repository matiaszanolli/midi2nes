"""
CC65 Toolchain Wrapper for MIDI2NES.

Provides a clean interface to the CA65 assembler and LD65 linker.
"""

import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple, List

from core.exceptions import ToolchainError, CompilationError


class CC65Wrapper:
    """
    Wrapper around the CC65 toolchain (CA65 assembler, LD65 linker).

    Provides methods to assemble and link NES ROMs, with proper
    error handling and toolchain availability checking.
    """

    def __init__(self, verbose: bool = False):
        """
        Initialize the CC65 wrapper.

        Args:
            verbose: If True, print detailed command output
        """
        self.verbose = verbose
        self._ca65_path: Optional[str] = None
        self._ld65_path: Optional[str] = None

    def check_toolchain(self) -> bool:
        """
        Check if CC65 tools are available.

        Returns:
            True if all required tools are available

        Raises:
            ToolchainError: If any tool is missing
        """
        # Check CA65
        self._ca65_path = shutil.which("ca65")
        if not self._ca65_path:
            raise ToolchainError("ca65")

        # Check LD65
        self._ld65_path = shutil.which("ld65")
        if not self._ld65_path:
            raise ToolchainError("ld65")

        # Verify they actually work
        try:
            result = subprocess.run(
                ["ca65", "--version"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise ToolchainError("ca65")
        except FileNotFoundError:
            raise ToolchainError("ca65")

        try:
            result = subprocess.run(
                ["ld65", "--version"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise ToolchainError("ld65")
        except FileNotFoundError:
            raise ToolchainError("ld65")

        return True

    def get_version(self) -> Tuple[str, str]:
        """
        Get CA65 and LD65 version strings.

        Returns:
            Tuple of (ca65_version, ld65_version)
        """
        self.check_toolchain()

        ca65_result = subprocess.run(
            ["ca65", "--version"],
            capture_output=True,
            text=True,
        )
        ld65_result = subprocess.run(
            ["ld65", "--version"],
            capture_output=True,
            text=True,
        )

        return (
            ca65_result.stdout.strip() or ca65_result.stderr.strip(),
            ld65_result.stdout.strip() or ld65_result.stderr.strip(),
        )

    def assemble(
        self,
        source_file: Path,
        output_file: Path,
        working_dir: Optional[Path] = None,
        include_paths: Optional[List[Path]] = None,
    ) -> bool:
        """
        Assemble a source file using CA65.

        Args:
            source_file: Path to the .asm source file
            output_file: Path for the .o output file
            working_dir: Working directory for assembly
            include_paths: Additional include paths

        Returns:
            True on success

        Raises:
            CompilationError: If assembly fails
        """
        cmd = ["ca65", str(source_file), "-o", str(output_file)]

        if include_paths:
            for path in include_paths:
                cmd.extend(["-I", str(path)])

        result = subprocess.run(
            cmd,
            cwd=working_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            raise CompilationError(
                f"Failed to assemble {source_file.name}: {error_msg}",
                tool="ca65",
                exit_code=result.returncode,
            )

        if self.verbose:
            print(f"  Assembled: {source_file.name} -> {output_file.name}")

        return True

    def link(
        self,
        object_files: List[Path],
        output_file: Path,
        config_file: Path,
        working_dir: Optional[Path] = None,
        library_paths: Optional[List[Path]] = None,
    ) -> bool:
        """
        Link object files using LD65.

        Args:
            object_files: List of .o object files to link
            output_file: Path for the output ROM file
            config_file: Path to the linker configuration file
            working_dir: Working directory for linking
            library_paths: Additional library paths

        Returns:
            True on success

        Raises:
            CompilationError: If linking fails
        """
        cmd = ["ld65", "-C", str(config_file)]

        for obj in object_files:
            cmd.append(str(obj))

        cmd.extend(["-o", str(output_file)])

        if library_paths:
            for path in library_paths:
                cmd.extend(["-L", str(path)])

        result = subprocess.run(
            cmd,
            cwd=working_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            raise CompilationError(
                f"Failed to link ROM: {error_msg}",
                tool="ld65",
                exit_code=result.returncode,
            )

        if self.verbose:
            print(f"  Linked: {output_file.name}")

        return True

    def build(
        self,
        source_files: List[Path],
        output_file: Path,
        config_file: Path,
        working_dir: Path,
    ) -> bool:
        """
        Full build: assemble all sources and link into a ROM.

        Args:
            source_files: List of .asm source files
            output_file: Path for the output ROM file
            config_file: Path to the linker configuration file
            working_dir: Working directory for the build

        Returns:
            True on success

        Raises:
            CompilationError: If any step fails
        """
        self.check_toolchain()

        # Assemble all source files
        object_files = []
        for source in source_files:
            obj_file = working_dir / source.with_suffix(".o").name
            self.assemble(source, obj_file, working_dir)
            object_files.append(obj_file)

        # Link into ROM
        self.link(object_files, output_file, config_file, working_dir)

        return True
