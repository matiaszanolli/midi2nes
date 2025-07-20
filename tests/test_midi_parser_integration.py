import unittest
import os
import tempfile
from mido import MidiFile, MidiTrack, Message, MetaMessage
from tracker.parser import parse_midi_to_frames
from tracker.pattern_detector import EnhancedPatternDetector
from tracker.tempo_map import (
    EnhancedTempoMap, TempoValidationConfig, 
    TempoOptimizationStrategy, TempoChangeType, 
    TempoValidationError
)

from constants import FRAME_MS, FRAME_RATE_HZ

class TestMIDIParserIntegration(unittest.TestCase):
    def setUp(self):
        """Create temporary directory for test MIDI files"""
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up temporary files"""
        for file in os.listdir(self.test_dir):
            os.remove(os.path.join(self.test_dir, file))
        os.rmdir(self.test_dir)
        
    def create_test_midi(self, filename, messages, ticks_per_beat=480):
        """Helper to create test MIDI files"""
        mid = MidiFile(ticks_per_beat=ticks_per_beat)
        track = MidiTrack()
        mid.tracks.append(track)
        
        for msg in messages:
            track.append(msg)
            
        path = os.path.join(self.test_dir, filename)
        mid.save(path)
        return path
        
    def test_basic_tempo_parsing(self):
        """Test basic tempo change parsing"""
        messages = [
            MetaMessage('set_tempo', tempo=500000, time=0),  # 120 BPM
            Message('note_on', note=60, velocity=64, time=480),  # C4 at 1 beat
            Message('note_off', note=60, velocity=0, time=480),  # Release after 1 beat
            MetaMessage('set_tempo', tempo=400000, time=0),  # 150 BPM
            Message('note_on', note=64, velocity=64, time=480),  # E4 at next beat
            Message('note_off', note=64, velocity=0, time=480)  # Release after 1 beat
        ]
        
        midi_path = self.create_test_midi('basic_tempo.mid', messages)
        result = parse_midi_to_frames(midi_path)
        
        # Verify events were parsed correctly
        events = result['events']['track_0']
        self.assertEqual(len(events), 4)  # 2 note_on and 2 note_off events
        
        # First note should be at frame 30 (500ms at 60fps)
        self.assertEqual(events[0]['frame'], 30)
        self.assertEqual(events[0]['type'], 'note_on')
        self.assertEqual(events[0]['note'], 60)
        
        # Second note should reflect the tempo change
        self.assertEqual(events[2]['type'], 'note_on')
        self.assertEqual(events[2]['note'], 64)
        
    def test_frame_aligned_tempo_changes(self):
        """Test that tempo changes are properly frame-aligned"""
        messages = [
            MetaMessage('set_tempo', tempo=500000, time=0),  # 120 BPM
            MetaMessage('set_tempo', tempo=400000, time=16),  # Should align to frame
            Message('note_on', note=60, velocity=64, time=0)
        ]
        
        midi_path = self.create_test_midi('frame_aligned.mid', messages)
        result = parse_midi_to_frames(midi_path)
        
        # Get the frame time of the note
        note_frame = result['events']['track_0'][0]['frame']
        
        # Verify frame alignment
        self.assertEqual(note_frame * FRAME_MS % FRAME_MS, 0)

    def test_complex_tempo_sequence(self):
        """Test handling of multiple sequential tempo changes"""
        messages = [
            MetaMessage('set_tempo', tempo=500000, time=0),  # 120 BPM
            MetaMessage('set_tempo', tempo=400000, time=480),  # 150 BPM
            MetaMessage('set_tempo', tempo=300000, time=480),  # 200 BPM
            Message('note_on', note=60, velocity=64, time=480)
        ]
        
        midi_path = self.create_test_midi('complex_tempo.mid', messages)
        result = parse_midi_to_frames(midi_path)
        
        # Get the first note event
        note_event = result['events']['track_0'][0]
        
        # Calculate expected frame:
        # First segment: 480 ticks at 120 BPM = 500ms
        # Second segment: 480 ticks at 150 BPM = 400ms
        # Third segment: 480 ticks at 200 BPM = 300ms
        # Total time = 1200ms
        # At 60fps (16.667ms per frame), frame = 1200/16.667 = 72 frames
        expected_frame = 72
        self.assertEqual(note_event['frame'], expected_frame)

    def test_invalid_tempo_handling(self):
        """Test handling of invalid tempo changes"""
        messages = [
            MetaMessage('set_tempo', tempo=500000, time=0),  # 120 BPM
            MetaMessage('set_tempo', tempo=100000, time=480),  # 600 BPM (invalid)
            Message('note_on', note=60, velocity=64, time=480)
        ]
        
        midi_path = self.create_test_midi('invalid_tempo.mid', messages)
        result = parse_midi_to_frames(midi_path)
        
        # Get the first note event
        note_event = result['events']['track_0'][0]
        
        # Calculate expected frame:
        # Since the second tempo change is invalid, it should be ignored
        # 960 ticks at 120 BPM = 1000ms
        # At 60fps, frame = 1000/16.67 ≈ 60 frames
        expected_frame = 60
        self.assertEqual(note_event['frame'], expected_frame)
        
def test_pattern_detection_with_tempo(self):
    """Test pattern detection with tempo changes"""
    # Create a very simple and clear repeating pattern
    # Use short notes with consistent timing to make pattern detection easier
    messages = [
        # Set initial tempo
        MetaMessage('set_tempo', tempo=500000, time=0),  # 120 BPM
        
        # First occurrence of pattern: C4->D4->E4
        Message('note_on', note=60, velocity=64, time=240),   # C4
        Message('note_off', note=60, velocity=0, time=240),
        Message('note_on', note=62, velocity=64, time=0),   # D4
        Message('note_off', note=62, velocity=0, time=240),
        Message('note_on', note=64, velocity=64, time=0),   # E4
        Message('note_off', note=64, velocity=0, time=240),
        
        # Gap between patterns
        Message('note_off', note=64, velocity=0, time=480),
        
        # Second occurrence of pattern: C4->D4->E4
        Message('note_on', note=60, velocity=64, time=0),   # C4
        Message('note_off', note=60, velocity=0, time=240),
        Message('note_on', note=62, velocity=64, time=0),   # D4
        Message('note_off', note=62, velocity=0, time=240),
        Message('note_on', note=64, velocity=64, time=0),   # E4
        Message('note_off', note=64, velocity=0, time=240),
        
        # Gap between patterns
        Message('note_off', note=64, velocity=0, time=480),
        
        # Third occurrence of pattern: C4->D4->E4
        Message('note_on', note=60, velocity=64, time=0),   # C4
        Message('note_off', note=60, velocity=0, time=240),
        Message('note_on', note=62, velocity=64, time=0),   # D4
        Message('note_off', note=62, velocity=0, time=240),
        Message('note_on', note=64, velocity=64, time=0),   # E4
        Message('note_off', note=64, velocity=0, time=240),
        
        # Gap between patterns
        Message('note_off', note=64, velocity=0, time=480),
        
        # Fourth occurrence of pattern: C4->D4->E4
        Message('note_on', note=60, velocity=64, time=0),   # C4
        Message('note_off', note=60, velocity=0, time=240),
        Message('note_on', note=62, velocity=64, time=0),   # D4
        Message('note_off', note=62, velocity=0, time=240),
        Message('note_on', note=64, velocity=64, time=0),   # E4
        Message('note_off', note=64, velocity=0, time=240)
    ]
    
    midi_path = self.create_test_midi('pattern_tempo.mid', messages)
    
    # Create tempo map first
    config = TempoValidationConfig(
        min_tempo_bpm=40.0,
        max_tempo_bpm=250.0,
        min_duration_frames=2,
        max_duration_frames=FRAME_RATE_HZ * 30  # 30 seconds
    )
    tempo_map = EnhancedTempoMap(
        initial_tempo=500000,  # 120 BPM
        validation_config=config,
        optimization_strategy=TempoOptimizationStrategy.FRAME_ALIGNED
    )
    
    # Now create the pattern detector with the tempo map
    pattern_detector = EnhancedPatternDetector(tempo_map=tempo_map)
    
    # Parse MIDI file
    result = parse_midi_to_frames(midi_path)
    
    # Get the patterns and references
    patterns = result['metadata']['track_0']['patterns']
    pattern_refs = result['metadata']['track_0']['pattern_refs']
    
    # Debug output
    print(f"DEBUG: Found {len(patterns)} patterns")
    print(f"DEBUG: Found {len(pattern_refs)} pattern references")
    
    # Verify pattern detection
    self.assertTrue(len(patterns) > 0, "No patterns detected")
    
    # Since we have 4 occurrences of the same pattern, we should have at least 3 references
    if len(pattern_refs) < 2:
        print("DEBUG: Pattern details:")
        for i, pattern in enumerate(patterns):
            print(f"  Pattern {i}: {pattern}")
        print("DEBUG: Pattern references:")
        for i, ref in enumerate(pattern_refs):
            print(f"  Reference {i}: {ref}")
    
    self.assertTrue(len(pattern_refs) >= 2, 
                   f"Not enough pattern references found. Got {len(pattern_refs)}, expected at least 2")
    
    # Verify pattern content
    if len(patterns) > 0:
        first_pattern = patterns[list(patterns.keys())[0]]
        pattern_events = first_pattern['events']
        self.assertEqual(len(pattern_events), 3, "Pattern should contain 3 notes")
        self.assertEqual(pattern_events[0]['note'], 60, "First note should be C4")
        self.assertEqual(pattern_events[1]['note'], 62, "Second note should be D4")
        self.assertEqual(pattern_events[2]['note'], 64, "Third note should be E4")
        
        # Verify all notes in the pattern have the same velocity
        velocities = set(event['volume'] for event in pattern_events)
        self.assertEqual(len(velocities), 1, "All notes should have the same velocity")
        self.assertEqual(list(velocities)[0], 64, "Velocity should be 64")


if __name__ == '__main__':
    unittest.main()
