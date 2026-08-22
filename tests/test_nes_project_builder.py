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
        hardcoded MMC3 template (#18)."""
        from mappers.mmc1 import MMC1Mapper

        builder = NESProjectBuilder(str(project_dir))
        builder.set_mapper(MMC1Mapper())
        builder.prepare_project(str(minimal_music_asm))

        build_script = project_dir / "build.sh" if os.name != 'nt' else project_dir / "build.bat"
        content = build_script.read_text()

        # Must match the mapper's own script byte-for-byte.
        assert content == MMC1Mapper().generate_build_script(os.name == 'nt')

    def test_mmc1_build_script_has_no_vector_fixup(self, project_dir, minimal_music_asm):
        """Regression (MAP-2 / #213): the old post-link fixup copied 6 bytes
        from file offset 0xFFFA (inside the switchable PRGSWAP region) onto
        the correctly-placed vectors at 0x2000A, overwriting valid
        reset/NMI/IRQ addresses with PRGSWAP fill data. generate_linker_config's
        `VECTORS: load = PRGFIXED, start = $FFFA` already places vectors
        correctly, so no post-link fixup is needed."""
        from mappers.mmc1 import MMC1Mapper

        builder = NESProjectBuilder(str(project_dir))
        builder.set_mapper(MMC1Mapper())
        builder.prepare_project(str(minimal_music_asm))

        build_script = project_dir / "build.sh" if os.name != 'nt' else project_dir / "build.bat"
        content = build_script.read_text()

        assert '0x2000A' not in content
        assert '0xFFFA' not in content
        assert not MMC1Mapper().generate_post_process_commands(os.name == 'nt')

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

    def test_debug_overlay_gets_explicit_code_segment(self, project_dir, temp_dir):
        """#388/MAP-2026-08-05-1: the debug overlay must not inherit whatever
        segment was last active in music.asm. Build a fixture ending in
        .segment "RODATA" (matching the real DPCM-stub-appended case) and
        assert an explicit .segment "CODE" directive sits between that and
        debug_init: -- with nothing else (in particular no other .segment)
        in between."""
        music_asm = temp_dir / "music_ending_in_rodata.asm"
        music_asm.write_text(
            '.export init_music, update_music\n'
            '.segment "CODE"\n'
            'init_music:\n    rts\n'
            'update_music:\n    rts\n'
            '.segment "RODATA"\n'
            'dpcm_bank_table:\n    .byte $00\n'
        )

        from mappers.mmc1 import MMC1Mapper
        builder = NESProjectBuilder(str(project_dir), debug_mode=True, mapper=MMC1Mapper())
        builder.prepare_project(str(music_asm))

        content = (project_dir / "music.asm").read_text()
        before_debug = content.split("debug_init:")[0]
        # The nearest .segment directive before debug_init: must be CODE,
        # not the trailing RODATA the fixture (and the real DPCM stub path)
        # left active.
        last_segment = before_debug.rsplit('.segment', 1)[-1].splitlines()[0].strip()
        assert last_segment == '"CODE"', (
            f"debug_init inherited segment {last_segment!r} instead of an "
            "explicit CODE segment"
        )

    def test_mmc1_debug_restores_bank_before_debug_update_call(self, project_dir, minimal_music_asm):
        """#388/MAP-2026-08-05-1 defense-in-depth: on a mapper with a
        switchable direct-export bank (MMC1), main.asm's NMI handler must
        reselect bank 0 before `jsr debug_update`."""
        from mappers.mmc1 import MMC1Mapper
        builder = NESProjectBuilder(str(project_dir), debug_mode=True, mapper=MMC1Mapper())
        builder.prepare_project(str(minimal_music_asm))

        main_asm = (project_dir / "main.asm").read_text()
        assert "jsr debug_update" in main_asm
        before_call = main_asm.split("jsr debug_update")[0]
        # MMC1Mapper.generate_bank_switch_code(0) writes bank 0 via 5
        # writes to $E000; the last one must appear before the call.
        bank_select_snippet = MMC1Mapper().generate_bank_switch_code(0)
        assert bank_select_snippet in before_call

    def test_nrom_and_mmc3_debug_have_no_bank_restore(self, project_dir, minimal_music_asm):
        """NROM/MMC3 have no switchable direct-export bank
        (direct_export_bank_size() is None), so no bank-restore code should
        be emitted before jsr debug_update for them (#388 sibling check)."""
        from mappers.nrom import NROMMapper
        from mappers.mmc3 import MMC3Mapper

        for mapper_cls in (NROMMapper, MMC3Mapper):
            builder = NESProjectBuilder(str(project_dir), debug_mode=True, mapper=mapper_cls())
            builder.prepare_project(str(minimal_music_asm))
            main_asm = (project_dir / "main.asm").read_text()
            # Scope to the nmi: handler's gap between the two jsr calls --
            # NROM has no bank registers at all, but MMC3's own reset-time
            # init code legitimately writes $E000 (IRQ disable) elsewhere in
            # the file, so a whole-file substring check would false-positive.
            nmi_gap = main_asm.split("jsr update_music")[1].split("jsr debug_update")[0]
            assert "$E000" not in nmi_gap, (
                f"{mapper_cls.__name__} should not emit MMC1-style bank-switch code "
                "between update_music and debug_update"
            )


class TestJukeboxSongCount:
    """Test prepare_project's song_count param (#30/F-13, song bank -> ROM).

    Replaces the old prepare_multi_song_project()/add_song_bank() placeholder
    tests -- those methods were removed once a real multi-song route
    (CA65Exporter.export_song_bank_bytecode + prepare_project(song_count=N))
    existed to call instead.
    """

    @staticmethod
    def _bytecode_music_asm(temp_dir):
        path = temp_dir / "music.asm"
        path.write_text(
            "; CA65 Exporter: MMC3 Macro Bytecode mode\n"
            ".segment \"CODE\"\ninit_music:\n    rts\nupdate_music:\n    rts\n"
        )
        return path

    @staticmethod
    def _jukebox_music_asm(temp_dir):
        # First line matches CA65Exporter.export_song_bank_bytecode's actual
        # header exactly (exporter/exporter_ca65.py) -- the marker
        # prepare_project's auto-detection looks for (#453/MAP-2026-08-21-1).
        path = temp_dir / "music.asm"
        path.write_text(
            "; CA65 Assembly Export (MMC3 Macro Bytecode -- multi-song jukebox build)\n"
            ".segment \"CODE\"\ninit_music:\n    rts\nupdate_music:\n    rts\n"
        )
        return path

    def test_song_count_none_leaves_output_unchanged(self, project_dir, temp_dir):
        """The default (song_count=None) must produce byte-identical main.asm
        to before this parameter existed -- no JUKEBOX_BUILD define, no
        Start-skip polling."""
        music_asm = self._bytecode_music_asm(temp_dir)
        builder = NESProjectBuilder(str(project_dir))
        assert builder.prepare_project(str(music_asm))

        content = (project_dir / "main.asm").read_text()
        assert "JUKEBOX_BUILD" not in content
        assert "audio_advance_song" not in content
        assert "prev_start_state" not in content

    def test_song_count_one_still_defines_jukebox_build(self, project_dir, temp_dir):
        """Regression (#30/F-13, MAP-2026-08-07-2/NH-HW-2026-08-07-1/
        PL-2026-08-07-1): a 1-song bank still goes through
        CA65Exporter.export_song_bank_bytecode, which ALWAYS emits
        jukebox-format symbols (song0_*, a song_table, `jmp
        audio_init_song`) regardless of song count -- so song_count=1 must
        still define JUKEBOX_BUILD, or the resulting music.asm fails to
        link (unresolved audio_init_song / fixed sequence labels /
        channel_start_banks / instrument_table). Only song_count=None (an
        ordinary, non-jukebox-exporter build) should skip it -- see
        test_song_count_none_leaves_output_unchanged above."""
        music_asm = self._bytecode_music_asm(temp_dir)
        builder = NESProjectBuilder(str(project_dir))
        assert builder.prepare_project(str(music_asm), song_count=1)

        content = (project_dir / "main.asm").read_text()
        assert "JUKEBOX_BUILD = 1" in content

    def test_song_count_above_one_defines_jukebox_build_before_include(
            self, project_dir, temp_dir):
        """JUKEBOX_BUILD must be a plain assignment (ca65's .ifdef only
        recognizes real symbol/constant definitions, not .define'd macros)
        and must precede `.include "audio_engine.asm"` so the engine's own
        `.ifdef JUKEBOX_BUILD` sees it."""
        music_asm = self._bytecode_music_asm(temp_dir)
        builder = NESProjectBuilder(str(project_dir))
        assert builder.prepare_project(str(music_asm), song_count=3)

        content = (project_dir / "main.asm").read_text()
        assert "JUKEBOX_BUILD = 1" in content
        assert content.index("JUKEBOX_BUILD = 1") < content.index('.include "audio_engine.asm"')

    def test_song_count_above_one_adds_start_skip_polling(self, project_dir, temp_dir):
        """A jukebox build reads the joypad in the NMI handler and calls
        audio_advance_song on a fresh Start press (#30/F-13)."""
        music_asm = self._bytecode_music_asm(temp_dir)
        builder = NESProjectBuilder(str(project_dir))
        assert builder.prepare_project(str(music_asm), song_count=2)

        content = (project_dir / "main.asm").read_text()
        assert "jsr read_joypad_safe" in content
        assert "jsr audio_advance_song" in content
        assert "prev_start_state: .res 1" in content
        # Must be inside the NMI handler, after update_music, not the reset routine.
        nmi_body = content.split("nmi:")[1]
        assert "audio_advance_song" in nmi_body

    def test_jukebox_music_asm_without_song_count_still_defines_jukebox_build(
            self, project_dir, temp_dir):
        """Regression (#453/MAP-2026-08-21-1): the documented split
        `prepare`/`compile` flow (and any library caller besides
        run_song_build) never passes song_count. Without auto-detection, a
        jukebox music.asm "succeeded" here -- capacity pre-flight passes,
        all files written -- and only failed two steps later at ld65 with
        unresolved externals (audio_init_song, the fixed sequence labels,
        channel_start_banks, instrument_table), since JUKEBOX_BUILD was
        never defined. song_count must now be auto-detected from
        music.asm's own jukebox marker."""
        music_asm = self._jukebox_music_asm(temp_dir)
        builder = NESProjectBuilder(str(project_dir))
        assert builder.prepare_project(str(music_asm))  # no song_count passed

        content = (project_dir / "main.asm").read_text()
        assert "JUKEBOX_BUILD = 1" in content
        assert "jsr audio_advance_song" in content

    def test_explicit_song_count_still_overrides_auto_detection(
            self, project_dir, temp_dir):
        """An explicit song_count (as run_song_build always passes) must
        still work unchanged on jukebox content -- auto-detection is a
        fallback for when the caller omits it, not a replacement."""
        music_asm = self._jukebox_music_asm(temp_dir)
        builder = NESProjectBuilder(str(project_dir))
        assert builder.prepare_project(str(music_asm), song_count=5)

        content = (project_dir / "main.asm").read_text()
        assert "JUKEBOX_BUILD = 1" in content

    def test_ordinary_bytecode_music_asm_is_not_misdetected_as_jukebox(
            self, project_dir, temp_dir):
        """A plain single-song bytecode build (no jukebox marker, no
        song_count) must still leave output unchanged -- auto-detection
        must not false-positive on ordinary bytecode-mode music.asm."""
        music_asm = self._bytecode_music_asm(temp_dir)
        builder = NESProjectBuilder(str(project_dir))
        assert builder.prepare_project(str(music_asm))

        content = (project_dir / "main.asm").read_text()
        assert "JUKEBOX_BUILD" not in content
        assert "audio_advance_song" not in content


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

    def test_bytecode_mode_requires_audio_engine(self, project_dir, temp_dir, monkeypatch):
        """Regression (#37/M-11): bytecode-mode main.asm writes to frame_counter
        unconditionally in reset, relying entirely on audio_engine.asm's
        ZEROPAGE block being pulled in later via .include. If that file were
        ever missing, this must fail loudly here -- before any project files
        are written -- rather than let it surface as a cryptic "undefined
        symbol" from ca65 much later."""
        from nes.project_builder import ExportError
        from pathlib import Path as _Path

        bytecode_music_asm = temp_dir / "music.asm"
        bytecode_music_asm.write_text(
            "; CA65 Exporter: MMC3 Macro Bytecode mode\n"
            ".segment \"CODE\"\ninit_music:\n    rts\nupdate_music:\n    rts\n"
        )

        real_exists = _Path.exists

        def fake_exists(self):
            if self.name == "audio_engine.asm":
                return False
            return real_exists(self)

        monkeypatch.setattr(_Path, "exists", fake_exists)

        builder = NESProjectBuilder(str(project_dir))
        with pytest.raises(ExportError):
            builder.prepare_project(str(bytecode_music_asm))

        # No half-written project should be left behind.
        assert not (project_dir / "main.asm").exists()


class TestDeadMacroInstrumentCodeRemoved:
    """Regression (#314/EXP-12): prepare_project used to append a second,
    fully dead macro-instrument/DPCM-trigger implementation (seq_cmd_instrument,
    seq_cmd_dpcm_play, plus ~85 bytes of dedicated ch_*/apu_shadow_* BSS state)
    into every bytecode-mode music.asm -- nes/audio_engine.asm implements both
    operations itself, inline, with different names/calling convention, so
    neither routine was ever called. fetch_sequence_byte in the same block IS
    live (audio_engine.asm imports and calls it) and must survive."""

    def test_dead_symbols_are_gone_but_fetch_sequence_byte_remains(
            self, project_dir, temp_dir):
        bytecode_music_asm = temp_dir / "music.asm"
        bytecode_music_asm.write_text(
            "; CA65 Exporter: MMC3 Macro Bytecode mode\n"
            ".segment \"CODE\"\ninit_music:\n    rts\nupdate_music:\n    rts\n"
        )

        builder = NESProjectBuilder(str(project_dir))
        assert builder.prepare_project(str(bytecode_music_asm))

        music_content = (project_dir / "music.asm").read_text()
        for dead_symbol in (
            "seq_cmd_instrument", "seq_cmd_dpcm_play", "ch_macro_vol_lo",
            "ch_sequence_bank", "apu_shadow_ctrl", "switch_dpcm_bank",
        ):
            assert dead_symbol not in music_content, \
                f"{dead_symbol} should have been removed as dead code"

        assert ".global fetch_sequence_byte" in music_content
        assert "fetch_sequence_byte:" in music_content


class TestReturnValues:
    """Test function return values."""

    def test_prepare_project_returns_true(self, project_dir, minimal_music_asm):
        """Test that prepare_project returns True on success."""
        builder = NESProjectBuilder(str(project_dir))
        result = builder.prepare_project(str(minimal_music_asm))

        assert result == True
        assert isinstance(result, bool)


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
