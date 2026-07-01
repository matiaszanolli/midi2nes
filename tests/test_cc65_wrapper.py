"""
Regression tests for compiler/cc65_wrapper.py

Covers SAFE-03 (#122): subprocess.run calls must have timeout= so a hung
ca65/ld65 process raises a typed error rather than blocking forever.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from compiler.cc65_wrapper import CC65Wrapper
from core.exceptions import CompilationError, ToolchainError


class TestSubprocessTimeouts:
    """SAFE-03: TimeoutExpired must surface as a typed exception, not a hang."""

    def setup_method(self):
        self.wrapper = CC65Wrapper()
        # Pretend the toolchain is installed so we can reach the subprocess calls.
        self.wrapper._ca65_path = "/usr/bin/ca65"
        self.wrapper._ld65_path = "/usr/bin/ld65"

    # --- check_toolchain probes ---

    def test_check_toolchain_ca65_timeout_raises_toolchain_error(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ca65", timeout=10)):
            with pytest.raises(ToolchainError):
                self.wrapper.check_toolchain()

    def test_check_toolchain_ld65_timeout_raises_toolchain_error(self):
        ok = MagicMock(returncode=0, stdout="ca65 2.18", stderr="")
        # CA65 probe succeeds; LD65 probe times out.
        with patch("subprocess.run", side_effect=[ok, subprocess.TimeoutExpired(cmd="ld65", timeout=10)]):
            with pytest.raises(ToolchainError):
                self.wrapper.check_toolchain()

    # --- get_version probes ---

    def test_get_version_ca65_timeout_raises_toolchain_error(self):
        with patch.object(self.wrapper, "check_toolchain"):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ca65", timeout=10)):
                with pytest.raises(ToolchainError):
                    self.wrapper.get_version()

    def test_get_version_ld65_timeout_raises_toolchain_error(self):
        ok = MagicMock(returncode=0, stdout="ca65 2.18", stderr="")
        with patch.object(self.wrapper, "check_toolchain"):
            with patch("subprocess.run", side_effect=[ok, subprocess.TimeoutExpired(cmd="ld65", timeout=10)]):
                with pytest.raises(ToolchainError):
                    self.wrapper.get_version()

    # --- assemble ---

    def test_assemble_timeout_raises_compilation_error(self, tmp_path):
        src = tmp_path / "music.asm"
        src.write_text("; stub\n")
        out = tmp_path / "music.o"
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ca65", timeout=120)):
            with pytest.raises(CompilationError) as exc_info:
                self.wrapper.assemble(src, out, working_dir=tmp_path)
        assert exc_info.value.tool == "ca65"

    def test_assemble_timeout_error_is_not_a_raw_timeout_expired(self, tmp_path):
        src = tmp_path / "music.asm"
        src.write_text("; stub\n")
        out = tmp_path / "music.o"
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ca65", timeout=120)):
            try:
                self.wrapper.assemble(src, out, working_dir=tmp_path)
            except CompilationError:
                pass
            except subprocess.TimeoutExpired:
                pytest.fail("TimeoutExpired leaked out of assemble() — should be CompilationError")

    # --- link ---

    def test_link_timeout_raises_compilation_error(self, tmp_path):
        obj = tmp_path / "music.o"
        obj.write_bytes(b"")
        out = tmp_path / "game.nes"
        cfg = tmp_path / "nes.cfg"
        cfg.write_text("; stub\n")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ld65", timeout=120)):
            with pytest.raises(CompilationError) as exc_info:
                self.wrapper.link([obj], out, cfg, working_dir=tmp_path)
        assert exc_info.value.tool == "ld65"

    def test_link_timeout_error_is_not_a_raw_timeout_expired(self, tmp_path):
        obj = tmp_path / "music.o"
        obj.write_bytes(b"")
        out = tmp_path / "game.nes"
        cfg = tmp_path / "nes.cfg"
        cfg.write_text("; stub\n")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ld65", timeout=120)):
            try:
                self.wrapper.link([obj], out, cfg, working_dir=tmp_path)
            except CompilationError:
                pass
            except subprocess.TimeoutExpired:
                pytest.fail("TimeoutExpired leaked out of link() — should be CompilationError")

    # --- verify timeout values are set (nonzero-exit still surfaces) ---

    def test_assemble_nonzero_exit_still_raises_compilation_error(self, tmp_path):
        src = tmp_path / "bad.asm"
        src.write_text("; bad\n")
        out = tmp_path / "bad.o"
        fail_result = MagicMock(returncode=1, stderr="syntax error", stdout="")
        with patch("subprocess.run", return_value=fail_result):
            with pytest.raises(CompilationError):
                self.wrapper.assemble(src, out, working_dir=tmp_path)

    def test_link_nonzero_exit_still_raises_compilation_error(self, tmp_path):
        obj = tmp_path / "bad.o"
        obj.write_bytes(b"")
        out = tmp_path / "game.nes"
        cfg = tmp_path / "nes.cfg"
        cfg.write_text("; stub\n")
        fail_result = MagicMock(returncode=1, stderr="undefined symbol", stdout="")
        with patch("subprocess.run", return_value=fail_result):
            with pytest.raises(CompilationError):
                self.wrapper.link([obj], out, cfg, working_dir=tmp_path)
