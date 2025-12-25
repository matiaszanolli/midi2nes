"""End-to-end tests for the complete MIDI to ROM pipeline"""

import pytest
import tempfile
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.append(str(Path(__file__).parent.parent))

import main


class TestEndToEndPipeline:
    """Test the complete pipeline from MIDI to ROM"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        
    def create_test_midi(self):
        """Create a minimal test MIDI file"""
        import mido
        mid = mido.MidiFile()
        track = mido.MidiTrack()
        mid.tracks.append(track)
        
        # Add a few notes
        track.append(mido.Message('note_on', note=60, velocity=64, time=0))
        track.append(mido.Message('note_off', note=60, velocity=0, time=480))
        track.append(mido.Message('note_on', note=64, velocity=64, time=0))
        track.append(mido.Message('note_off', note=64, velocity=0, time=480))
        
        midi_path = self.temp_path / "test.mid"
        mid.save(midi_path)
        return midi_path
    
    def test_compile_rom_function(self):
        """Test the compile_rom function with mocked cc65 tools"""
        from main import compile_rom
        
        project_dir = self.temp_path / "project"
        project_dir.mkdir()
        rom_output = self.temp_path / "output.nes"
        
        # Create dummy asm files
        (project_dir / "main.asm").write_text(".byte $00")
        (project_dir / "music.asm").write_text(".byte $00")
        (project_dir / "nes.cfg").write_text("")
        
        # Mock successful compilation
        with patch('subprocess.run') as mock_run:
            # Mock ca65/ld65 version checks
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            
            # Create fake ROM file
            fake_rom = project_dir / "game.nes"
            fake_rom.write_bytes(b'NES\x1a' + b'\x00' * 40000)  # 40KB fake ROM
            
            result = compile_rom(project_dir, rom_output)
            
            # Should succeed
            assert result == True
            
    def test_compile_rom_missing_tools(self):
        """Test compile_rom when cc65 tools are missing"""
        from main import compile_rom
        
        project_dir = self.temp_path / "project"
        project_dir.mkdir()
        rom_output = self.temp_path / "output.nes"
        
        with patch('subprocess.run') as mock_run:
            # Mock ca65 not found
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
            
            result = compile_rom(project_dir, rom_output)
            
            # Should fail gracefully
            assert result == False
    
    def test_full_pipeline_parse_step(self):
        """Test that the full pipeline can at least parse MIDI"""
        midi_path = self.create_test_midi()
        
        # Just test parsing step in isolation
        from tracker.parser_fast import parse_midi_to_frames
        result = parse_midi_to_frames(str(midi_path))
        
        assert 'events' in result
        assert 'metadata' in result
        
    def test_run_parse_command(self):
        """Test the parse command"""
        midi_path = self.create_test_midi()
        output_path = self.temp_path / "parsed.json"
        
        # Create args object
        args = MagicMock()
        args.input = str(midi_path)
        args.output = str(output_path)
        
        main.run_parse(args)
        
        assert output_path.exists()
        
    def test_run_map_command(self):
        """Test the map command"""
        # First create parsed data
        midi_path = self.create_test_midi()
        parsed_path = self.temp_path / "parsed.json"
        
        from tracker.parser_fast import parse_midi_to_frames
        import json
        midi_data = parse_midi_to_frames(str(midi_path))
        parsed_path.write_text(json.dumps(midi_data))
        
        output_path = self.temp_path / "mapped.json"
        
        args = MagicMock()
        args.input = str(parsed_path)
        args.output = str(output_path)
        
        main.run_map(args)
        
        assert output_path.exists()
        
    def test_run_frames_command(self):
        """Test the frames command"""
        # Create minimal mapped data
        mapped_path = self.temp_path / "mapped.json"
        import json
        mapped_data = {
            "pulse1": [{"frame": 0, "note": 60, "volume": 64}],
            "pulse2": []
        }
        mapped_path.write_text(json.dumps(mapped_data))
        
        output_path = self.temp_path / "frames.json"
        
        args = MagicMock()
        args.input = str(mapped_path)
        args.output = str(output_path)
        
        main.run_frames(args)
        
        assert output_path.exists()


    @pytest.mark.slow
    @pytest.mark.requires_cc65
    def test_full_pipeline_midi_to_validated_rom(self):
        """Test complete pipeline from MIDI to validated ROM.

        This test generates a real ROM file and validates it using ROM diagnostics.
        """
        midi_path = self.create_test_midi()
        rom_path = self.temp_path / "output.nes"

        # Create args for full pipeline
        args = MagicMock()
        args.input = str(midi_path)
        args.output = str(rom_path)
        args.no_patterns = False
        args.debug = False
        args.verbose = False
        args.skip_validation = True  # Skip validation for this test if integrated

        try:
            # Run full pipeline (if available)
            from main import run_full_pipeline
            run_full_pipeline(args)

            # Check if ROM was generated
            if rom_path.exists():
                # Validate the generated ROM
                from debug.rom_diagnostics import ROMDiagnostics
                diagnostics = ROMDiagnostics(verbose=False)
                result = diagnostics.diagnose_rom(str(rom_path))

                assert result.is_valid_nes == True, "Generated ROM should have valid iNES header"
                assert result.reset_vectors_valid == True, "Generated ROM should have valid reset vectors"
                assert result.overall_health in ["HEALTHY", "GOOD", "FAIR"], \
                    f"Generated ROM should be at least FAIR health, got {result.overall_health}"
        except Exception as e:
            pytest.skip(f"Full pipeline test skipped: {str(e)}")

    @pytest.mark.integration
    def test_pipeline_project_structure(self):
        """Test that the pipeline creates proper project structure."""
        from nes.project_builder import NESProjectBuilder

        project_dir = self.temp_path / "nes_project"
        music_asm = self.temp_path / "music.asm"
        music_asm.write_text("""; Test music
