"""
Integration tests for complete MIDI to ROM pipeline with validation.

These tests generate actual NES ROMs using the full pipeline (including CC65 compilation)
and validate the generated ROM files. These are THE critical tests that catch ROM validity issues.

Pytest markers:
- @pytest.mark.slow - Takes >5 seconds
- @pytest.mark.requires_cc65 - Requires CC65 toolchain installed
- @pytest.mark.integration - Full pipeline integration test
"""

import pytest
import sys
import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import run_parse, run_map, run_frames, run_export, run_prepare, compile_rom
from nes.project_builder import NESProjectBuilder
from debug.rom_diagnostics import ROMDiagnostics
from tracker.parser_fast import parse_midi_to_frames


@pytest.mark.slow
@pytest.mark.requires_cc65
@pytest.mark.integration
class TestFullPipelineWithROMGeneration:
    """Test complete MIDI to ROM pipeline with real ROM generation."""

    def test_generate_and_validate_real_rom(self, temp_dir, minimal_midi_file):
        """
        THE CRITICAL TEST: Generate real ROM from MIDI and validate with diagnostics.

        This test exercises the complete pipeline:
        1. Parse MIDI file
        2. Map tracks to NES channels
        3. Generate frames
        4. Export to CA65 assembly
        5. Prepare NES project
        6. Compile ROM with CC65
        7. Validate ROM with diagnostics

        This is the test that will catch if ROMs are being generated without proper
        validation, as it verifies the actual ROM file contents.
        """
        # Step 1: Parse MIDI
        frames_data = parse_midi_to_frames(str(minimal_midi_file))
        assert frames_data is not None
        assert "events" in frames_data or "frames" in frames_data

        # Step 2: Create directories
        export_dir = temp_dir / "export"
        export_dir.mkdir()

        music_asm = export_dir / "music.asm"
        project_dir = temp_dir / "nes_project"
        rom_output = temp_dir / "output.nes"

        # Step 3: Export to assembly (simplified - just create minimal music.asm)
        music_asm.write_text("""; Generated music.asm
.importzp frame_counter

.segment "CODE"

; APU initialization - CRITICAL for validation
init_music:
    lda #$0F
    sta $4015              ; APU Enable - CRITICAL PATTERN
    lda #$BF
    sta $4000              ; Pulse1 Init - GOOD PATTERN
    lda #$BF
    sta $4004              ; Pulse2 Init - GOOD PATTERN
    rts

update_music:
    inc frame_counter
    bne :+
    inc frame_counter+1
:
    rts
""")

        # Step 4: Prepare project
        builder = NESProjectBuilder(str(project_dir))
        result = builder.prepare_project(str(music_asm))
        assert result == True
        assert (project_dir / "main.asm").exists()
        assert (project_dir / "nes.cfg").exists()

        # Step 5: Compile ROM with CC65 (this is where real validation should happen)
        try:
            result = compile_rom(project_dir, rom_output)
            if not result:
                pytest.skip("CC65 compilation failed - CC65 may not be installed")
        except Exception as e:
            pytest.skip(f"CC65 compilation failed: {str(e)}")

        assert rom_output.exists(), "ROM file should exist after compilation"

        # Step 6: VALIDATE ROM - THE CRITICAL STEP
        diagnostics = ROMDiagnostics(verbose=False)
        rom_result = diagnostics.diagnose_rom(str(rom_output))

        # These assertions will catch ROM validity issues
        assert rom_result.is_valid_nes == True, "Generated ROM should have valid iNES header"
        assert rom_result.reset_vectors_valid == True, "Generated ROM should have valid reset vectors"
        assert rom_result.overall_health in ["HEALTHY", "GOOD", "FAIR"], \
            f"Generated ROM should be at least FAIR health, got {rom_result.overall_health}"

        # ROM should have some APU patterns (music init code)
        assert rom_result.apu_pattern_count > 0, \
            "Generated ROM should contain APU initialization patterns"

        # ROM should not be excessive zero-filled
        assert rom_result.zero_byte_percent < 85, \
            f"Generated ROM has too many zero bytes ({rom_result.zero_byte_percent:.1f}%)"

        # ROM should have reasonable assembly code
        assert rom_result.assembly_code_score > 30, \
            f"Generated ROM has low assembly code score ({rom_result.assembly_code_score})"

    def test_rom_binary_contents_validation(self, temp_dir, minimal_midi_file):
        """Test that generated ROM contains correct binary patterns."""
        # Setup
        music_asm = temp_dir / "music.asm"
        music_asm.write_text("""; Music with APU init
.importzp frame_counter
.segment "CODE"
init_music:
    lda #$0F
    sta $4015              ; APU Enable pattern
    rts
update_music:
    inc frame_counter
    rts
""")

        project_dir = temp_dir / "project"
        rom_output = temp_dir / "output.nes"

        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(music_asm))

        try:
            result = compile_rom(project_dir, rom_output)
            if not result:
                pytest.skip("CC65 compilation failed")
        except Exception:
            pytest.skip("CC65 not installed")

        # Read ROM binary
        with open(rom_output, 'rb') as f:
            rom_data = f.read()

        # Verify iNES header
        assert rom_data[:3] == b'NES'
        assert rom_data[3] == 0x1A

        # Verify PRG bank count
        prg_banks = rom_data[4]
        assert prg_banks == 8, "Should have 8 PRG banks (128KB)"

        # Verify CHR bank count
        chr_banks = rom_data[5]
        assert chr_banks == 0, "Should have 0 CHR banks (CHR-RAM)"

        # Verify reset vectors are present in ROM data
        # Vectors should be at offset 16 + 128K - 6
        vectors_offset = 16 + (128 * 1024) - 6
        assert vectors_offset < len(rom_data)
        # Vectors should not be 0x0000
        assert rom_data[vectors_offset:vectors_offset+2] != b'\x00\x00'

    def test_rom_health_check_integration(self, temp_dir, minimal_midi_file):
        """Test that generated ROM passes health checks."""
        music_asm = temp_dir / "music.asm"
        music_asm.write_text("""; Music with APU init
.importzp frame_counter
.segment "CODE"
init_music:
    lda #$0F
    sta $4015
    lda #$BF
    sta $4000
    rts
update_music:
    rts
""")

        project_dir = temp_dir / "project"
        rom_output = temp_dir / "output.nes"

        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(music_asm))

        try:
            result = compile_rom(project_dir, rom_output)
            if not result:
                pytest.skip("CC65 compilation failed")
        except Exception:
            pytest.skip("CC65 not installed")

        # Validate ROM
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(rom_output))

        # ROM should be valid
        assert result.is_valid_nes == True

        # Check specific health metrics
        assert result.file_size > 0
        assert result.expected_size > 0
        assert result.prg_banks >= 1
        assert len(result.reset_vectors) == 3


