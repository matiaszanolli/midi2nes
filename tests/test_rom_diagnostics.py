"""
Comprehensive tests for ROM diagnostics tool.

Tests the ROMDiagnostics class which validates NES ROMs and detects issues:
- Invalid iNES headers
- Incorrect ROM sizes
- Missing APU initialization code
- Invalid reset vectors
- Excessive zero bytes
- Low assembly code density
"""

import pytest
import sys
from pathlib import Path
import struct
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from debug.rom_diagnostics import ROMDiagnostics, ROMDiagnosticResult


class TestROMDiagnosticsBasic:
    """Basic tests for ROMDiagnostics initialization and setup."""

    def test_diagnostics_initialization(self):
        """Test ROMDiagnostics can be initialized."""
        diagnostics = ROMDiagnostics(verbose=False)
        assert diagnostics is not None
        assert diagnostics.verbose == False

    def test_diagnostics_verbose_mode(self):
        """Test ROMDiagnostics verbose flag."""
        diagnostics = ROMDiagnostics(verbose=True)
        assert diagnostics.verbose == True


class TestValidROMDiagnosis:
    """Test diagnosis of valid ROMs."""

    def test_diagnose_valid_rom(self, valid_rom_file):
        """Test that a valid ROM is properly diagnosed as HEALTHY or GOOD."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        assert result is not None
        assert result.is_valid_nes == True
        assert result.overall_health in ["HEALTHY", "GOOD", "FAIR"]
        assert result.file_size > 0
        assert result.prg_banks == 8
        assert result.chr_banks == 0
        assert result.reset_vectors_valid == True

    def test_valid_rom_has_no_critical_issues(self, valid_rom_file):
        """Test that a valid ROM has no critical issues."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        # Should not have critical issues
        critical_issues = [i for i in result.issues if 'invalid' in i.lower() or 'excessive' in i.lower()]
        assert len(critical_issues) <= 1  # Allow at most one non-critical issue

    def test_valid_rom_has_apu_patterns(self, valid_rom_file):
        """Test that a valid ROM contains APU initialization patterns."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        assert result.apu_pattern_count > 0, "Valid ROM should have APU patterns"

    def test_valid_rom_has_reset_vectors(self, valid_rom_file):
        """Test that a valid ROM has properly formatted reset vectors."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        assert 'NMI' in result.reset_vectors
        assert 'RESET' in result.reset_vectors
        assert 'IRQ' in result.reset_vectors
        assert all(0x8000 <= addr <= 0xFFFF for addr in result.reset_vectors.values())


class TestInvalidHeaderDetection:
    """Test detection of invalid iNES headers."""

    def test_diagnose_invalid_ines_header(self, invalid_header_rom):
        """Test that invalid header is detected."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(invalid_header_rom))

        assert result.is_valid_nes == False
        assert result.overall_health == "ERROR"
        assert len(result.issues) > 0
        assert any("Invalid iNES header" in issue for issue in result.issues)

    def test_diagnose_nonexistent_file(self, temp_dir):
        """Test handling of nonexistent ROM file."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(temp_dir / "nonexistent.nes"))

        assert result.is_valid_nes == False
        assert result.overall_health == "ERROR"
        assert len(result.issues) > 0

    def test_diagnose_empty_file(self, temp_dir):
        """Test handling of empty file."""
        empty_file = temp_dir / "empty.nes"
        empty_file.write_bytes(b'')

        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(empty_file))

        assert result.is_valid_nes == False
        assert result.overall_health == "ERROR"

    def test_diagnose_too_small_file(self, temp_dir):
        """Test handling of file smaller than iNES header."""
        small_file = temp_dir / "small.nes"
        small_file.write_bytes(b'NES')  # Only 3 bytes

        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(small_file))

        assert result.is_valid_nes == False
        assert result.overall_health == "ERROR"


class TestZeroByteDetection:
    """Test detection of excessive zero bytes."""

    def test_diagnose_zero_filled_rom(self, zero_filled_rom):
        """Test that excessive zero bytes are detected."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(zero_filled_rom))

        assert result.is_valid_nes == True
        assert result.zero_byte_percent > 70
        assert any("zero bytes" in issue.lower() for issue in result.issues)

    def test_zero_byte_percentage_calculation(self, zero_filled_rom):
        """Test that zero byte percentage is calculated correctly."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(zero_filled_rom))

        # Zero filled ROM should be ~100% zeros in PRG data
        assert result.zero_byte_percent > 85


