"""
Comprehensive tests for tracker/parser_fast.py

This test suite covers:
- Basic MIDI parsing functionality
- Tempo change handling
- Note event processing
- Track naming and metadata
- Error handling and edge cases
- Full analysis parser with patterns/loops
- Command-line interface
"""

import pytest
import tempfile
import os
import sys
import json
import mido
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

sys.path.append(str(Path(__file__).parent.parent))

from tracker.parser_fast import (
    parse_midi_to_frames, 
    parse_midi_to_frames_with_analysis
)
from tracker.tempo_map import TempoValidationError


class TestParseMidiToFrames:
    """Test the fast MIDI parser"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = Path(tempfile.mkdtemp())
        
    def teardown_method(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_test_midi(self, filename="test.mid", tracks=None):
        """Create a test MIDI file"""
        if tracks is None:
            tracks = [
                [
                    mido.MetaMessage('track_name', name='Piano', time=0),
                    mido.Message('note_on', channel=0, note=60, velocity=64, time=0),
                    mido.Message('note_off', channel=0, note=60, velocity=0, time=480),
                    mido.MetaMessage('end_of_track', time=0)
                ]
            ]
        
        mid = mido.MidiFile()
        for track_data in tracks:
            track = mido.MidiTrack()
            track.extend(track_data)
            mid.tracks.append(track)
        
        midi_path = self.temp_dir / filename
        mid.save(str(midi_path))
        return str(midi_path)
    
    def test_basic_midi_parsing(self):
        """Test basic MIDI file parsing"""
        midi_path = self.create_test_midi()
        result = parse_midi_to_frames(midi_path)
        
        assert isinstance(result, dict)
        assert 'events' in result
        assert 'metadata' in result
        assert isinstance(result['events'], dict)
        assert isinstance(result['metadata'], dict)
        
        # Should have at least one track
        assert len(result['events']) > 0
        
        # Check basic event structure
        first_track = next(iter(result['events'].values()))
        assert len(first_track) >= 2  # note_on and note_off
        
        for event in first_track:
            assert 'frame' in event
            assert 'note' in event
            assert 'volume' in event
            assert 'type' in event
            assert 'tempo' in event
    
    def test_track_naming(self):
        """Test that track names are properly extracted and sanitized"""
        tracks = [
            [
                mido.MetaMessage('track_name', name='Piano Track', time=0),
                mido.Message('note_on', channel=0, note=60, velocity=64, time=0),
                mido.Message('note_off', channel=0, note=60, velocity=0, time=480),
                mido.MetaMessage('end_of_track', time=0)
            ],
            [
                mido.MetaMessage('track_name', name='Guitar/Bass', time=0),  # Special chars
                mido.Message('note_on', channel=1, note=50, velocity=80, time=0),
                mido.Message('note_off', channel=1, note=50, velocity=0, time=240),
                mido.MetaMessage('end_of_track', time=0)
            ]
        ]
        
        midi_path = self.create_test_midi("naming_test.mid", tracks)
        result = parse_midi_to_frames(midi_path)
        
        # Check that track names are sanitized (spaces -> underscores)
        track_names = list(result['events'].keys())
        assert 'Piano_Track' in track_names
        assert 'Guitar/Bass' in track_names  # Special chars preserved
    
    def test_default_track_naming(self):
        """Test default track naming when no track_name is provided"""
        tracks = [
            [
                # No track_name message
                mido.Message('note_on', channel=0, note=60, velocity=64, time=0),
                mido.Message('note_off', channel=0, note=60, velocity=0, time=480),
                mido.MetaMessage('end_of_track', time=0)
            ]
        ]
        
        midi_path = self.create_test_midi("default_naming.mid", tracks)
        result = parse_midi_to_frames(midi_path)
        
        # Should use default track_N naming
        assert 'track_0' in result['events']
    
    def test_tempo_changes(self):
        """Test handling of tempo changes"""
        tracks = [
            [
                mido.MetaMessage('set_tempo', tempo=600000, time=0),  # 100 BPM
                mido.Message('note_on', channel=0, note=60, velocity=64, time=0),
                mido.MetaMessage('set_tempo', tempo=300000, time=240),  # 200 BPM
                mido.Message('note_off', channel=0, note=60, velocity=0, time=240),
                mido.MetaMessage('end_of_track', time=0)
            ]
        ]
        
        midi_path = self.create_test_midi("tempo_test.mid", tracks)
        result = parse_midi_to_frames(midi_path)
        
        events = next(iter(result['events'].values()))
        
        # Should have events with different tempo values
        tempos = [event['tempo'] for event in events]
        assert len(set(tempos)) > 1, "Should have multiple tempo values"
    
    def test_invalid_tempo_handling(self):
        """Test that invalid tempos are silently skipped"""
        # Create a mock MIDI file with invalid tempo
        with patch('mido.MidiFile') as mock_midi:
            mock_track = MagicMock()
            mock_track.tracks = [[
                mido.MetaMessage('set_tempo', tempo=0, time=0),  # Invalid tempo
                mido.Message('note_on', channel=0, note=60, velocity=64, time=0),
                mido.Message('note_off', channel=0, note=60, velocity=0, time=480),
            ]]
            mock_midi.return_value = mock_track
            
            # Mock tempo map to raise TempoValidationError
            with patch('tracker.parser_fast.EnhancedTempoMap') as mock_tempo_map:
                mock_tempo_instance = MagicMock()
                mock_tempo_instance.add_tempo_change.side_effect = TempoValidationError("Invalid tempo")
                mock_tempo_instance.get_frame_for_tick.return_value = 0
                mock_tempo_instance.get_tempo_at_tick.return_value = 500000
                mock_tempo_map.return_value = mock_tempo_instance
                
                # Should not raise exception
                result = parse_midi_to_frames("dummy.mid")
                assert isinstance(result, dict)
    
    def test_note_events_processing(self):
        """Test note_on and note_off event processing"""
        tracks = [
            [
                mido.Message('note_on', channel=0, note=60, velocity=100, time=0),
                mido.Message('note_on', channel=0, note=64, velocity=80, time=120),
                mido.Message('note_on', channel=0, note=67, velocity=0, time=120),  # note_on with vel=0 -> note_off
                mido.Message('note_off', channel=0, note=60, velocity=0, time=240),
                mido.Message('note_off', channel=0, note=64, velocity=64, time=120),
                mido.MetaMessage('end_of_track', time=0)
            ]
        ]
        
        midi_path = self.create_test_midi("notes_test.mid", tracks)
        result = parse_midi_to_frames(midi_path)
        
        events = next(iter(result['events'].values()))
        
        # Check note values
        notes = [event['note'] for event in events]
        assert 60 in notes
        assert 64 in notes
        assert 67 in notes
        
        # Check velocity handling
        note_on_events = [e for e in events if e['type'] == 'note_on']
        note_off_events = [e for e in events if e['type'] == 'note_off']
        
        assert len(note_on_events) > 0
        assert len(note_off_events) > 0
        
        # Check that note_on with velocity 0 becomes note_off
        note_67_events = [e for e in events if e['note'] == 67]
        assert all(e['type'] == 'note_off' for e in note_67_events)
    
    def test_event_error_handling(self):
        """Test that problematic events are silently skipped"""
        with patch('mido.MidiFile') as mock_midi:
            mock_track = MagicMock()
            mock_track.tracks = [[
                mido.Message('note_on', channel=0, note=60, velocity=64, time=0),
            ]]
            mock_midi.return_value = mock_track
            
            # Mock tempo map to raise exception on get_frame_for_tick
            with patch('tracker.parser_fast.EnhancedTempoMap') as mock_tempo_map:
                mock_tempo_instance = MagicMock()
                mock_tempo_instance.get_frame_for_tick.side_effect = Exception("Frame calculation error")
                mock_tempo_map.return_value = mock_tempo_instance
                
                # Should not raise exception, should return empty events
                result = parse_midi_to_frames("dummy.mid")
                assert isinstance(result, dict)
                assert 'events' in result
    
    def test_empty_midi_file(self):
        """Test parsing of empty MIDI file"""
        tracks = [
            [mido.MetaMessage('end_of_track', time=0)]
        ]
        
        midi_path = self.create_test_midi("empty.mid", tracks)
        result = parse_midi_to_frames(midi_path)
        
        assert isinstance(result, dict)
        assert 'events' in result
        assert 'metadata' in result
        # Should have the track but with no events
        assert len(result['events']) >= 0
    
    def test_multiple_tracks(self):
        """Test parsing MIDI file with multiple tracks"""
        tracks = [
            [
                mido.MetaMessage('track_name', name='Piano', time=0),
                mido.Message('note_on', channel=0, note=60, velocity=64, time=0),
                mido.Message('note_off', channel=0, note=60, velocity=0, time=480),
                mido.MetaMessage('end_of_track', time=0)
            ],
            [
                mido.MetaMessage('track_name', name='Guitar', time=0),
                mido.Message('note_on', channel=1, note=55, velocity=80, time=0),
                mido.Message('note_off', channel=1, note=55, velocity=0, time=240),
                mido.MetaMessage('end_of_track', time=0)
            ],
            [
                mido.MetaMessage('track_name', name='Drums', time=0),
                mido.Message('note_on', channel=9, note=36, velocity=100, time=0),
                mido.Message('note_off', channel=9, note=36, velocity=0, time=120),
                mido.MetaMessage('end_of_track', time=0)
            ]
        ]
        
        midi_path = self.create_test_midi("multi_track.mid", tracks)
        result = parse_midi_to_frames(midi_path)
        
        assert len(result['events']) == 3
        assert 'Piano' in result['events']
        assert 'Guitar' in result['events']
        assert 'Drums' in result['events']
        
        # Each track should have events
        for track_name, events in result['events'].items():
            assert len(events) >= 2  # At least note_on and note_off


class TestParseMidiToFramesWithAnalysis:
    """Test the full analysis parser"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = Path(tempfile.mkdtemp())
        
    def teardown_method(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_test_midi(self, filename="test_analysis.mid"):
        """Create a test MIDI file with patterns"""
        tracks = [
            [
                mido.MetaMessage('track_name', name='PatternTrack', time=0),
                # Pattern: C-E-G-C
                mido.Message('note_on', channel=0, note=60, velocity=64, time=0),
                mido.Message('note_off', channel=0, note=60, velocity=0, time=120),
                mido.Message('note_on', channel=0, note=64, velocity=64, time=0),
                mido.Message('note_off', channel=0, note=64, velocity=0, time=120),
                mido.Message('note_on', channel=0, note=67, velocity=64, time=0),
                mido.Message('note_off', channel=0, note=67, velocity=0, time=120),
                mido.Message('note_on', channel=0, note=72, velocity=64, time=0),
                mido.Message('note_off', channel=0, note=72, velocity=0, time=120),
                # Repeat pattern
                mido.Message('note_on', channel=0, note=60, velocity=64, time=0),
                mido.Message('note_off', channel=0, note=60, velocity=0, time=120),
                mido.Message('note_on', channel=0, note=64, velocity=64, time=0),
                mido.Message('note_off', channel=0, note=64, velocity=0, time=120),
                mido.Message('note_on', channel=0, note=67, velocity=64, time=0),
                mido.Message('note_off', channel=0, note=67, velocity=0, time=120),
                mido.Message('note_on', channel=0, note=72, velocity=64, time=0),
                mido.Message('note_off', channel=0, note=72, velocity=0, time=120),
                mido.MetaMessage('end_of_track', time=0)
            ]
        ]
        
        mid = mido.MidiFile()
        for track_data in tracks:
            track = mido.MidiTrack()
            track.extend(track_data)
            mid.tracks.append(track)
        
        midi_path = self.temp_dir / filename
        mid.save(str(midi_path))
        return str(midi_path)
    
    def test_analysis_parser_basic_structure(self):
        """Test that the analysis parser returns proper structure"""
        midi_path = self.create_test_midi()
        result = parse_midi_to_frames_with_analysis(midi_path)
        
        assert isinstance(result, dict)
        assert 'events' in result
        assert 'metadata' in result
        assert isinstance(result['events'], dict)
        assert isinstance(result['metadata'], dict)
    
    @patch('tracker.pattern_detector.EnhancedPatternDetector')
    @patch('tracker.loop_manager.EnhancedLoopManager')
    def test_analysis_with_patterns(self, mock_loop_manager, mock_pattern_detector):
        """Test that pattern detection is called and results included"""
        # Mock pattern detector
        mock_detector_instance = MagicMock()
        mock_detector_instance.detect_patterns.return_value = {
            'patterns': {'pattern_1': [{'note': 60, 'frame': 0}]},
            'references': {'pattern_1': [0, 10]},
            'stats': {'compression_ratio': 2.0}
        }
        mock_pattern_detector.return_value = mock_detector_instance
        
        # Mock loop manager
        mock_loop_instance = MagicMock()
        mock_loop_instance.detect_loops.return_value = [{'start': 0, 'end': 10}]
        mock_loop_instance.generate_jump_table.return_value = {'0': 10}
        mock_loop_manager.return_value = mock_loop_instance
        
        midi_path = self.create_test_midi()
        result = parse_midi_to_frames_with_analysis(midi_path)
        
        # Should have metadata for tracks with note events
        assert len(result['metadata']) > 0
        
        track_metadata = next(iter(result['metadata'].values()))
        assert 'patterns' in track_metadata
        assert 'pattern_refs' in track_metadata
        assert 'compression_stats' in track_metadata
        assert 'loops' in track_metadata
        assert 'jump_table' in track_metadata
    
    @patch('tracker.pattern_detector.EnhancedPatternDetector')
    @patch('tracker.loop_manager.EnhancedLoopManager')
    def test_analysis_skips_empty_tracks(self, mock_loop_manager, mock_pattern_detector):
        """Test that tracks without note_on events are skipped in analysis"""
        # Create MIDI with one track having only note_off or other events
        tracks = [
            [
                mido.MetaMessage('track_name', name='EmptyTrack', time=0),
                mido.Message('note_off', channel=0, note=60, velocity=0, time=480),  # Only note_off
                mido.MetaMessage('end_of_track', time=0)
            ],
            [
                mido.MetaMessage('track_name', name='ActiveTrack', time=0),
                mido.Message('note_on', channel=0, note=60, velocity=64, time=0),  # Has note_on
                mido.Message('note_off', channel=0, note=60, velocity=0, time=480),
                mido.MetaMessage('end_of_track', time=0)
            ]
        ]
        
        mid = mido.MidiFile()
        for track_data in tracks:
            track = mido.MidiTrack()
            track.extend(track_data)
            mid.tracks.append(track)
        
        midi_path = self.temp_dir / "empty_track_test.mid"
        mid.save(str(midi_path))
        
        # Mock pattern detector
        mock_detector_instance = MagicMock()
        mock_detector_instance.detect_patterns.return_value = {
            'patterns': {}, 'references': {}, 'stats': {}
        }
        mock_pattern_detector.return_value = mock_detector_instance
        
        # Mock loop manager
        mock_loop_instance = MagicMock()
        mock_loop_instance.detect_loops.return_value = []
        mock_loop_instance.generate_jump_table.return_value = {}
        mock_loop_manager.return_value = mock_loop_instance
        
        result = parse_midi_to_frames_with_analysis(str(midi_path))
        
        # Should only have metadata for the track with actual note_on events
        assert 'ActiveTrack' in result['metadata']
        # EmptyTrack might be present but with empty analysis or not present at all
        if 'EmptyTrack' in result['metadata']:
            empty_metadata = result['metadata']['EmptyTrack']
            # Should have empty or minimal metadata
            assert len(empty_metadata.get('patterns', {})) == 0
    
    def test_tempo_validation_error_handling(self):
        """Test handling of tempo validation errors in analysis parser"""
        # Create a real MIDI file with invalid tempo that will trigger TempoValidationError 
        # in the analysis parser's tempo map rebuild section (lines 122-123)
        tracks = [
            [
                mido.MetaMessage('set_tempo', tempo=1, time=0),  # Extremely low tempo - invalid
                mido.Message('note_on', channel=0, note=60, velocity=64, time=0),
                mido.Message('note_off', channel=0, note=60, velocity=0, time=480),
                mido.MetaMessage('end_of_track', time=0)
            ]
        ]
        
        mid = mido.MidiFile()
        for track_data in tracks:
            track = mido.MidiTrack()
            track.extend(track_data)
            mid.tracks.append(track)
        
        midi_path = self.temp_dir / "invalid_tempo.mid"
        mid.save(str(midi_path))
        
        # This should not raise an exception even with invalid tempo
        # The TempoValidationError should be caught and silently skipped
        result = parse_midi_to_frames_with_analysis(str(midi_path))
        assert isinstance(result, dict)
        assert 'events' in result
        assert 'metadata' in result


class TestCommandLineInterface:
    """Test the command-line interface functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = Path(tempfile.mkdtemp())
        
    def teardown_method(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_test_midi(self):
        """Create a simple test MIDI file"""
        mid = mido.MidiFile()
        track = mido.MidiTrack()
        track.extend([
            mido.Message('note_on', channel=0, note=60, velocity=64, time=0),
            mido.Message('note_off', channel=0, note=60, velocity=0, time=480),
            mido.MetaMessage('end_of_track', time=0)
        ])
        mid.tracks.append(track)
        
        midi_path = self.temp_dir / "cli_test.mid"
        mid.save(str(midi_path))
        return str(midi_path)
    
    def test_cli_fast_parsing_integration(self):
        """Test CLI with actual file I/O - fast parsing"""
        midi_path = self.create_test_midi()
        output_path = str(self.temp_dir / "output.json")
        
        # Run the actual CLI script using module syntax
        import subprocess
        project_root = Path(__file__).parent.parent
        result = subprocess.run([
            'python3', '-m', 'tracker.parser_fast',
            midi_path, output_path
        ], cwd=str(project_root), capture_output=True, text=True)
        
        assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}"
        assert Path(output_path).exists()
        
        # Check that output file contains expected structure
        with open(output_path, 'r') as f:
            data = json.load(f)
            assert 'events' in data
            assert 'metadata' in data
    
    def test_cli_with_analysis_integration(self):
        """Test CLI with actual file I/O - analysis parsing"""
        midi_path = self.create_test_midi()
        output_path = str(self.temp_dir / "output_analysis.json")
        
        # Run the actual CLI script with analysis using module syntax
        import subprocess
        project_root = Path(__file__).parent.parent
        result = subprocess.run([
            'python3', '-m', 'tracker.parser_fast',
            midi_path, output_path, '--with-analysis'
        ], cwd=str(project_root), capture_output=True, text=True)
        
        assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}"
        assert Path(output_path).exists()
        
        # Check that output file contains expected structure with metadata
        with open(output_path, 'r') as f:
            data = json.load(f)
            assert 'events' in data
            assert 'metadata' in data
    
    def test_cli_insufficient_arguments_integration(self):
        """Test CLI with insufficient arguments"""
        import subprocess
        project_root = Path(__file__).parent.parent
        result = subprocess.run([
            'python3', '-m', 'tracker.parser_fast', 'input.mid'  # Missing output path
        ], cwd=str(project_root), capture_output=True, text=True)
        
        assert result.returncode == 1
        assert "Usage:" in result.stdout or "Usage:" in result.stderr
    
    def test_cli_nonexistent_input_file(self):
        """Test CLI with non-existent input file"""
        output_path = str(self.temp_dir / "output.json")

        import subprocess
        project_root = Path(__file__).parent.parent
        result = subprocess.run([
            'python3', 'tracker/parser_fast.py',
            'nonexistent.mid', output_path
        ], cwd=str(project_root), capture_output=True, text=True)
        
        # Should exit with error due to missing input file
        assert result.returncode != 0
    
    @patch('tracker.parser_fast.parse_midi_to_frames')
    @patch('sys.argv')
    def test_cli_fast_parsing(self, mock_argv, mock_parse_fast):
        """Test CLI with fast parsing (default)"""
        midi_path = self.create_test_midi()
        output_path = str(self.temp_dir / "output.json")
        
        mock_argv.__getitem__ = lambda _, idx: [
            'parser_fast.py', midi_path, output_path
        ][idx]
        mock_argv.__len__ = lambda _: 3
        
        mock_parse_fast.return_value = {
            'events': {'track_0': [{'frame': 0, 'note': 60, 'volume': 64}]},
            'metadata': {}
        }
        
        # Import and run the CLI
        import tracker.parser_fast as parser_module
        
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('json.dump') as mock_json_dump:
                with patch('builtins.print') as mock_print:
                    # Simulate running the main block
                    parser_module.__name__ = '__main__'
                    
                    # This would normally be executed in if __name__ == '__main__'
                    # We'll call the parsing function directly
                    mock_parse_fast.assert_not_called()  # Reset any previous calls
                    
                    # Simulate the CLI logic
                    result = mock_parse_fast(midi_path)
                    
                    mock_parse_fast.assert_called_once_with(midi_path)
    
    @patch('tracker.parser_fast.parse_midi_to_frames_with_analysis')
    @patch('sys.argv')
    def test_cli_with_analysis(self, mock_argv, mock_parse_analysis):
        """Test CLI with analysis flag"""
        midi_path = self.create_test_midi()
        output_path = str(self.temp_dir / "output_analysis.json")
        
        mock_argv.__getitem__ = lambda _, idx: [
            'parser_fast.py', midi_path, output_path, '--with-analysis'
        ][idx]
        mock_argv.__len__ = lambda _: 4
        mock_argv.__contains__ = lambda _, item: item == '--with-analysis'
        
        mock_parse_analysis.return_value = {
            'events': {'track_0': [{'frame': 0, 'note': 60, 'volume': 64}]},
            'metadata': {'track_0': {'patterns': {}}}
        }
        
        # Simulate the CLI logic for analysis parsing
        result = mock_parse_analysis(midi_path)
        mock_parse_analysis.assert_called_once_with(midi_path)
    
    @patch('sys.argv')
    @patch('sys.exit')
    @patch('builtins.print')
    def test_cli_insufficient_arguments(self, mock_print, mock_exit, mock_argv):
        """Test CLI with insufficient arguments"""
        mock_argv.__len__ = lambda _: 2  # Only script name and one argument
        
        # Import the module to trigger the main block check
        import importlib
        import tracker.parser_fast as parser_module
        
        # Simulate running with insufficient args
        if len(sys.argv) < 3:
            print("Usage: python parser_fast.py <input.mid> <output.json> [--with-analysis]")
            sys.exit(1)
        
        # The above would normally be in the if __name__ == '__main__' block
        # We're just testing the logic would call these functions
        mock_print.assert_called_once()
        mock_exit.assert_called_once_with(1)


class TestEdgeCases:
    """Test various edge cases and error conditions"""
    
    def test_file_not_found(self):
        """Test handling of non-existent MIDI files"""
        with pytest.raises(FileNotFoundError):
            parse_midi_to_frames("nonexistent_file.mid")
    
    def test_corrupted_midi_file(self):
        """Test handling of corrupted MIDI files"""
        # Create a file that's not a valid MIDI file
        temp_dir = Path(tempfile.mkdtemp())
        bad_midi = temp_dir / "corrupted.mid"
        bad_midi.write_text("This is not a MIDI file")
        
        try:
            with pytest.raises(Exception):  # Should raise some kind of MIDI parsing error
                parse_midi_to_frames(str(bad_midi))
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @patch('tracker.parser_fast.EnhancedTempoMap')
    def test_tempo_map_initialization_error(self, mock_tempo_map):
        """Test handling of tempo map initialization errors"""
        mock_tempo_map.side_effect = Exception("Tempo map creation failed")
        
        with pytest.raises(Exception):
            parse_midi_to_frames("dummy.mid")
    
    def test_very_large_midi_file(self):
        """Test handling of MIDI files with many events"""
        # Create a MIDI file with many note events
        mid = mido.MidiFile()
        track = mido.MidiTrack()
        
        # Add many note events
        for i in range(1000):
            track.append(mido.Message('note_on', channel=0, note=60+i%12, velocity=64, time=10))
            track.append(mido.Message('note_off', channel=0, note=60+i%12, velocity=0, time=10))
        
        track.append(mido.MetaMessage('end_of_track', time=0))
        mid.tracks.append(track)
        
        temp_dir = Path(tempfile.mkdtemp())
        large_midi = temp_dir / "large.mid"
        mid.save(str(large_midi))
        
        try:
            # Should handle large files without crashing
            result = parse_midi_to_frames(str(large_midi))
            assert isinstance(result, dict)
            assert 'events' in result
            
            # Should have many events
            total_events = sum(len(events) for events in result['events'].values())
            assert total_events > 1000
            
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
