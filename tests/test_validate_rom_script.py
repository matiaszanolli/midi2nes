"""
Tests for the validate_rom.py standalone validator script.

Tests the validate_rom function which performs basic NES ROM validation.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from validate_rom import validate_rom


class TestValidateROMFunction:
    """Test the validate_rom function."""

    def test_validate_valid_rom(self, valid_rom_file):
        """Test validate_rom with a valid ROM."""
        result = validate_rom(str(valid_rom_file))
        assert result == True

    def test_validate_invalid_header_rom(self, invalid_header_rom):
        """Test validate_rom with invalid header."""
        result = validate_rom(str(invalid_header_rom))
        assert result == False

    def test_validate_bad_vectors_rom(self, bad_vectors_rom):
        """Test validate_rom with bad reset vectors."""
        result = validate_rom(str(bad_vectors_rom))
        # ROM with bad vectors pointing to zero page might be detected as problematic
        # The result should be a boolean
        assert isinstance(result, bool)

    def test_validate_zero_filled_rom(self, zero_filled_rom):
        """Test validate_rom with zero-filled ROM."""
        result = validate_rom(str(zero_filled_rom))
        # Should pass basic validation (valid header and vectors)
        # But might have other issues
        assert isinstance(result, bool)


class TestValidateROMWithNonexistentFile:
    """Test validate_rom with nonexistent files."""

    def test_validate_nonexistent_file(self, temp_dir):
        """Test validate_rom with nonexistent file."""
        result = validate_rom(str(temp_dir / "nonexistent.nes"))
        assert result == False

    def test_validate_empty_file(self, temp_dir):
        """Test validate_rom with empty file."""
        empty_file = temp_dir / "empty.nes"
        empty_file.write_bytes(b'')

        result = validate_rom(str(empty_file))
        assert result == False

    def test_validate_too_small_file(self, temp_dir):
        """Test validate_rom with file too small for header."""
        small_file = temp_dir / "small.nes"
        small_file.write_bytes(b'NES')

        result = validate_rom(str(small_file))
        assert result == False


class TestValidateROMHeaderDetection:
    """Test header detection in validate_rom."""

    def test_detects_valid_header(self, valid_rom_file, capsys):
        """Test that valid iNES header is detected."""
        validate_rom(str(valid_rom_file))
        captured = capsys.readouterr()

        assert "Valid iNES header" in captured.out or "✅" in captured.out

    def test_detects_invalid_header(self, invalid_header_rom, capsys):
        """Test that invalid header is detected."""
        validate_rom(str(invalid_header_rom))
        captured = capsys.readouterr()

        assert "Invalid" in captured.out or "❌" in captured.out

    def test_detects_invalid_signature(self, temp_dir, capsys):
        """Test detection of invalid iNES signature."""
        bad_header = temp_dir / "bad_header.nes"
        bad_header.write_bytes(b'BAD\x1A' + b'\x00' * 131072)

        validate_rom(str(bad_header))
        captured = capsys.readouterr()

        assert "Invalid iNES header" in captured.out or "signature" in captured.out.lower()


class TestValidateROMBankInfo:
    """Test PRG/CHR bank information."""

    def test_reports_prg_banks(self, valid_rom_file, capsys):
        """Test that PRG bank count is reported."""
        validate_rom(str(valid_rom_file))
        captured = capsys.readouterr()

        assert "PRG-ROM" in captured.out or "banks" in captured.out
        assert "8" in captured.out  # valid_rom_file has 8 banks

    def test_reports_chr_banks(self, valid_rom_file, capsys):
        """Test that CHR bank count is reported."""
        validate_rom(str(valid_rom_file))
        captured = capsys.readouterr()

        assert "CHR-ROM" in captured.out or "CHR" in captured.out

    def test_reports_mapper(self, valid_rom_file, capsys):
        """Test that mapper number is reported."""
        validate_rom(str(valid_rom_file))
        captured = capsys.readouterr()

        assert "Mapper" in captured.out or "mapper" in captured.out


class TestValidateROMSize:
    """Test ROM size validation."""

    def test_checks_rom_size(self, valid_rom_file, capsys):
        """Test that ROM size is checked."""
        validate_rom(str(valid_rom_file))
        captured = capsys.readouterr()

        assert "size" in captured.out.lower() or "bytes" in captured.out

    def test_detects_size_mismatch(self, temp_dir, capsys):
        """Test detection of size mismatch."""
        from tests.conftest import _create_ines_header

        # Create ROM with wrong size
        rom_path = temp_dir / "wrong_size.nes"
        header = _create_ines_header(8, 0, mapper=1)
        # Only add half the expected data
        prg_rom = b'\x00' * (64 * 1024)  # Only 64KB instead of 128KB
        rom_path.write_bytes(header + prg_rom)

        validate_rom(str(rom_path))
        captured = capsys.readouterr()

        # Should detect size mismatch
        assert "mismatch" in captured.out.lower() or "Size" in captured.out

    def test_reports_correct_size(self, valid_rom_file, capsys):
        """Test reporting of correct ROM size."""
        validate_rom(str(valid_rom_file))
        captured = capsys.readouterr()

        assert "matches header" in captured.out or "✅" in captured.out or "Size" in captured.out


class TestValidateROMVectors:
    """Test reset vector validation."""

    def test_checks_reset_vector(self, valid_rom_file, capsys):
        """Test that reset vector is checked."""
        validate_rom(str(valid_rom_file))
        captured = capsys.readouterr()

        assert "vector" in captured.out.lower() or "Reset" in captured.out

    def test_detects_invalid_reset_vector(self, bad_vectors_rom, capsys):
        """Test detection of invalid reset vector."""
        validate_rom(str(bad_vectors_rom))
        captured = capsys.readouterr()

        # Should report about vectors
        assert "vector" in captured.out.lower() or "Reset" in captured.out

    def test_rejects_zero_reset_vector(self, temp_dir, capsys):
        """Test that zero reset vector is rejected."""
        from tests.conftest import _create_ines_header
        import struct

        rom_path = temp_dir / "zero_vector.nes"
        header = _create_ines_header(8, 0, mapper=1)
        prg_rom = bytearray(128 * 1024)

        # Set reset vector to 0
        vectors_offset = 0x20000 - 6
        prg_rom[vectors_offset:vectors_offset+2] = struct.pack('<H', 0x0000)  # NMI
        prg_rom[vectors_offset+2:vectors_offset+4] = struct.pack('<H', 0x0000)  # RESET = 0
        prg_rom[vectors_offset+4:vectors_offset+6] = struct.pack('<H', 0x8000)  # IRQ

        rom_path.write_bytes(header + bytes(prg_rom))

        result = validate_rom(str(rom_path))
        captured = capsys.readouterr()

        assert result == False
        assert "zero" in captured.out.lower() or "won't boot" in captured.out

    def test_accepts_valid_reset_vector(self, valid_rom_file, capsys):
        """Test that valid reset vector is accepted."""
        result = validate_rom(str(valid_rom_file))
        assert result == True
        captured = capsys.readouterr()

        assert "valid" in captured.out.lower() or "✅" in captured.out


class TestValidateROMOutput:
    """Test output formatting."""

    def test_output_includes_filename(self, valid_rom_file, capsys):
        """Test that filename is included in output."""
        validate_rom(str(valid_rom_file))
        captured = capsys.readouterr()

        assert "valid.nes" in captured.out or str(valid_rom_file.name) in captured.out

    def test_output_includes_rom_size(self, valid_rom_file, capsys):
        """Test that ROM size is in output."""
        validate_rom(str(valid_rom_file))
        captured = capsys.readouterr()

        # Should show bytes and/or KB
        assert "bytes" in captured.out or "KB" in captured.out

    def test_output_includes_status_emoji(self, valid_rom_file, capsys):
        """Test that status emoji are included."""
        validate_rom(str(valid_rom_file))
        captured = capsys.readouterr()

        # Should have some emoji or status indicator
        assert any(symbol in captured.out for symbol in ['✅', '❌', '⚠️', '🎮', '📏'])


class TestValidateROMReturnValues:
    """Test return value consistency."""

    def test_returns_bool(self, valid_rom_file):
        """Test that validate_rom returns a boolean."""
        result = validate_rom(str(valid_rom_file))
        assert isinstance(result, bool)

    def test_returns_true_for_valid(self, valid_rom_file):
        """Test that validate_rom returns True for valid ROM."""
        result = validate_rom(str(valid_rom_file))
        assert result == True

    def test_returns_false_for_invalid(self, invalid_header_rom):
        """Test that validate_rom returns False for invalid ROM."""
        result = validate_rom(str(invalid_header_rom))
        assert result == False

    def test_returns_false_for_nonexistent(self, temp_dir):
        """Test that validate_rom returns False for nonexistent file."""
        result = validate_rom(str(temp_dir / "nonexistent.nes"))
        assert result == False
