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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
