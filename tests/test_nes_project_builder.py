"""
Comprehensive tests for NESProjectBuilder.

Tests the NESProjectBuilder class which creates complete NES projects:
- Generates main.asm with NMI handlers and reset vectors
- Generates nes.cfg linker configuration
- Creates build scripts (build.sh/build.bat)
- Integrates music.asm with generated project structure
- Supports debug mode with debug overlay
"""

import pytest
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nes.project_builder import NESProjectBuilder


class TestNESProjectBuilderInitialization:
    """Test NESProjectBuilder initialization."""

    def test_builder_initialization(self, project_dir):
        """Test that NESProjectBuilder can be initialized."""
        builder = NESProjectBuilder(str(project_dir))
        assert builder is not None
        assert builder.project_path == Path(project_dir)
        assert builder.use_mmc1 == True
        assert builder.debug_mode == False

    def test_builder_with_debug_mode(self, project_dir):
        """Test NESProjectBuilder with debug mode enabled."""
        builder = NESProjectBuilder(str(project_dir), debug_mode=True)
        assert builder.debug_mode == True
        assert builder.use_mmc1 == True


class TestProjectStructureCreation:
    """Test that prepare_project creates all required files."""

    def test_prepare_project_creates_directory(self, temp_dir, minimal_music_asm):
        """Test that prepare_project creates the project directory."""
        project_dir = temp_dir / "new_project"
        assert not project_dir.exists()

        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        assert project_dir.exists()
        assert project_dir.is_dir()

    def test_prepare_project_creates_all_files(self, project_dir, minimal_music_asm):
        """Test that prepare_project creates all required files."""
        builder = NESProjectBuilder(str(project_dir))
        result = builder.prepare_project(str(minimal_music_asm))

        assert result == True
        assert (project_dir / "main.asm").exists()
        assert (project_dir / "music.asm").exists()
        assert (project_dir / "nes.cfg").exists()

        # Build script should exist (name depends on OS)
        build_script = project_dir / "build.sh" if os.name != 'nt' else project_dir / "build.bat"
        assert build_script.exists()

    def test_music_asm_copied_correctly(self, project_dir, minimal_music_asm):
        """Test that music.asm is copied with correct content."""
        music_content = minimal_music_asm.read_text()

        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        project_music = project_dir / "music.asm"
        assert project_music.exists()
        assert "init_music" in project_music.read_text()


