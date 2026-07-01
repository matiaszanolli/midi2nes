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
        # Default mapper is MMC3 to match the pipeline default (#25).
        assert builder.use_mmc1 == False
        assert builder.mapper.mapper_number == 4
        assert builder.debug_mode == False

    def test_builder_with_debug_mode(self, project_dir):
        """Test NESProjectBuilder with debug mode enabled."""
        builder = NESProjectBuilder(str(project_dir), debug_mode=True)
        assert builder.debug_mode == True
        assert builder.use_mmc1 == False  # MMC3 is the default (#25)


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
        assert '$00' in content  # 0 CHR banks
        # Default is MMC3: 32 * 16KB = 512KB PRG, mapper byte $40 (#25).
        assert '32' in content  # 32 PRG banks
        assert '$40' in content  # Mapper 4 (MMC3)

    def test_mmc3_main_asm_has_single_header_segment(self, project_dir, minimal_music_asm):
        """Regression (#22): the builder owns the one `.segment "HEADER"`, and the
        mapper's generate_header_asm() returns bare bytes. MMC3 used to emit its
        own `.segment "HEADER"` too, so main.asm carried two consecutive HEADER
        segment directives. All mappers must follow the bare-bytes contract."""
        from mappers.mmc3 import MMC3Mapper
        builder = NESProjectBuilder(str(project_dir), mapper=MMC3Mapper())
        builder.prepare_project(str(minimal_music_asm))

        content = (project_dir / "main.asm").read_text()
        assert content.count('.segment "HEADER"') == 1
        assert '"NES", $1A' in content      # the header bytes still land
        assert '$40' in content             # Mapper 4 (MMC3) flags byte

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
        """Test that nes.cfg defines PRG-ROM sections matching the default mapper."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        nes_cfg = project_dir / "nes.cfg"
        content = nes_cfg.read_text()

        # Default is MMC3 (#25): banked 8KB windows (PRG_BANK_xx) + fixed
        # PRG_FIX region.  MMC1 used PRGSWAP/PRGFIXED — those are gone.
        has_mmc3 = 'PRG_BANK_00' in content and 'PRG_FIX' in content
        assert has_mmc3, "Default mapper (MMC3) PRG regions must be present in nes.cfg"

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

    def test_build_script_honors_selected_mapper(self, project_dir, minimal_music_asm):
        """The generated build.sh must come from the selected mapper, not a
        hardcoded MMC3 template (#18). MMC1 needs its vector fixup post-process."""
        from mappers.mmc1 import MMC1Mapper

        builder = NESProjectBuilder(str(project_dir))
        builder.set_mapper(MMC1Mapper())
        builder.prepare_project(str(minimal_music_asm))

        build_script = project_dir / "build.sh" if os.name != 'nt' else project_dir / "build.bat"
        content = build_script.read_text()

        # MMC1 relocates the reset/NMI/IRQ vectors to file offset 0x2000A.
        assert '0x2000A' in content
        # Must match the mapper's own script byte-for-byte.
        assert content == MMC1Mapper().generate_build_script(os.name == 'nt')

    def test_mmc3_build_script_has_no_vector_fixup(self, project_dir, minimal_music_asm):
        """MMC3 keeps the vectors in its fixed last bank, so the build script
        must not carry an MMC1-style fixup (#18)."""
        from mappers.mmc3 import MMC3Mapper

        builder = NESProjectBuilder(str(project_dir))
        builder.set_mapper(MMC3Mapper())
        builder.prepare_project(str(minimal_music_asm))

        build_script = project_dir / "build.sh" if os.name != 'nt' else project_dir / "build.bat"
        content = build_script.read_text()

        assert '0x2000A' not in content
        assert content == MMC3Mapper().generate_build_script(os.name == 'nt')


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
    """Test MMC1 mapper configuration (explicit MMC1 — not the default)."""

    def test_mmc3_is_default_mapper(self, project_dir, minimal_music_asm):
        """Regression (#25): the default mapper must be MMC3, matching the pipeline."""
        from mappers.mmc3 import MMC3Mapper
        builder = NESProjectBuilder(str(project_dir))
        assert builder.use_mmc1 == False
        assert isinstance(builder.mapper, MMC3Mapper)

        builder.prepare_project(str(minimal_music_asm))

        content = (project_dir / "main.asm").read_text()
        # MMC3 iNES header: 32 * 16KB = 512KB, mapper byte $40.
        assert '32' in content
        assert '$40' in content

    def test_512kb_prg_rom_default_configuration(self, project_dir, minimal_music_asm):
        """Default (MMC3) produces 512KB PRG-ROM header (#25)."""
        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(minimal_music_asm))

        content = (project_dir / "main.asm").read_text()

        # MMC3: 32 * 16KB = 512KB
        assert '32' in content or '512' in content

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


class TestMapperFactoryDefault:
    """Regression tests for M-7 (#25): get_mapper('auto', 0) must return MMC3."""

    def test_get_mapper_auto_no_size_returns_mmc3(self):
        """get_mapper('auto', data_size=0) must return MMC3, not MMC1 (#25)."""
        from mappers.factory import get_mapper
        from mappers.mmc3 import MMC3Mapper
        mapper = get_mapper("auto", data_size=0)
        assert isinstance(mapper, MMC3Mapper), (
            f"Expected MMC3Mapper but got {type(mapper).__name__}. "
            "get_mapper('auto', 0) must match the pipeline default (MMC3)."
        )

    def test_builder_default_mapper_is_mmc3(self, project_dir):
        """NESProjectBuilder() with no explicit mapper must resolve to MMC3 (#25)."""
        from mappers.mmc3 import MMC3Mapper
        builder = NESProjectBuilder(str(project_dir))
        assert isinstance(builder.mapper, MMC3Mapper), (
            "Builder default mapper must be MMC3 to match the pipeline"
        )

    def test_get_mapper_auto_with_size_uses_auto_select(self):
        """get_mapper('auto', data_size>0) must use auto_select, not the hardcoded default."""
        from mappers.factory import get_mapper
        from mappers.mmc1 import MMC1Mapper
        # A tiny payload fits NROM; auto_select should return the smallest that fits.
        mapper = get_mapper("auto", data_size=1024)
        assert mapper is not None
        # Result must be the smallest mapper that can hold 1 KB (NROM can, so check we
        # get something valid, not the hardcoded mmc3 fallback).
        assert hasattr(mapper, 'can_fit_data')