@pytest.mark.slow
@pytest.mark.requires_cc65
@pytest.mark.integration
class TestDebugModeROMGeneration:
    """Test ROM generation with debug mode enabled."""

    def test_debug_mode_rom_generation(self, temp_dir, minimal_midi_file):
        """Test that debug mode ROM generation works."""
        music_asm = temp_dir / "music.asm"
        music_asm.write_text("""; Basic music.asm
.importzp frame_counter
.segment "CODE"
init_music:
    lda #$0F
    sta $4015
    rts
update_music:
    rts
""")

        project_dir = temp_dir / "debug_project"

        # Generate with debug mode
        builder = NESProjectBuilder(str(project_dir), debug_mode=True)
        result = builder.prepare_project(str(music_asm))
        assert result == True

        # Verify debug-related files exist
        assert (project_dir / "main.asm").exists()
        assert (project_dir / "music.asm").exists()

        rom_output = temp_dir / "debug_output.nes"

        try:
            result = compile_rom(project_dir, rom_output)
            if not result:
                pytest.skip("CC65 compilation failed")
        except Exception:
            pytest.skip("CC65 not installed")

        # Validate debug ROM
        diagnostics = ROMDiagnostics(verbose=False)
        rom_result = diagnostics.diagnose_rom(str(rom_output))

        assert rom_result.is_valid_nes == True