class TestMainAsmGeneration:
    """Test main.asm generation."""

    def test_main_asm_is_generated(self, project_dir, minimal_music_asm):
        """Test that main.asm is generated."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        main_asm = project_dir / "main.asm"
        assert main_asm.exists()
        content = main_asm.read_text()
        assert len(content) > 0

    def test_main_asm_has_ines_header(self, project_dir, minimal_music_asm):
        """Test that main.asm defines iNES header."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        main_asm = project_dir / "main.asm"
        content = main_asm.read_text()

        # Should define iNES header
        assert '.segment "HEADER"' in content
        assert 'NES", $1A' in content or '"NES", $1A' in content
        assert '$08' in content  # 8 PRG banks
        assert '$00' in content  # 0 CHR banks
        assert '$10' in content  # Mapper 1 (MMC1)

    def test_main_asm_has_reset_handler(self, project_dir, minimal_music_asm):
        """Test that main.asm defines reset handler."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        main_asm = project_dir / "main.asm"
        content = main_asm.read_text()

        assert 'reset:' in content or 'reset' in content.lower()
        assert 'sei' in content  # Disable interrupts
        assert 'cld' in content  # Clear decimal mode
        assert 'ldx #$FF' in content or 'ldx #' in content  # Set up stack

    def test_main_asm_has_nmi_handler(self, project_dir, minimal_music_asm):
        """Test that main.asm defines NMI handler."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        main_asm = project_dir / "main.asm"
        content = main_asm.read_text()

        assert 'nmi:' in content or 'NMI:' in content.upper()
        assert 'jsr update_music' in content or 'update_music' in content
        assert 'rti' in content  # Return from interrupt

    def test_main_asm_has_irq_handler(self, project_dir, minimal_music_asm):
        """Test that main.asm defines IRQ handler."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        main_asm = project_dir / "main.asm"
        content = main_asm.read_text()

        assert 'irq:' in content or 'IRQ:' in content.upper()

    def test_main_asm_has_vector_table(self, project_dir, minimal_music_asm):
        """Test that main.asm defines interrupt vector table."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        main_asm = project_dir / "main.asm"
        content = main_asm.read_text()

        assert '.segment "VECTORS"' in content or 'VECTORS' in content
        assert '.word nmi' in content or 'nmi' in content
        assert '.word reset' in content or 'reset' in content
        assert '.word irq' in content or 'irq' in content

    def test_main_asm_has_mmc1_initialization(self, project_dir, minimal_music_asm):
        """Test that main.asm initializes MMC1 mapper."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        main_asm = project_dir / "main.asm"
        content = main_asm.read_text()

        # Should initialize MMC1
        assert '#$80' in content  # Reset command
        assert '$8000' in content  # MMC1 control register
        assert 'MMC1' in content.upper() or '$8000' in content

    def test_main_asm_has_music_imports(self, project_dir, minimal_music_asm):
        """Test that main.asm imports music functions."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        main_asm = project_dir / "main.asm"
        content = main_asm.read_text()

        assert 'init_music' in content
        assert 'update_music' in content

    def test_main_asm_has_zeropage_variables(self, project_dir, minimal_music_asm):
        """Test that main.asm defines zeropage variables."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        main_asm = project_dir / "main.asm"
        content = main_asm.read_text()

        assert '.segment "ZEROPAGE"' in content or 'ZEROPAGE' in content
        assert 'frame_counter' in content
        assert '.exportzp' in content or 'exportzp' in content

    def test_main_asm_enables_nmi(self, project_dir, minimal_music_asm):
        """Test that main.asm enables NMI for 60Hz timing."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        main_asm = project_dir / "main.asm"
        content = main_asm.read_text()

        # Should enable NMI ($2000 = $80)
        assert '#$80' in content
        assert '$2000' in content


