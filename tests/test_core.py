import unittest
import sys
import os

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from nes_emulator_core import process_all_tracks, compile_channel_to_frames

class TestNESCore(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.test_tracks = {
            'pulse1': [{'frame': 0, 'note': 60, 'velocity': 100}],
            'pulse2': [{'frame': 0, 'note': 64, 'velocity': 100}],
            'triangle': [{'frame': 0, 'note': 48, 'velocity': 100}],
            'noise': [{'frame': 0, 'note': 60, 'velocity': 100}],
            'dpcm': [{'frame': 0, 'note': 60, 'velocity': 100}]
        }

    def test_basic_track_structure(self):
        """Test that process_all_tracks maintains expected channel structure"""
        result = process_all_tracks(self.test_tracks)
        
        # Test channel presence
        expected_channels = {'pulse1', 'pulse2', 'triangle', 'noise', 'dpcm'}
        self.assertEqual(set(result.keys()), expected_channels)
        
        # Test that each channel has frame data
        for channel in expected_channels:
            self.assertIsInstance(result[channel], dict)

    def test_frame_compilation(self):
        """Test basic frame compilation logic"""
        events = [
            {'frame': 0, 'note': 60, 'velocity': 100},
            {'frame': 4, 'note': 62, 'velocity': 100},
        ]
        
        frames = compile_channel_to_frames(events, channel_type='pulse1')
        
        # Test frame timing
        self.assertIn(0, frames)  # First note starts at frame 0
        self.assertIn(4, frames)  # Second note starts at frame 4

    def test_empty_track_handling(self):
        """Test handling of empty tracks"""
        empty_tracks = {
            'pulse1': [],
            'pulse2': [],
            'triangle': [],
            'noise': [],
            'dpcm': []
        }
        
        result = process_all_tracks(empty_tracks)
        
        # Test that all channels are present even if empty
        self.assertEqual(set(result.keys()), 
                        {'pulse1', 'pulse2', 'triangle', 'noise', 'dpcm'})
        
        # Test that empty channels have empty frame dictionaries
        for channel_frames in result.values():
            self.assertIsInstance(channel_frames, dict)
            self.assertEqual(len(channel_frames), 0)

    def test_basic_note_processing(self):
        """Test basic note event processing"""
        events = [{'frame': 0, 'note': 60, 'velocity': 100}]
        
        frames = compile_channel_to_frames(events, channel_type='pulse1')
        
        # Test that frame 0 exists and has basic note data
        self.assertIn(0, frames)
        frame_data = frames[0]
        self.assertIn('note', frame_data)
        self.assertEqual(frame_data['note'], 60)

if __name__ == '__main__':
    unittest.main()
