"""Tests for nes/visualizer.py (--visualizer on-screen volume-bar UI).

Pytest markers:
- @pytest.mark.slow / @pytest.mark.requires_cc65 - real ca65/ld65 compile
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from nes.visualizer import (
    NESVisualizer,
    generate_chr_tiles,
    NUM_TILES,
    NUM_CHANNELS,
)


class TestChrTileData:
    """The 9-tile fill set is the visual contract -- get the pixel data
    wrong and the bars render as noise, not a meter."""

    def test_tile_count_and_size(self):
        data = generate_chr_tiles()
        assert len(data) == NUM_TILES * 16  # 16 bytes/tile (2 bitplanes x 8 rows)

    def test_tile_0_is_fully_empty(self):
        data = generate_chr_tiles()
        tile0 = data[0:16]
        assert tile0 == b"\x00" * 16

    def test_tile_8_is_fully_filled(self):
        data = generate_chr_tiles()
        tile8 = data[8 * 16:9 * 16]
        assert tile8 == b"\xFF" * 16

    def test_both_bitplanes_identical_per_tile(self):
        """Filled pixels must read color index 3 (both planes set), empty
        pixels index 0 (both planes clear) -- a mismatched plane would
        produce stray index 1/2 pixels the palette never defines."""
        data = generate_chr_tiles()
        for t in range(NUM_TILES):
            tile = data[t * 16:(t + 1) * 16]
            plane0, plane1 = tile[:8], tile[8:]
            assert plane0 == plane1

    def test_fill_grows_from_the_bottom(self):
        """Tile N fills the bottom N of its 8 rows -- row 7 (last byte of
        the bitplane) must be the first to become solid as N increases."""
        data = generate_chr_tiles()
        for n in range(NUM_TILES):
            plane0 = data[n * 16: n * 16 + 8]
            filled_rows = sum(1 for b in plane0 if b == 0xFF)
            empty_rows = sum(1 for b in plane0 if b == 0x00)
            assert filled_rows == n
            assert empty_rows == 8 - n
            # bottom `n` rows filled means the tail of the byte sequence is
            # the solid part
            assert plane0[8 - n:] == bytes([0xFF] * n)
            assert plane0[:8 - n] == bytes([0x00] * (8 - n))


class TestVisualizerAsmGeneration:
    """Content-assertion coverage for the generated CA65 source, mirroring
    tests/test_debug_overlay.py's style for the sibling --debug overlay."""

    def test_disabled_visualizer_produces_no_real_code(self):
        vis = NESVisualizer(enable_visualizer=False)
        system = vis.generate_full_visualizer_system()
        assert "visualizer_init:" not in system
        assert "visualizer_update:" not in system

    def test_full_system_has_all_three_parts(self):
        vis = NESVisualizer(enable_visualizer=True)
        system = vis.generate_full_visualizer_system()
        assert "visualizer_chr_tiles:" in system
        assert "visualizer_palette:" in system
        assert "visualizer_init:" in system
        assert "visualizer_update:" in system

    def test_init_does_vblank_wait_chr_upload_and_enables_rendering(self):
        vis = NESVisualizer(enable_visualizer=True)
        init = vis.generate_visualizer_init()
        # 2x vblank wait via $2002 bit 7 -- currently absent anywhere else
        # in the repo; needed now that real rendering is being turned on.
        assert init.count("bit $2002") >= 2
        # CHR-RAM tile upload (144 = 9 tiles x 16 bytes)
        assert "visualizer_chr_tiles" in init
        assert "cpy #144" in init
        # Palette init
        assert "visualizer_palette" in init
        assert "cpy #16" in init
        # PPUMASK enable -- the first write of $2001 anywhere in the repo
        assert "sta $2001" in init

    def test_update_reads_channel_vis_vol_for_all_four_channels(self):
        vis = NESVisualizer(enable_visualizer=True)
        update = vis.generate_visualizer_update()
        assert "visualizer_update:" in update
        assert "VIS_DRAW_BAR" in update
        # The macro body indexes channel_vis_vol by its chan_off parameter
        # (not a literal per channel); each channel gets its own call site.
        assert "channel_vis_vol+chan_off" in update
        for i in range(NUM_CHANNELS):
            assert f"VIS_DRAW_BAR {i}," in update
        # Never reads the APU back -- only ever writes channel_vis_vol.
        assert "$4015" not in update
        assert "$4000" not in update

    def test_chr_upload_byte_table_matches_generate_chr_tiles(self):
        vis = NESVisualizer(enable_visualizer=True)
        data_asm = vis.generate_visualizer_data()
        tiles = generate_chr_tiles()
        # Spot check: the first and last byte of the table appear literally.
        assert f"${tiles[0]:02X}" in data_asm or "$00" in data_asm
        assert f"${tiles[-1]:02X}" in data_asm