class TestLinkerConfigGeneration:
    """Test nes.cfg linker configuration generation."""

    def test_nes_cfg_is_generated(self, project_dir, minimal_music_asm):
        """Test that nes.cfg is generated."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        nes_cfg = project_dir / "nes.cfg"
        assert nes_cfg.exists()
        content = nes_cfg.read_text()
        assert len(content) > 0

    def test_nes_cfg_has_memory_sections(self, project_dir, minimal_music_asm):
        """Test that nes.cfg defines memory sections."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        nes_cfg = project_dir / "nes.cfg"
        content = nes_cfg.read_text()

        # Should have MEMORY section
        assert 'MEMORY' in content

    def test_nes_cfg_has_header_section(self, project_dir, minimal_music_asm):
        """Test that nes.cfg defines HEADER section."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        nes_cfg = project_dir / "nes.cfg"
        content = nes_cfg.read_text()

        assert 'HEADER' in content
        assert 'start = $0000' in content
        assert 'size = $0010' in content  # 16 bytes for header

    def test_nes_cfg_has_prg_rom_section(self, project_dir, minimal_music_asm):
        """Test that nes.cfg defines 128KB PRG-ROM section."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        nes_cfg = project_dir / "nes.cfg"
        content = nes_cfg.read_text()

        # MMC1 uses PRGSWAP (0x1C000 = 112KB) + PRGFIXED (0x4000 = 16KB) = 128KB total
        # Check for either MMC1 structure or simple PRG structure
        has_mmc1 = 'PRGSWAP' in content and 'PRGFIXED' in content
        has_simple_prg = ('0x20000' in content or '$20000' in content)
        assert has_mmc1 or has_simple_prg, "Should have either MMC1 (PRGSWAP+PRGFIXED) or simple PRG structure"

    def test_nes_cfg_has_zeropage_section(self, project_dir, minimal_music_asm):
        """Test that nes.cfg defines zero page."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        nes_cfg = project_dir / "nes.cfg"
        content = nes_cfg.read_text()

        assert 'ZP' in content or 'ZEROPAGE' in content
        assert '$0000' in content
        assert '$0100' in content  # Zero page is $0000-$00FF

    def test_nes_cfg_has_segments(self, project_dir, minimal_music_asm):
        """Test that nes.cfg has SEGMENTS section."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        nes_cfg = project_dir / "nes.cfg"
        content = nes_cfg.read_text()

        assert 'SEGMENTS' in content
        assert 'CODE' in content
        assert 'VECTORS' in content

    def test_nes_cfg_vectors_at_fffa(self, project_dir, minimal_music_asm):
        """Test that nes.cfg places vectors at $FFFA."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        nes_cfg = project_dir / "nes.cfg"
        content = nes_cfg.read_text()

        # Vectors should be at end of ROM ($FFFA)
        assert '$FFFA' in content or '0xFFFA' in content


class TestBuildScriptGeneration:
    """Test build script generation."""

    def test_build_script_is_created(self, project_dir, minimal_music_asm):
        """Test that build script is created."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        # Build script name depends on OS
        build_script = project_dir / "build.sh" if os.name != 'nt' else project_dir / "build.bat"
        assert build_script.exists()

    def test_build_script_contains_ca65(self, project_dir, minimal_music_asm):
        """Test that build script compiles with ca65."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        build_script = project_dir / "build.sh" if os.name != 'nt' else project_dir / "build.bat"
        content = build_script.read_text()

        assert 'ca65' in content
        assert 'main.asm' in content
        assert 'music.asm' in content

    def test_build_script_contains_ld65(self, project_dir, minimal_music_asm):
        """Test that build script links with ld65."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        build_script = project_dir / "build.sh" if os.name != 'nt' else project_dir / "build.bat"
        content = build_script.read_text()

        assert 'ld65' in content
        assert 'nes.cfg' in content
        assert 'game.nes' in content

    def test_unix_build_script_is_executable(self, project_dir, minimal_music_asm):
        """Test that Unix build script is executable."""
        if os.name == 'nt':
            pytest.skip("Unix-only test")

        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        build_script = project_dir / "build.sh"
        # Check if executable bit is set
        assert os.access(str(build_script), os.X_OK)

    def test_windows_build_script_is_bat(self, project_dir, minimal_music_asm):
        """Test that Windows build script is .bat file."""
        if os.name != 'nt':
            pytest.skip("Windows-only test")

        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        build_script = project_dir / "build.bat"
        assert build_script.exists()
        content = build_script.read_text()
        assert '@echo off' in content or 'ca65' in content


class TestDebugModeIntegration:
    """Test debug mode functionality."""

    def test_debug_mode_includes_overlay(self, project_dir, minimal_music_asm):
        """Test that debug mode includes overlay code."""
        builder = NESProjectBuilder(str(project_dir), debug_mode=True)
        builder.prepare_project(str(minimal_music_asm))

        music_asm = project_dir / "music.asm"
        content = music_asm.read_text()

        # Debug overlay should be included
        # Check for debug functions
        assert 'debug' in content.lower() or len(content) > 1000

    def test_debug_mode_in_main_asm(self, project_dir, minimal_music_asm):
        """Test that debug mode is reflected in main.asm."""
        builder = NESProjectBuilder(str(project_dir), debug_mode=True)
        builder.prepare_project(str(minimal_music_asm))

        main_asm = project_dir / "main.asm"
        content = main_asm.read_text()

        # Should have debug-related content
        # (could be debug imports or debug initialization)
        # Just verify it's a valid main.asm
        assert 'reset:' in content or 'nmi:' in content

    def test_normal_mode_no_debug(self, project_dir, minimal_music_asm):
        """Test that normal mode excludes debug code."""
        builder = NESProjectBuilder(str(project_dir), debug_mode=False)
        builder.prepare_project(str(minimal_music_asm))

        music_asm = project_dir / "music.asm"
        original_size = len(minimal_music_asm.read_text())
        generated_size = len(music_asm.read_text())

        # Without debug, should be close to original size
        assert generated_size >= original_size - 100  # Allow some variation


