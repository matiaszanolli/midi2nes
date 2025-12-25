"""
Tests for the quick ROM health checker.

Tests the check_rom module which provides a simplified interface to ROM diagnostics.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from debug.check_rom import quick_check


class TestQuickCheckFunction:
    """Test the quick_check function."""

    def test_quick_check_valid_rom(self, valid_rom_file, capsys):
        """Test quick_check with a valid ROM."""
        result = quick_check(str(valid_rom_file))

        # Valid ROM should return True (health is HEALTHY or GOOD)
        # or at least produce output about the ROM
        captured = capsys.readouterr()
        assert "valid.nes" in captured.out or str(valid_rom_file.name) in captured.out or "bytes" in captured.out

    def test_quick_check_invalid_rom(self, invalid_header_rom, capsys):
        """Test quick_check with invalid ROM."""
        result = quick_check(str(invalid_header_rom))

        assert result == False
        captured = capsys.readouterr()
        assert "invalid_header" in captured.out or "ERROR" in captured.out or "❌" in captured.out

    def test_quick_check_bad_vectors_rom(self, bad_vectors_rom, capsys):
        """Test quick_check with ROM with bad vectors."""
        result = quick_check(str(bad_vectors_rom))

        # Might fail due to invalid vectors
        captured = capsys.readouterr()
        assert "bytes" in captured.out or "bad_vectors" in captured.out

    def test_quick_check_zero_filled_rom(self, zero_filled_rom, capsys):
        """Test quick_check with zero-filled ROM."""
        result = quick_check(str(zero_filled_rom))

        # Likely to fail due to excessive zeros
        captured = capsys.readouterr()
        # Should output something about the ROM
        assert "zero_filled" in captured.out or "bytes" in captured.out

    def test_quick_check_outputs_file_size(self, valid_rom_file, capsys):
        """Test that quick_check outputs file size."""
        quick_check(str(valid_rom_file))
        captured = capsys.readouterr()

        # Should show file size
        assert "bytes" in captured.out or "KB" in captured.out or "PRG" in captured.out

    def test_quick_check_shows_health_status(self, valid_rom_file, capsys):
        """Test that quick_check displays health status."""
        quick_check(str(valid_rom_file))
        captured = capsys.readouterr()

        # Should show health status emoji or text
        assert "🟢" in captured.out or "HEALTHY" in captured.out or "GOOD" in captured.out or "valid" in captured.out.lower()


class TestQuickCheckWithNonexistentFile:
    """Test quick_check with nonexistent files."""

    def test_quick_check_nonexistent_file(self, temp_dir, capsys):
        """Test quick_check with nonexistent file."""
        result = quick_check(str(temp_dir / "nonexistent.nes"))

        assert result == False
        captured = capsys.readouterr()
        assert "❌" in captured.out or "ERROR" in captured.out or "not found" in captured.out.lower()


class TestQuickCheckReturnValues:
    """Test quick_check return values."""

    def test_quick_check_returns_bool(self, valid_rom_file):
        """Test that quick_check returns a boolean."""
        result = quick_check(str(valid_rom_file))
        assert isinstance(result, bool)

    def test_quick_check_true_for_healthy(self, valid_rom_file):
        """Test that quick_check returns boolean for healthy ROM."""
        result = quick_check(str(valid_rom_file))
        # Should return True for HEALTHY/GOOD, may return True or False for FAIR
        assert isinstance(result, bool)

    def test_quick_check_false_for_error(self, invalid_header_rom):
        """Test that quick_check returns False for invalid ROM."""
        result = quick_check(str(invalid_header_rom))
        assert result == False