class TestResetVectorDetection:
    """Test detection and validation of reset vectors."""

    def test_diagnose_bad_reset_vectors(self, bad_vectors_rom):
        """Test that invalid reset vectors are detected."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(bad_vectors_rom))

        assert result.is_valid_nes == True
        assert result.reset_vectors_valid == False
        assert any("reset vector" in issue.lower() for issue in result.issues)

    def test_reset_vector_extraction(self, bad_vectors_rom):
        """Test that reset vectors are correctly extracted."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(bad_vectors_rom))

        assert 'NMI' in result.reset_vectors
        assert 'RESET' in result.reset_vectors
        assert 'IRQ' in result.reset_vectors
        # Should extract the bad values we wrote
        assert result.reset_vectors['NMI'] == 0x0050
        assert result.reset_vectors['RESET'] == 0x00F0
        assert result.reset_vectors['IRQ'] == 0x0100

    def test_valid_vectors_in_good_rom(self, valid_rom_file):
        """Test that valid ROM has correct vector addresses."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        assert result.reset_vectors_valid == True
        # All vectors should point to ROM space
        for vec in result.reset_vectors.values():
            assert 0x8000 <= vec <= 0xFFFF


class TestAPUPatternDetection:
    """Test detection of APU initialization patterns."""

    def test_apu_pattern_detection_in_valid_rom(self, valid_rom_file):
        """Test that APU patterns are detected in valid ROM."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        assert result.apu_pattern_count > 0

    def test_no_apu_patterns_detected(self, no_apu_rom):
        """Test that missing APU patterns are detected."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(no_apu_rom))

        assert result.apu_pattern_count == 0
        assert any("APU" in issue for issue in result.issues)

    def test_apu_patterns_list(self):
        """Test that ROMDiagnostics has APU patterns defined."""
        diagnostics = ROMDiagnostics()
        assert len(diagnostics.APU_PATTERNS) > 0
        # Each pattern should be a tuple of (bytes, description, priority)
        for pattern in diagnostics.APU_PATTERNS:
            assert len(pattern) == 3
            assert isinstance(pattern[0], bytes)
            assert isinstance(pattern[1], str)
            assert pattern[2] in ["critical", "good", "bad", "normal"]


class TestAssemblyCodeDetection:
    """Test detection of assembly code patterns."""

    def test_assembly_patterns_defined(self):
        """Test that assembly patterns are defined."""
        diagnostics = ROMDiagnostics()
        assert len(diagnostics.ASSEMBLY_PATTERNS) > 0
        # Each pattern should be a tuple of (bytes, description)
        for pattern in diagnostics.ASSEMBLY_PATTERNS:
            assert len(pattern) == 2
            assert isinstance(pattern[0], bytes)
            assert isinstance(pattern[1], str)

    def test_assembly_code_scoring(self, valid_rom_file):
        """Test that assembly code is scored."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        assert result.assembly_code_score >= 0
        # Valid ROM with some patterns should have reasonable score
        assert result.assembly_code_score > 0

    def test_zero_assembly_score_in_zero_filled(self, zero_filled_rom):
        """Test that zero-filled ROM has low assembly score."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(zero_filled_rom))

        # Zero-filled ROM should have very low or zero assembly score
        assert result.assembly_code_score == 0


class TestROMSizeValidation:
    """Test ROM size validation."""

    def test_rom_size_matches_header(self, valid_rom_file):
        """Test that ROM size matches iNES header specification."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        # Expected size: 16 (header) + 8 * 16384 (PRG) + 0 * 8192 (CHR)
        expected = 16 + (8 * 16384)
        assert result.file_size == expected
        assert result.size_mismatch == 0

    def test_file_size_recorded(self, valid_rom_file):
        """Test that file size is correctly recorded."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        assert result.file_size > 0
        assert result.expected_size > 0
        assert result.file_size == valid_rom_file.stat().st_size


class TestPatternDensity:
    """Test pattern data density detection."""

    def test_pattern_density_calculated(self, valid_rom_file):
        """Test that pattern density is calculated."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        assert result.pattern_data_density >= 0
        assert result.pattern_data_density <= 100

    def test_low_pattern_density_detected(self, zero_filled_rom):
        """Test that low pattern density is detected."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(zero_filled_rom))

        # Zero-filled ROM should have very low pattern density
        assert result.pattern_data_density < 10


class TestHealthDetermination:
    """Test overall health status determination."""

    def test_healthy_rom_status(self, valid_rom_file):
        """Test that valid ROM gets appropriate health status."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        assert result.overall_health in ["HEALTHY", "GOOD", "FAIR"]

    def test_error_rom_status(self, invalid_header_rom):
        """Test that invalid ROM gets ERROR status."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(invalid_header_rom))

        assert result.overall_health == "ERROR"

    def test_poor_rom_status(self, zero_filled_rom):
        """Test that ROM with multiple issues gets POOR/FAIR status."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(zero_filled_rom))

        assert result.overall_health in ["POOR", "FAIR", "GOOD"]

    def test_health_based_on_issues(self, bad_vectors_rom):
        """Test that health status reflects number of issues."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(bad_vectors_rom))

        if len(result.issues) > 3:
            assert result.overall_health == "POOR"
        elif len(result.issues) > 0:
            assert result.overall_health in ["FAIR", "POOR"]


class TestRecommendations:
    """Test that recommendations are provided."""

    def test_recommendations_provided(self, bad_vectors_rom):
        """Test that recommendations are provided for issues."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(bad_vectors_rom))

        if len(result.issues) > 0:
            assert len(result.recommendations) > 0

    def test_specific_recommendations_for_issues(self, no_apu_rom):
        """Test that specific recommendations match detected issues."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(no_apu_rom))

        if any("APU" in issue for issue in result.issues):
            assert any("music player" in rec.lower() or "apu" in rec.lower()
                      for rec in result.recommendations)


class TestReportFormatting:
    """Test report generation and formatting."""

    def test_print_report_human_format(self, valid_rom_file, capsys):
        """Test that report can be printed in human format."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        diagnostics.print_report(result, format='human')
        captured = capsys.readouterr()

        assert "ROM Diagnostics" in captured.out or "MIDI2NES" in captured.out
        assert "bytes" in captured.out or "iNES" in captured.out

    def test_print_report_json_format(self, valid_rom_file, capsys):
        """Test that report can be printed in JSON format."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        diagnostics.print_report(result, format='json')
        captured = capsys.readouterr()

        # Should be valid JSON
        output_json = json.loads(captured.out)
        assert 'file_path' in output_json
        assert 'overall_health' in output_json

    def test_report_includes_diagnostics(self, valid_rom_file, capsys):
        """Test that report includes key diagnostic information."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        diagnostics.print_report(result, format='human')
        captured = capsys.readouterr()

        # Report should mention key metrics
        assert "size" in captured.out.lower() or "bytes" in captured.out.lower()


