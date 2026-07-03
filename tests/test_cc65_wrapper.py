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

    # --- stderr must actually be surfaced in the raised error, not swallowed ---

    def test_assemble_failure_message_includes_stderr(self, tmp_path):
        src = tmp_path / "bad.asm"
        src.write_text("; bad\n")
        out = tmp_path / "bad.o"
        fail_result = MagicMock(returncode=1, stderr="syntax error near line 5", stdout="")
        with patch("subprocess.run", return_value=fail_result):
            with pytest.raises(CompilationError) as exc_info:
                self.wrapper.assemble(src, out, working_dir=tmp_path)
        assert "syntax error near line 5" in str(exc_info.value)

    def test_link_failure_message_includes_stderr(self, tmp_path):
        obj = tmp_path / "bad.o"
        obj.write_bytes(b"")
        out = tmp_path / "game.nes"
        cfg = tmp_path / "nes.cfg"
        cfg.write_text("; stub\n")
        fail_result = MagicMock(returncode=1, stderr="undefined symbol _music_data", stdout="")
        with patch("subprocess.run", return_value=fail_result):
            with pytest.raises(CompilationError) as exc_info:
                self.wrapper.link([obj], out, cfg, working_dir=tmp_path)
        assert "undefined symbol _music_data" in str(exc_info.value)


class TestMissingToolDetection:
    """REG-09/#49: check_toolchain must raise a clear ToolchainError when
    ca65/ld65 aren't found on PATH, not fail some other way further down."""

    def setup_method(self):
        self.wrapper = CC65Wrapper()

    def test_missing_ca65_raises_toolchain_error(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(ToolchainError) as exc_info:
                self.wrapper.check_toolchain()
        assert exc_info.value.tool == "ca65"

    def test_missing_ld65_raises_toolchain_error(self):
        # ca65 resolves; ld65 does not.
        def fake_which(name):
            return "/usr/bin/ca65" if name == "ca65" else None

        ok = MagicMock(returncode=0, stdout="ca65 2.18", stderr="")
        with patch("shutil.which", side_effect=fake_which):
            with patch("subprocess.run", return_value=ok):
                with pytest.raises(ToolchainError) as exc_info:
                    self.wrapper.check_toolchain()
        assert exc_info.value.tool == "ld65"

    def test_missing_tool_error_names_the_tool(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(ToolchainError) as exc_info:
                self.wrapper.check_toolchain()
        assert "ca65" in str(exc_info.value)

    def test_ca65_version_probe_nonzero_exit_raises_toolchain_error(self):
        self.wrapper._ca65_path = "/usr/bin/ca65"
        self.wrapper._ld65_path = "/usr/bin/ld65"
        bad = MagicMock(returncode=1, stdout="", stderr="not a real binary")
        with patch("shutil.which", side_effect=lambda name: f"/usr/bin/{name}"):
            with patch("subprocess.run", return_value=bad):
                with pytest.raises(ToolchainError) as exc_info:
                    self.wrapper.check_toolchain()
        assert exc_info.value.tool == "ca65"

    def test_ld65_version_probe_nonzero_exit_raises_toolchain_error(self):
        ok = MagicMock(returncode=0, stdout="ca65 2.18", stderr="")
        bad = MagicMock(returncode=1, stdout="", stderr="not a real binary")
        with patch("shutil.which", side_effect=lambda name: f"/usr/bin/{name}"):
            with patch("subprocess.run", side_effect=[ok, bad]):
                with pytest.raises(ToolchainError) as exc_info:
                    self.wrapper.check_toolchain()
        assert exc_info.value.tool == "ld65"


class TestBuildMethod:
    """The full build() pipeline (assemble all sources, then link) had no
    direct coverage -- only its constituent assemble()/link() calls were
    tested in isolation."""

    def setup_method(self):
        self.wrapper = CC65Wrapper()

    def test_build_assembles_all_sources_then_links(self, tmp_path):
        src1 = tmp_path / "main.asm"
        src2 = tmp_path / "music.asm"
        src1.write_text("; stub\n")
        src2.write_text("; stub\n")
        out = tmp_path / "game.nes"
        cfg = tmp_path / "nes.cfg"
        cfg.write_text("; stub\n")

        with patch.object(self.wrapper, "check_toolchain") as mock_check, \
             patch.object(self.wrapper, "assemble") as mock_assemble, \
             patch.object(self.wrapper, "link") as mock_link:
            result = self.wrapper.build([src1, src2], out, cfg, tmp_path)

        assert result is True
        mock_check.assert_called_once()
        assert mock_assemble.call_count == 2
        mock_link.assert_called_once()
        linked_objects = mock_link.call_args[0][0]
        assert [p.name for p in linked_objects] == ["main.o", "music.o"]

    def test_build_propagates_assemble_failure_without_linking(self, tmp_path):
        src = tmp_path / "bad.asm"
        src.write_text("; bad\n")
        out = tmp_path / "game.nes"
        cfg = tmp_path / "nes.cfg"
        cfg.write_text("; stub\n")

        with patch.object(self.wrapper, "check_toolchain"), \
             patch.object(self.wrapper, "assemble", side_effect=CompilationError("boom", tool="ca65", exit_code=1)), \
             patch.object(self.wrapper, "link") as mock_link:
            with pytest.raises(CompilationError):
                self.wrapper.build([src], out, cfg, tmp_path)
        mock_link.assert_not_called()

    def test_build_propagates_link_failure(self, tmp_path):
        src = tmp_path / "main.asm"
        src.write_text("; stub\n")
        out = tmp_path / "game.nes"
        cfg = tmp_path / "nes.cfg"
        cfg.write_text("; stub\n")

        with patch.object(self.wrapper, "check_toolchain"), \
             patch.object(self.wrapper, "assemble"), \
             patch.object(self.wrapper, "link", side_effect=CompilationError("boom", tool="ld65", exit_code=1)):
            with pytest.raises(CompilationError):
                self.wrapper.build([src], out, cfg, tmp_path)