class TestNESVisualizerCompileSmoke:
    """Real ca65/ld65 compile of both export paths with --visualizer,
    exercising all 4 non-DPCM channels through both the "write" and
    "@silence" code paths this feature added. 6502 asm correctness can't be
    verified any other way."""

    # Synthetic frames: each channel goes note-on (frame 0) -> silence
    # (frame 1 or 2), so both the hardware-write and @silence snapshot
    # stores added by this feature get assembled and linked.
    FRAMES = {
        "pulse1": {
            "0": {"pitch": 100, "control": 0x30 | 10, "note": 60, "volume": 10},
            "1": {"pitch": 100, "control": 0x30 | 10, "note": 60, "volume": 10},
            "2": {"pitch": 0, "control": 0x30, "note": 0, "volume": 0},
        },
        "pulse2": {
            "0": {"pitch": 90, "control": 0x30 | 8, "note": 55, "volume": 8},
            "1": {"pitch": 0, "control": 0x30, "note": 0, "volume": 0},
        },
        "triangle": {
            "0": {"pitch": 80, "volume": 15, "note": 50},
            "1": {"pitch": 0, "volume": 0, "note": 0},
        },
        "noise": {
            "0": {"note": 5, "control": 0x30 | 12, "volume": 12},
            "1": {"note": 0, "control": 0x30, "volume": 0},
        },
    }

    @pytest.mark.slow
    @pytest.mark.requires_cc65
    def test_direct_export_visualizer_compiles(self, temp_dir):
        from exporter.exporter_ca65 import CA65Exporter
        from nes.project_builder import NESProjectBuilder
        from compiler.compiler import compile_rom
        from mappers.mmc3 import MMC3Mapper

        music_asm = temp_dir / "music.asm"
        mapper = MMC3Mapper()
        CA65Exporter().export_direct_frames(
            self.FRAMES, str(music_asm), standalone=False, mapper=mapper, visualizer=True)

        project_path = temp_dir / "nes_project"
        builder = NESProjectBuilder(str(project_path), mapper=mapper, visualizer_mode=True)
        assert builder.prepare_project(str(music_asm))

        out_rom = temp_dir / "out.nes"
        assert compile_rom(project_path, out_rom), \
            "direct-export --visualizer build failed to compile/link"
        assert out_rom.exists()

    @pytest.mark.slow
    @pytest.mark.requires_cc65
    def test_bytecode_export_visualizer_compiles(self, temp_dir):
        from exporter.exporter_ca65 import CA65Exporter
        from nes.project_builder import NESProjectBuilder
        from compiler.compiler import compile_rom
        from mappers.mmc3 import MMC3Mapper

        music_asm = temp_dir / "music.asm"
        mapper = MMC3Mapper()
        # `patterns` truthiness alone selects the bytecode branch --
        # export_tables_with_patterns's docstring; contents are irrelevant.
        patterns = {"p0": {"events": [{"frame": 0, "note": 60, "volume": 10}]}}
        references = {"pulse1": [{"start_frame": 0, "pattern_id": "p0", "length": 1}]}
        CA65Exporter().export_tables_with_patterns(
            self.FRAMES, patterns, references, str(music_asm),
            standalone=False, mapper=mapper)
        assert "MMC3 Macro Bytecode" in music_asm.read_text()

        project_path = temp_dir / "nes_project"
        builder = NESProjectBuilder(str(project_path), mapper=mapper, visualizer_mode=True)
        assert builder.prepare_project(str(music_asm))
        main_asm = (project_path / "main.asm").read_text()
        assert "VISUALIZER_BUILD = 1" in main_asm

        out_rom = temp_dir / "out.nes"
        assert compile_rom(project_path, out_rom), \
            "bytecode --visualizer build failed to compile/link"
        assert out_rom.exists()

    @pytest.mark.slow
    @pytest.mark.requires_cc65
    def test_visualizer_off_is_unaffected(self, temp_dir):
        """Zero-cost-when-unused: a normal (non-visualizer) build must still
        compile/link fine -- VISUALIZER_BUILD-gated code must not leak out
        when visualizer_mode is False."""
        from exporter.exporter_ca65 import CA65Exporter
        from nes.project_builder import NESProjectBuilder
        from compiler.compiler import compile_rom
        from mappers.mmc3 import MMC3Mapper

        music_asm = temp_dir / "music.asm"
        mapper = MMC3Mapper()
        patterns = {"p0": {"events": [{"frame": 0, "note": 60, "volume": 10}]}}
        references = {"pulse1": [{"start_frame": 0, "pattern_id": "p0", "length": 1}]}
        CA65Exporter().export_tables_with_patterns(
            self.FRAMES, patterns, references, str(music_asm),
            standalone=False, mapper=mapper)

        project_path = temp_dir / "nes_project"
        builder = NESProjectBuilder(str(project_path), mapper=mapper)  # visualizer_mode=False
        assert builder.prepare_project(str(music_asm))
        main_asm = (project_path / "main.asm").read_text()
        assert "VISUALIZER_BUILD" not in main_asm
        assert "channel_vis_vol" not in main_asm

        out_rom = temp_dir / "out.nes"
        assert compile_rom(project_path, out_rom)
        assert out_rom.exists()