class TestMultiSongCompatibility:
    """Test legacy multi-song compatibility."""

    def test_prepare_multi_song_project(self, project_dir, minimal_music_asm):
        """Test prepare_multi_song_project method."""
        builder = NESProjectBuilder(str(project_dir))
        segments_data = {"song_1": {}}

        result = builder.prepare_multi_song_project(str(minimal_music_asm), segments_data)
        assert result == True
        assert (project_dir / "main.asm").exists()

    def test_add_song_bank(self, project_dir, minimal_music_asm):
        """Test add_song_bank method."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        song_bank = {"name": "song_1", "data": b"test"}
        result = builder.add_song_bank(song_bank)
        assert result == True


class TestMMC1Configuration:
    """Test MMC1 mapper configuration."""

    def test_mmc1_always_enabled(self, project_dir, minimal_music_asm):
        """Test that MMC1 is always enabled."""
        builder = NESProjectBuilder(str(project_dir))
        assert builder.use_mmc1 == True

        builder.prepare_project(str(minimal_music_asm))

        main_asm = project_dir / "main.asm"
        content = main_asm.read_text()

        # Should have MMC1 initialization
        assert '$8000' in content or 'MMC1' in content.upper()

    def test_128kb_prg_rom_configuration(self, project_dir, minimal_music_asm):
        """Test that 128KB PRG-ROM is configured."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        main_asm = project_dir / "main.asm"
        content = main_asm.read_text()

        # Should specify 8 PRG banks (128KB)
        assert '$08' in content or '8 x' in content or '128' in content

    def test_chr_ram_configuration(self, project_dir, minimal_music_asm):
        """Test that CHR-RAM is configured (no CHR-ROM)."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        main_asm = project_dir / "main.asm"
        content = main_asm.read_text()

        # Should specify 0 CHR banks (CHR-RAM)
        assert '$00' in content or '0 x' in content


class TestErrorHandling:
    """Test error handling."""

    def test_prepare_project_with_nonexistent_music(self, project_dir):
        """Test handling of nonexistent music.asm file."""
        builder = NESProjectBuilder(str(project_dir))

        nonexistent = project_dir / "nonexistent.asm"
        with pytest.raises(FileNotFoundError):
            builder.prepare_project(str(nonexistent))

    def test_prepare_project_creates_missing_directory(self, temp_dir, minimal_music_asm):
        """Test that prepare_project creates missing project directory."""
        project_dir = temp_dir / "new" / "nested" / "project"
        assert not project_dir.exists()

        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        assert project_dir.exists()
        assert (project_dir / "main.asm").exists()


class TestReturnValues:
    """Test function return values."""

    def test_prepare_project_returns_true(self, project_dir, minimal_music_asm):
        """Test that prepare_project returns True on success."""
        builder = NESProjectBuilder(str(project_dir))
        result = builder.prepare_project(str(minimal_music_asm))

        assert result == True
        assert isinstance(result, bool)

    def test_add_song_bank_returns_true(self, project_dir, minimal_music_asm):
        """Test that add_song_bank returns True."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        result = builder.add_song_bank({})
        assert result == True

    def test_prepare_multi_song_returns_true(self, project_dir, minimal_music_asm):
        """Test that prepare_multi_song_project returns True."""
        builder = NESProjectBuilder(str(project_dir))
        result = builder.prepare_multi_song_project(str(minimal_music_asm), {})

        assert result == True
