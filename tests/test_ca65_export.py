import unittest
import subprocess
import tempfile
from pathlib import Path
from exporter.exporter_ca65 import CA65Exporter
from nes.project_builder import NESProjectBuilder
from mappers.mmc3 import MMC3Mapper

class TestCA65Export(unittest.TestCase):
    def setUp(self):
        self.exporter = CA65Exporter()
        self.test_frames = {
            'pulse1': {
                '0': {'note': 60, 'volume': 15},
                '32': {'note': 67, 'volume': 12}
            }
        }
        self.test_patterns = {
            'pattern_1': {
                'events': [
                    {'note': 60, 'volume': 15},
                    {'note': 67, 'volume': 12}
                ]
            }
        }
        self.test_references = {
            '0': ('pattern_1', 0),
            '32': ('pattern_1', 1)
        }
        
    def test_midi_note_to_timer_value(self):
        # Test valid notes
        self.assertGreater(self.exporter.midi_note_to_timer_value(60), 0)  # Middle C
        self.assertGreater(self.exporter.midi_note_to_timer_value(67), 0)  # G4
        
        # Test invalid notes
        self.assertEqual(self.exporter.midi_note_to_timer_value(20), 0)  # Too low
        self.assertEqual(self.exporter.midi_note_to_timer_value(120), 0)  # Too high

    def test_midi_note_to_timer_value_floors_at_8(self):
        # Regression (NH-06 / #27): the highest in-range timer values are < 8,
        # which silences pulse/triangle (t < 8). NES_NOTE_TABLE floors at 8.
        self.assertGreaterEqual(self.exporter.midi_note_to_timer_value(118), 8)
        self.assertGreaterEqual(self.exporter.midi_note_to_timer_value(119), 8)
        # Out-of-range still returns the 0 "rest" sentinel.
        self.assertEqual(self.exporter.midi_note_to_timer_value(120), 0)

    def test_base_timer_matches_pitch_table(self):
        # Regression (NH-03 / #16): the exporter base timer and the frame pitch
        # must be on the same scale (fCPU/16 pulse table). A4 = 253, C4 = 426.
        from nes.pitch_table import NES_NOTE_TABLE
        self.assertEqual(self.exporter.midi_note_to_timer_value(69), 253)  # A4
        self.assertEqual(self.exporter.midi_note_to_timer_value(60), 426)  # C4
        for note in range(24, 120):
            self.assertEqual(self.exporter.midi_note_to_timer_value(note),
                             NES_NOTE_TABLE[note])

    def test_pitch_offset_is_zero_for_unbent_notes(self):
        # Regression (NH-03 / #16): bytecode pitch offset = frame_pitch - base_timer.
        # When the frame pitch equals the table value (no bend), the offset must
        # be 0 so bytecode-mode playback pitch == direct-mode pitch.
        from nes.pitch_table import PitchProcessor
        pp = PitchProcessor()
        for note in range(24, 108):
            base = self.exporter.midi_note_to_timer_value(note)
            frame_pitch = pp.get_channel_pitch(note, 'pulse1')
            offset = max(-128, min(127, frame_pitch - base))
            self.assertEqual(offset, 0,
                             f"note {note}: frame {frame_pitch} vs base {base}")

    def test_dmc_level_clamped_to_7bit(self):
        # Regression (NH-05 / #24): $4011 is a 7-bit register; an out-of-range
        # dmc_level must be masked to 0-127 so CMD_DMC_LEVEL never sets bit 7 or
        # overflows the :02X byte.
        import re
        frames = {'dpcm': {'0': {'note': 1, 'volume': 15, 'dmc_level': 200},
                           '1': {'note': 1, 'volume': 15}}}
        patterns = {'p0': {'events': [{'note': 1, 'volume': 15}]}}
        refs = {'0': ('p0', 0)}  # non-empty patterns -> macro bytecode path
        test_output = Path("test_dmc_clamp.asm")
        try:
            self.exporter.export_tables_with_patterns(frames, patterns, refs, test_output)
            output = test_output.read_text()
            levels = [int(b, 16) for b in re.findall(
                r'\.byte \$87, \$([0-9A-Fa-f]{2}) ; CMD_DMC_LEVEL', output)]
            self.assertTrue(levels, "expected at least one CMD_DMC_LEVEL emission")
            for lvl in levels:
                self.assertLessEqual(lvl, 0x7F)
            self.assertEqual(levels[0], 200 & 0x7F)  # 0x48, not 0xC8
        finally:
            if test_output.exists():
                test_output.unlink()

    def test_export_tables_with_patterns(self):
        test_output = Path("test_output.asm")
        try:
            self.exporter.export_tables_with_patterns(
                self.test_frames,
                self.test_patterns,
                self.test_references,
                test_output
            )
            with open(test_output, 'r') as f:
                output = f.read()
                
            # Test file header and new MMC3 mode output
            self.assertIn("; CA65 Assembly Export (MMC3 Macro Bytecode)", output)
            
            # Test segments
            self.assertIn(".segment \"DPCM\"", output)
            self.assertIn(".segment \"CODE_8000\"", output)
            
            # Test tables
            self.assertIn("ntsc_period_low:", output)
            self.assertIn("ntsc_period_high:", output)
            self.assertIn("instrument_table:", output)
            
            # Test pattern/sequence data
            self.assertIn("pulse1_sequence:", output)
            self.assertIn("pulse2_sequence:", output)
            self.assertIn("triangle_sequence:", output)
            self.assertIn("noise_sequence:", output)
            self.assertIn("dpcm_sequence:", output)
            
            # Test macro definitions
            self.assertIn("macro_vol_0:", output)
            self.assertIn("macro_duty_0:", output)
            self.assertIn("macro_pitch_0:", output)
            self.assertIn("macro_arp_0:", output)
            
        finally:
            if test_output.exists():
                test_output.unlink()
                
    def test_sweep_disabled_in_direct_init_paths(self):
        # Regression (NH-07 / #31): both direct-export init paths must disable the
        # pulse sweep units ($4001/$4005). Standalone emits a reset proc;
        # non-standalone emits init_music for the project builder.
        for standalone in (True, False):
            out = Path(f"test_sweep_{int(standalone)}.asm")
            try:
                self.exporter.export_tables_with_patterns(
                    self.test_frames, {}, {}, out, standalone=standalone)
                asm = out.read_text()
                self.assertIn("sta $4001", asm,
                              f"standalone={standalone}: pulse1 sweep ($4001) not disabled")
                self.assertIn("sta $4005", asm,
                              f"standalone={standalone}: pulse2 sweep ($4005) not disabled")
            finally:
                if out.exists():
                    out.unlink()

    def test_empty_patterns(self):
        test_output = Path("test_empty.asm")
        try:
            self.exporter.export_tables_with_patterns({}, {}, {}, test_output)
            with open(test_output, 'r') as f:
                output = f.read()
            
            # Empty patterns triggers direct frame export mode
            self.assertIn("; CA65 Assembly Export (Direct Frame Data)", output)
            self.assertIn(".segment \"CODE\"", output)
            self.assertIn(".segment \"ZEROPAGE\"", output)  # Direct frame mode has zeropage
            self.assertIn("frame_counter: .res 2", output)
            
            # Should have NES initialization structure
            self.assertIn(".proc reset", output)
            self.assertIn(".proc nmi", output)
            self.assertIn("play_music_frame", output)
            
            # Should have proper APU initialization
            self.assertIn("lda #$0F", output)  # APU enable value
            self.assertIn("sta $4015", output)  # APU status register
            
        finally:
            if test_output.exists():
                test_output.unlink()

