import unittest
import os
import tempfile
from mido import MidiFile, MidiTrack, Message, MetaMessage
from tracker.parser import parse_midi_to_frames
from tracker.pattern_detector import EnhancedPatternDetector
from tracker.track_mapper import assign_tracks_to_nes_channels
from tracker.tempo_map import (
    EnhancedTempoMap, TempoValidationConfig, 
    TempoOptimizationStrategy, TempoChangeType, 
    TempoValidationError
)
from exporter.exporter_nsf import NSFExporter
from exporter.exporter_ca65 import CA65Exporter
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

    def verify_nsf_binary(self, file_path):
        """Verify NSF binary structure and playability"""
        with open(file_path, 'rb') as f:
            data = f.read()
        
        # Check file size
        self.assertGreaterEqual(len(data), 128, "NSF file too small")
        
        # Verify NSF header
        self.assertEqual(data[0:5], b'NESM\x1a', "Invalid NSF header")
        
        # Verify essential memory addresses
        load_address = int.from_bytes(data[8:10], 'little')
        init_address = int.from_bytes(data[10:12], 'little')
        play_address = int.from_bytes(data[12:14], 'little')
        
        self.assertLess(load_address, init_address, "Invalid address ordering")
        self.assertLess(init_address, play_address, "Invalid address ordering")
        
        # Verify bank references
        banks = data[0x70:0x78]
        self.assertTrue(any(b != 0 for b in banks), "No banks specified")

    def verify_ca65_assembly(self, file_path):
        """Verify CA65 assembly structure and syntax"""
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for required sections
        required_sections = [
            '.segment "HEADER"',
            '.segment "CODE"',
            '.segment "VECTORS"',
            'note_table:',
            'frame_data:'
        ]
        
        for section in required_sections:
            self.assertIn(section, content, f"Missing required section: {section}")
        
        # Verify label definitions
        self.assertIn('init:', content, "Missing init routine")
        self.assertIn('play:', content, "Missing play routine")
        
        # Check for valid addressing modes
        self.assertNotIn('undefined', content.lower(), "Contains undefined references")
        
    def test_complete_pipeline_with_verification(self):
        """Test the complete pipeline and verify the output binary"""
        # 1. Create a simple test MIDI file with known patterns
        messages = [
            MetaMessage('set_tempo', tempo=500000, time=0),  # 120 BPM
            Message('note_on', note=60, velocity=64, time=480),  # C4
            Message('note_off', note=60, velocity=0, time=480),
            Message('note_on', note=64, velocity=64, time=0),   # E4
            Message('note_off', note=64, velocity=0, time=480),
            Message('note_on', note=67, velocity=64, time=0),   # G4
            Message('note_off', note=67, velocity=0, time=480),
            # Repeat the same pattern
            Message('note_on', note=60, velocity=64, time=480),  # C4
            Message('note_off', note=60, velocity=0, time=480),
            Message('note_on', note=64, velocity=64, time=0),   # E4
            Message('note_off', note=64, velocity=0, time=480),
            Message('note_on', note=67, velocity=64, time=0),   # G4
            Message('note_off', note=67, velocity=0, time=480)
        ]
        
        test_midi_path = self.create_test_midi('test_complete.mid', messages)
        
        # 2. Parse MIDI to JSON
        parsed_data = parse_midi_to_frames(test_midi_path)
        self.assertIn('events', parsed_data, "Missing events in parsed data")
        self.assertIn('track_0', parsed_data['events'], "Missing track_0 in parsed data")
        
        # 3. Map channels (with mock dpcm_index_path)
        import tempfile
        import json
        # Create a temporary DPCM index file
        dpcm_index = {}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(dpcm_index, f)
            dpcm_index_path = f.name
        
        mapped_data = assign_tracks_to_nes_channels(parsed_data['events'], dpcm_index_path)
        self.assertIn('pulse1', mapped_data, "Missing pulse1 channel in mapped data")
        
        # Clean up temporary file
        import os
        os.unlink(dpcm_index_path)
        
        # 4. Generate frames (using mock function from test_frame_validation)
        from tests.test_frame_validation import generate_frames
        frame_data = generate_frames(mapped_data)
        self.assertTrue(len(frame_data) > 0, "No frames generated")
        
        # 5. Detect patterns (with mock tempo map)
        from tracker.tempo_map import EnhancedTempoMap
        mock_tempo_map = EnhancedTempoMap()
        pattern_detector = EnhancedPatternDetector(mock_tempo_map)
        
        # Convert frame data to events format expected by pattern detector
        events = []
        for frame_num, frame in enumerate(frame_data):
            for channel_name, channel_data in frame.items():
                if channel_data['note'] > 0 or channel_data['volume'] > 0:
                    event = {
                        'frame': frame_num,
                        'note': channel_data['note'],
                        'volume': channel_data['volume']
                    }
                    events.append(event)
        
        # Sort events by frame number
        events.sort(key=lambda x: x['frame'])
        
        pattern_data = pattern_detector.detect_patterns(events)
        self.assertIn('patterns', pattern_data, "No patterns detected")
        self.assertIn('references', pattern_data, "No pattern references found")
        
        # 6. Export to both formats
        nsf_exporter = NSFExporter()
        ca65_exporter = CA65Exporter()
        
        nsf_output = os.path.join(self.test_dir, "test_output.nsf")
        ca65_output = os.path.join(self.test_dir, "test_output.asm")
        
        nsf_result = nsf_exporter.export(frame_data, nsf_output)
        self.assertTrue(os.path.exists(nsf_output), "NSF file not created")
        
        ca65_result = ca65_exporter.export_tables_with_patterns(
            frame_data,
            pattern_data['patterns'],
            pattern_data['references'],
            ca65_output
        )
        self.assertTrue(os.path.exists(ca65_output), "CA65 file not created")
        
        # 7. Verify binary output
        self.verify_nsf_binary(nsf_output)
        self.verify_ca65_assembly(ca65_output)

    # [Previous test methods remain unchanged]
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

if __name__ == '__main__':
    unittest.main()