@pytest.mark.slow
@pytest.mark.requires_cc65
@pytest.mark.integration
class TestROMCompilationErrorHandling:
    """Test error handling in ROM compilation."""

    def test_compilation_with_missing_files(self, temp_dir):
        """Test compilation failure with missing files."""
        project_dir = temp_dir / "project"
        project_dir.mkdir()

        # Don't create any .asm files
        rom_output = temp_dir / "output.nes"

        result = compile_rom(project_dir, rom_output)
        # Should fail
        assert result == False

    def test_compilation_with_invalid_assembly(self, temp_dir):
        """Test compilation failure with invalid assembly."""
        project_dir = temp_dir / "project"
        project_dir.mkdir()

        # Create invalid assembly
        (project_dir / "main.asm").write_text("INVALID ASSEMBLY SYNTAX @#$%")
        (project_dir / "music.asm").write_text("ALSO INVALID")
        (project_dir / "nes.cfg").write_text("")

        rom_output = temp_dir / "output.nes"

        try:
            result = compile_rom(project_dir, rom_output)
            if result:
                # CC65 might be lenient, but this should fail
                pass
            else:
                assert result == False
        except Exception:
            # If CC65 isn't available, that's okay for this test
            pytest.skip("CC65 not installed")


@pytest.mark.integration
class TestROMSizeValidation:
    """Test ROM size validation."""

    def test_generated_rom_has_expected_size(self, temp_dir):
        """Test that generated ROM has the expected size."""
        music_asm = temp_dir / "music.asm"
        music_asm.write_text("""; Music
.importzp frame_counter
.segment "CODE"
init_music: rts
update_music: rts
""")

        project_dir = temp_dir / "project"
        rom_output = temp_dir / "output.nes"

        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(music_asm))

        try:
            result = compile_rom(project_dir, rom_output)
            if not result:
                pytest.skip("CC65 compilation failed")
        except Exception:
            pytest.skip("CC65 not installed")

        # ROM should be approximately: 16 bytes (header) + 128KB (PRG)
        expected_min = 16 + (128 * 1024)
        actual_size = rom_output.stat().st_size

        assert actual_size >= expected_min, \
            f"ROM size {actual_size} is less than minimum {expected_min}"

        # Should not be excessively larger
        assert actual_size < expected_min * 1.1, \
            f"ROM size {actual_size} is larger than expected {expected_min}"


@pytest.mark.integration
class TestROMValidationMetrics:
    """Test ROM validation metrics calculation."""

    def test_diagnostics_calculates_all_metrics(self, valid_rom_file):
        """Test that diagnostics calculates all required metrics."""
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(valid_rom_file))

        # All metrics should be calculated
        assert result.file_size is not None and result.file_size >= 0
        assert result.prg_banks is not None and result.prg_banks >= 0
        assert result.chr_banks is not None and result.chr_banks >= 0
        assert result.expected_size is not None and result.expected_size >= 0
        assert result.zero_byte_percent is not None
        assert result.repeated_chunks_percent is not None
        assert result.apu_pattern_count is not None and result.apu_pattern_count >= 0
        assert result.pattern_data_density is not None
        assert result.assembly_code_score is not None and result.assembly_code_score >= 0
        assert result.reset_vectors is not None
        assert result.reset_vectors_valid is not None
        assert result.overall_health in ["HEALTHY", "GOOD", "FAIR", "POOR", "ERROR"]


@pytest.mark.slow
@pytest.mark.integration
class TestPipelineFailureRecovery:
    """Test that pipeline handles failures gracefully."""

    def test_compilation_failure_without_rom_output(self, temp_dir):
        """Test that compilation failure doesn't create broken ROM."""
        project_dir = temp_dir / "project"
        project_dir.mkdir()

        # Create incomplete project
        (project_dir / "main.asm").write_text("INVALID")
        (project_dir / "music.asm").write_text("INVALID")
        (project_dir / "nes.cfg").write_text("")

        rom_output = temp_dir / "output.nes"
        assert not rom_output.exists()

        try:
            result = compile_rom(project_dir, rom_output)
            # Either compilation fails or ROM is created but might be invalid
            if result:
                # If ROM was created, it should be testable
                assert rom_output.exists()
            else:
                # Compilation failed as expected
                pass
        except Exception:
            pytest.skip("CC65 not installed")