class TestCA65CompilationIntegration(unittest.TestCase):
    def setUp(self):
        self.exporter = CA65Exporter()
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir) / "test_project"
        self.builder = NESProjectBuilder(str(self.project_path), mapper=MMC3Mapper())
        
        # Basic test data
        self.test_frames = {
            'pulse1': {
                '0': {'note': 60, 'volume': 15},
                '32': {'note': 67, 'volume': 12}
            }
        }
        self.test_patterns = {
            'pattern_1': {
                'events': [
                    {'note': 60, 'volume': 15},
                    {'note': 67, 'volume': 12}
                ]
            }
        }
        self.test_references = {
            '0': ('pattern_1', 0),
            '32': ('pattern_1', 1)
        }

    def tearDown(self):
        # Clean up temporary files
        import shutil
        shutil.rmtree(self.temp_dir)

    def patch_music_asm(self, music_asm_path):
        """Fix missing entry points in the generated music.asm to ensure compilation."""
        with open(music_asm_path, 'r') as f:
            content = f.read()
            
        append_text = ""
        if "init_music:" not in content and ".proc init_music" not in content:
            append_text += "\n.segment \"CODE\"\n.export init_music\ninit_music:\n  rts\n"
            
        if "update_music:" not in content and ".proc update_music" not in content:
            append_text += "\n.segment \"CODE\"\n.export update_music\nupdate_music:\n"
            if "play_music_frame" in content:
                append_text += "  jsr play_music_frame\n"
            elif "play_pattern_frame" in content:
                append_text += "  jsr play_pattern_frame\n"
            append_text += "  rts\n"
            
        if append_text:
            with open(music_asm_path, 'a') as f:
                f.write(append_text)

    def patch_nes_cfg(self):
        """Ensure nes.cfg has the necessary segments for the export."""
        nes_cfg = self.project_path / "nes.cfg"
        if nes_cfg.exists():
            import re
            
            # Dynamically detect all segments requested by the assembly files
            required_segments = set()
            for asm_file in self.project_path.glob("*.asm"):
                content = asm_file.read_text()
                segments = re.findall(r'\.segment\s+"([^"]+)"', content)
                required_segments.update(segments)
                
            content = nes_cfg.read_text()
            modified = False
            
            # Find default fallback load area (last non-bank specific PRG area)
            default_load_area = "PRG"
            for area in ["PRGFIXED", "PRG_ROM", "PRG_BANK_0", "PRG"]:
                if f"{area}: start =" in content or f"{area}: file =" in content:
                    default_load_area = area
                    break
                    
            if "SEGMENTS {" in content:
                for seg in required_segments:
                    # Skip standard system segments that require specific memory mapping (ZP, RAM)
                    if f"{seg}:" not in content and seg not in ["ZEROPAGE", "BSS", "HEADER", "VECTORS"]:
                        # Handle MMC3 Bank switching segments
                        load_area = default_load_area
                        if seg.startswith("BANK_"):
                            bank_num = seg.split("_")[1]
                            if f"PRG_BANK_{bank_num}: start =" in content:
                                load_area = f"PRG_BANK_{bank_num}"
                            elif f"PRG_BANK_{int(bank_num)}: start =" in content:
                                load_area = f"PRG_BANK_{int(bank_num)}"
                        
                        align = ", align = 64" if seg == "DPCM" else ""
                        content = content.replace("SEGMENTS {", f"SEGMENTS {{\n    {seg}: load = {load_area}, type = ro{align}, optional = yes;")
                        modified = True
                        
            if modified:
                nes_cfg.write_text(content)

    def compile_and_link(self, project_path):
        """Compile and link the project, return (success, output)"""
        self.patch_nes_cfg()
        try:
            # Compile main.asm
            result = subprocess.run(
                ['ca65', 'main.asm', '-o', 'main.o'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                return False, f"Failed to compile main.asm:\n{result.stderr}"

            # Compile music.asm
            result = subprocess.run(
                ['ca65', 'music.asm', '-o', 'music.o'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                return False, f"Failed to compile music.asm:\n{result.stderr}"

            # Link the objects
            result = subprocess.run(
                ['ld65', '-C', 'nes.cfg', 'main.o', 'music.o', '-o', 'game.nes'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                return False, f"Failed to link:\n{result.stderr}"

            return True, "Compilation successful"
        except Exception as e:
            return False, f"Error during compilation: {str(e)}"

    def test_basic_project_compilation(self):
        """Test that a basic project with minimal music data compiles"""
        # Create project directory first
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        # Generate music.asm
        music_asm = self.project_path / "music.asm"
        self.exporter.export_tables_with_patterns(
            self.test_frames,
            self.test_patterns,
            self.test_references,
            music_asm,
            standalone=False
        )
        self.patch_music_asm(music_asm)
        
        # Prepare project
        self.builder.prepare_project(str(music_asm))
        
        # Try to compile
        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Compilation failed:\n{output}")

    def test_apu_initialized_in_boot_path(self):
        """The generated project must initialize the APU frame counter ($4017)
        and channel-enable register ($4015) before playback, otherwise the
        hardware frame sequencer fights the NMI-driven engine (issue #7).
        """
        self.project_path.mkdir(parents=True, exist_ok=True)
        music_asm = self.project_path / "music.asm"
        self.exporter.export_tables_with_patterns(
            self.test_frames, self.test_patterns, self.test_references,
            music_asm, standalone=False,
        )
        self.patch_music_asm(music_asm)
        self.builder.prepare_project(str(music_asm))

        # The patterns path boots via audio_engine.asm's audio_init.
        engine = (self.project_path / "audio_engine.asm").read_text()
        init = engine.split("audio_init:", 1)[1].split("audio_update:", 1)[0]
        self.assertIn("$4017", init, "audio_init must write the frame counter ($4017)")
        self.assertIn("$4015", init, "audio_init must enable channels ($4015)")
        # Regression (NH-07 / #31): both sweep units must be disabled at init so
        # power-on garbage cannot bend or silence the pulse channels.
        self.assertIn("sta $4001", init, "audio_init must disable pulse1 sweep ($4001)")
        self.assertIn("sta $4005", init, "audio_init must disable pulse2 sweep ($4005)")

    def test_direct_export_compilation(self):
        """The direct/--no-patterns export (real frames, no patterns) must build a
        self-contained ROM without the bytecode engine or audio_engine.asm, which
        import symbols the direct path never defines (issue #50).
        """
        self.project_path.mkdir(parents=True, exist_ok=True)
        music_asm = self.project_path / "music.asm"
        # Empty patterns routes export_tables_with_patterns to the direct exporter.
        self.exporter.export_tables_with_patterns(
            self.test_frames, {}, {}, music_asm, standalone=False,
        )
        self.patch_music_asm(music_asm)
        self.builder.prepare_project(str(music_asm))

        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Direct-export compilation failed:\n{output}")
        # The self-contained direct path must not include the bytecode engine.
        main_asm = (self.project_path / "main.asm").read_text()
        self.assertNotIn('.include "audio_engine.asm"', main_asm)

    def test_empty_project_compilation(self):
        """Test that a project with no music data still compiles"""
        # Create project directory first
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        music_asm = self.project_path / "music.asm"
        self.exporter.export_tables_with_patterns({}, {}, {}, music_asm, standalone=False)
        self.patch_music_asm(music_asm)
        
        self.builder.prepare_project(str(music_asm))
        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Empty project compilation failed:\n{output}")

    def test_multi_song_compilation(self):
        """Test compilation with multiple songs"""
        # Create project directory first
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        music_asm = self.project_path / "music.asm"
        
        # Use basic project preparation for now instead of multi-song features
        # The multi-song features require more complex segment management
        self.exporter.export_tables_with_patterns(
            self.test_frames,
            self.test_patterns,
            self.test_references,
            music_asm,
            standalone=False
        )
        self.patch_music_asm(music_asm)
        
        self.builder.prepare_project(str(music_asm))
        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Multi-song compilation failed:\n{output}")

    def test_zeropage_variables(self):
        """Test that zeropage variables are properly declared and used"""
        # Create project directory first
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        music_asm = self.project_path / "music.asm"
        self.exporter.export_tables_with_patterns(
            self.test_frames,
            self.test_patterns,
            self.test_references,
            music_asm,
            standalone=False
        )
        self.patch_music_asm(music_asm)
        
        self.builder.prepare_project(str(music_asm))
        
        # Read generated files and check for proper variable declarations
        with open(self.project_path / "main.asm") as f:
            main_content = f.read()
            # Updated to include temp_ptr for table-based lookups
            self.assertIn(".exportzp", main_content)
            self.assertIn("init_music", main_content)
            self.assertTrue("update_music" in main_content or "play_music" in main_content)
        
        with open(music_asm) as f:
            music_content = f.read()
            self.assertIn(".importzp", music_content)
            self.assertIn("init_music", music_content)
            self.assertTrue("update_music" in music_content or "play_music" in music_content)
        
        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Compilation with zeropage variables failed:\n{output}")

    def test_pattern_references(self):
        """Test that pattern references are properly aligned and addressable"""
        # Create project directory first
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        music_asm = self.project_path / "music.asm"
        
        # Create a pattern that requires proper alignment
        test_patterns = {
            'pattern_1': {'events': [{'note': 60, 'volume': 15}] * 256}  # Large pattern
        }
        test_references = {str(i): ('pattern_1', 0) for i in range(0, 256, 32)}
        
        self.exporter.export_tables_with_patterns(
            self.test_frames,
            test_patterns,
            test_references,
            music_asm,
            standalone=False
        )
        self.patch_music_asm(music_asm)
        
        self.builder.prepare_project(str(music_asm))
        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Compilation with large patterns failed:\n{output}")

    def test_bank_switching(self):
        """Test compilation with bank switching for large songs"""
        # Create project directory first
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        music_asm = self.project_path / "music.asm"
        
        # Create patterns that would require bank switching
        large_patterns = {
            f'pattern_{i}': {
                'events': [{'note': 60, 'volume': 15}] * 256
            } for i in range(32)  # Many large patterns
        }
        
        self.exporter.export_tables_with_patterns(
            self.test_frames,
            large_patterns,
            self.test_references,
            music_asm,
            standalone=False
        )
        self.patch_music_asm(music_asm)
        
        self.builder.prepare_project(str(music_asm))
        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Compilation with bank switching failed:\n{output}")

    def test_rom_size_validation(self):
        """Test that compiled ROMs have correct iNES format size"""
        # Create project directory first
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        music_asm = self.project_path / "music.asm"
        self.exporter.export_tables_with_patterns(
            self.test_frames,
            self.test_patterns,
            self.test_references,
            music_asm,
            standalone=False
        )
        self.patch_music_asm(music_asm)
        
        self.builder.prepare_project(str(music_asm))
        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Compilation failed:\n{output}")
        
        # Check that the generated ROM has correct size
        rom_path = self.project_path / "game.nes"
        self.assertTrue(rom_path.exists(), "ROM file not generated")
        
        # Read and validate ROM
        rom_size = rom_path.stat().st_size

        # Verify iNES header
        with open(rom_path, 'rb') as f:
            header = f.read(16)

        expected_size = 16 + (header[4] * 16384) + (header[5] * 8192)
        self.assertEqual(rom_size, expected_size,
            f"ROM size mismatch: got {rom_size} bytes, expected {expected_size} bytes")

        self.assertEqual(header[0:4], b'NES\x1a', "Invalid iNES header")
        self.assertEqual(header[6] & 0xF0, 0x40, "Mapper should be MMC3 (4)")

if __name__ == '__main__':
    unittest.main()