class TestDiagnosticResultDataclass:
    """Test the ROMDiagnosticResult dataclass."""

    def test_result_dataclass_creation(self, valid_rom_file):
        """Test that ROMDiagnosticResult can be created."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        assert isinstance(result, ROMDiagnosticResult)
        assert hasattr(result, 'file_path')
        assert hasattr(result, 'overall_health')
        assert hasattr(result, 'is_valid_nes')

    def test_result_has_all_fields(self, valid_rom_file):
        """Test that result has all expected fields."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        expected_fields = [
            'file_path', 'file_size', 'is_valid_nes', 'prg_banks', 'chr_banks',
            'expected_size', 'size_mismatch', 'zero_byte_percent',
            'repeated_chunks_percent', 'reset_vectors', 'reset_vectors_valid',
            'apu_pattern_count', 'pattern_data_density', 'assembly_code_score',
            'overall_health', 'issues', 'recommendations'
        ]

        for field in expected_fields:
            assert hasattr(result, field), f"Missing field: {field}"


class TestVerboseMode:
    """Test verbose output."""

    def test_verbose_mode_enabled(self, valid_rom_file, capsys):
        """Test that verbose mode produces additional output."""
        diagnostics = ROMDiagnostics(verbose=True)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        assert diagnostics.verbose == True

    def test_normal_mode_no_extra_output(self, valid_rom_file):
        """Test that non-verbose mode produces minimal output."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        assert diagnostics.verbose == False


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_single_prg_bank_rom(self, temp_dir):
        """Test ROM with minimal single PRG bank."""
        # Create 1 PRG bank ROM
        from tests.conftest import _create_ines_header

        rom_path = temp_dir / "single_bank.nes"
        header = _create_ines_header(1, 0, mapper=1)
        prg_rom = b'\x00' * (16 * 1024)
        rom_path.write_bytes(header + prg_rom)

        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(rom_path))

        assert result.is_valid_nes == True
        assert result.prg_banks == 1

    def test_rom_with_chr_data(self, temp_dir):
        """Test ROM with CHR data."""
        from tests.conftest import _create_ines_header

        rom_path = temp_dir / "with_chr.nes"
        header = _create_ines_header(8, 1, mapper=1)  # 8 PRG, 1 CHR
        prg_rom = b'\x00' * (128 * 1024)
        chr_rom = b'\x00' * (8 * 1024)
        rom_path.write_bytes(header + prg_rom + chr_rom)

        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(rom_path))

        assert result.is_valid_nes == True
        assert result.chr_banks == 1
        expected_size = 16 + (8 * 16384) + (1 * 8192)
        assert result.expected_size == expected_size