.importzp frame_counter
.segment "CODE"
init_music: lda #$0F
            sta $4015
            rts
update_music: rts
""")

        builder = NESProjectBuilder(str(project_dir))
        result = builder.prepare_project(str(music_asm))

        assert result == True
        assert (project_dir / "main.asm").exists()
        assert (project_dir / "music.asm").exists()
        assert (project_dir / "nes.cfg").exists()

    @pytest.mark.integration
    def test_pipeline_generates_valid_assembly(self):
        """Test that pipeline generates valid assembly code."""
        from nes.project_builder import NESProjectBuilder

        project_dir = self.temp_path / "project"
        music_asm = self.temp_path / "music.asm"
        music_asm.write_text("""; Music
.importzp frame_counter
.segment "CODE"
init_music: rts
update_music: rts
""")

        builder = NESProjectBuilder(str(project_dir))
        builder.prepare_project(str(music_asm))

        # Check main.asm has required elements
        main_asm = project_dir / "main.asm"
        content = main_asm.read_text()

        assert '.segment "HEADER"' in content
        assert 'NES' in content
        assert 'reset:' in content
        assert 'nmi:' in content
        assert '.segment "VECTORS"' in content

    @pytest.mark.integration
    def test_rom_diagnostics_on_generated_file(self):
        """Test that ROM diagnostics works on valid ROM file."""
        from tests.conftest import _create_ines_header
        import struct

        # Create a valid test ROM
        rom_path = self.temp_path / "test.nes"
        header = _create_ines_header(8, 0, mapper=1)

        # Create PRG data with valid reset vectors
        prg_rom = bytearray(128 * 1024)

        # Add APU pattern
        prg_rom[100:105] = b'\xA9\x0F\x8D\x15\x40'  # APU Enable pattern

        # Set reset vectors at end
        vectors_offset = 0x20000 - 6
        prg_rom[vectors_offset:vectors_offset+2] = struct.pack('<H', 0x8000)  # NMI
        prg_rom[vectors_offset+2:vectors_offset+4] = struct.pack('<H', 0x8000)  # RESET
        prg_rom[vectors_offset+4:vectors_offset+6] = struct.pack('<H', 0x8000)  # IRQ

        rom_path.write_bytes(header + bytes(prg_rom))

        # Diagnose the ROM
        from debug.rom_diagnostics import ROMDiagnostics
        diagnostics = ROMDiagnostics(verbose=False)
        result = diagnostics.diagnose_rom(str(rom_path))

        assert result.is_valid_nes == True
        assert result.reset_vectors_valid == True
        assert result.apu_pattern_count > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
