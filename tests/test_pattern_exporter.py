"""Tests for exporter/pattern_exporter.py and exporter/exporter.py"""

import pytest
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from exporter.pattern_exporter import PatternExporter
from exporter.exporter import generate_famitracker_txt_with_patterns, midi_note_to_ft


class TestPatternExporter:
    """Test PatternExporter class"""
    
    def test_initialization(self):
        """Test PatternExporter initialization"""
        compressed_data = {
            'pattern_1': {
                'events': [
                    {'note': 60, 'volume': 64},
                    {'note': 62, 'volume': 64}
                ]
            }
        }
        pattern_refs = {
            'pattern_1': [0, 10, 20]
        }
        
        exporter = PatternExporter(compressed_data, pattern_refs)
        
        assert exporter.compressed_data == compressed_data
        assert exporter.pattern_refs == pattern_refs
        assert exporter.pattern_map is not None
        
    def test_pattern_map_creation(self):
        """Test pattern map is created correctly"""
        compressed_data = {
            'pattern_1': {
                'events': [
                    {'note': 60, 'volume': 64},
                    {'note': 62, 'volume': 64}
                ]
            }
        }
        pattern_refs = {
            'pattern_1': [0, 10]
        }
        
        exporter = PatternExporter(compressed_data, pattern_refs)
        
        # Pattern at position 0: frames 0, 1
        assert 0 in exporter.pattern_map
        assert 1 in exporter.pattern_map
        
        # Pattern at position 10: frames 10, 11
        assert 10 in exporter.pattern_map
        assert 11 in exporter.pattern_map
        
    def test_get_frame_data(self):
        """Test getting frame data by frame number"""
        compressed_data = {
            'pattern_1': {
                'events': [
                    {'note': 60, 'volume': 64},
                    {'note': 62, 'volume': 64}
                ]
            }
        }
        pattern_refs = {
            'pattern_1': [0]
        }
        
        exporter = PatternExporter(compressed_data, pattern_refs)
        
        # Frame 0 should have first event
        frame_0 = exporter.get_frame_data(0)
        assert frame_0['note'] == 60
        assert frame_0['volume'] == 64
        
        # Frame 1 should have second event
        frame_1 = exporter.get_frame_data(1)
        assert frame_1['note'] == 62
        
        # Frame 5 doesn't exist
        frame_5 = exporter.get_frame_data(5)
        assert frame_5 == {}
        
    def test_get_max_frame(self):
        """Test getting maximum frame number"""
        compressed_data = {
            'pattern_1': {
                'events': [{'note': 60, 'volume': 64}]
            }
        }
        pattern_refs = {
            'pattern_1': [0, 10, 20]
        }
        
        exporter = PatternExporter(compressed_data, pattern_refs)
        
        # Max should be 20 (last pattern start)
        assert exporter.get_max_frame() == 20
        
    def test_expand_to_frames(self):
        """Test expanding patterns to frames"""
        compressed_data = {
            'pattern_1': {
                'events': [
                    {'note': 60, 'volume': 64},
                    {'note': 62, 'volume': 64}
                ]
            }
        }
        pattern_refs = {
            'pattern_1': [0, 5]
        }
        
        exporter = PatternExporter(compressed_data, pattern_refs)
        frames = exporter.expand_to_frames()
        
        # Should have frames 0, 1, 5, 6
        assert len(frames) >= 4
        assert 0 in frames
        assert 1 in frames
        assert 5 in frames
        assert 6 in frames


class TestExporterFunctions:
    """Test exporter.py functions"""
    
    def test_midi_note_to_ft(self):
        """Test MIDI note to FamiTracker format conversion"""
        # Middle C (MIDI 60) = C-4
        assert midi_note_to_ft(60) == "C-4"
        
        # A440 (MIDI 69) = A-4
        assert midi_note_to_ft(69) == "A-4"
        
        # C# (MIDI 61) = C#4
        assert midi_note_to_ft(61) == "C#4"
        
    def test_generate_famitracker_txt(self):
        """Test FamiTracker text generation"""
        compressed_data = {
            'pattern_1': {
                'events': [
                    {'note': 60, 'volume': 64},
                    {'note': 62, 'volume': 64}
                ]
            }
        }
        pattern_refs = {
            'pattern_1': [0]
        }
        
        result = generate_famitracker_txt_with_patterns(
            {},  # frames_data not used
            compressed_data,
            pattern_refs,
            rows_per_pattern=64
        )
        
        # Should generate valid FamiTracker text
        assert isinstance(result, str)
        assert "FamiTracker" in result
        assert "PATTERN" in result
        assert "C-4" in result  # MIDI note 60
        
    def test_generate_famitracker_txt_empty(self):
        """Test FamiTracker text generation with empty patterns"""
        result = generate_famitracker_txt_with_patterns(
            {},
            {},
            {},
            rows_per_pattern=4
        )
        
        # Should still generate valid output
        assert isinstance(result, str)
        assert "FamiTracker" in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
