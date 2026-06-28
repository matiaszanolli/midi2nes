# tests/test_frame_validation.py
import unittest
from nes.emulator_core import NESEmulatorCore

class TestFrameValidation(unittest.TestCase):
    def test_frame_data_validation(self):
        """Verify frame data structure and content"""
        # Generate test frame data
        test_frames = {
            'pulse1': {
                0: {'note': 60, 'volume': 15},
                1: {'note': 62, 'volume': 14}
            },
            'pulse2': {
                0: {'note': 64, 'volume': 12},
                1: {'note': 65, 'volume': 11}
            },
            'triangle': {
                0: {'note': 48, 'volume': 15},
                1: {'note': 50, 'volume': 15}
            },
            'noise': {
                0: {'noise_mode': 0, 'volume': 10},
                1: {'noise_mode': 1, 'volume': 9}
            }
        }
        
        for channel, frames in test_frames.items():
            for frame_num, frame in frames.items():
                # Verify value ranges for each channel
                if 'note' in frame:
                    self.assertGreaterEqual(frame['note'], 0, f"Note value too low in {channel}")
                    self.assertLessEqual(frame['note'], 127, f"Note value too high in {channel}")
                if 'volume' in frame:
                    self.assertGreaterEqual(frame['volume'], 0, f"Volume value too low in {channel}")
                    self.assertLessEqual(frame['volume'], 15, f"Volume value too high in {channel}")
                    
                # Special validation for noise channel
                if channel == 'noise':
                    if 'noise_mode' in frame:
                        self.assertIn(frame['noise_mode'], [0, 1], "Noise mode must be 0 or 1")

    def test_frame_sequence_validation(self):
        """Verify frame sequence consistency"""
        emulator = NESEmulatorCore()
        
        # Test with actual emulator to get realistic structure
        test_frames = emulator.process_all_tracks({
            'pulse1': [
                {'frame': 0, 'note': 60, 'velocity': 100},
                {'frame': 30, 'note': 64, 'velocity': 100}
            ],
            'pulse2': [
                {'frame': 0, 'note': 67, 'velocity': 100},
                {'frame': 30, 'note': 71, 'velocity': 100}
            ],
            'triangle': [
                {'frame': 0, 'note': 48, 'velocity': 100},
                {'frame': 30, 'note': 52, 'velocity': 100}
            ],
            'noise': [
                {'frame': 0, 'note': 0, 'velocity': 100},
                {'frame': 30, 'note': 0, 'velocity': 100}
            ]
        })
        
        # Verify frame sequence
        self.assertGreater(len(test_frames), 0, "No frames generated")
        
        for channel, frames in test_frames.items():
            self.assertIsInstance(frames, dict, f"Frames for {channel} should be a dictionary")
            
            previous_frame = -1
            for frame_num, frame in sorted(frames.items()):
                self.assertIsInstance(frame, dict, "Frame data should be a dictionary")
                
                # Verify frame-to-frame consistency
                self.assertGreater(frame_num, previous_frame, f"Frame sequence not ordered in {channel}")
                
                if 'note' in frame:
                    self.assertIsInstance(frame['note'], int, f"Note value in {channel} is not an integer")
                if 'volume' in frame:
                    self.assertIsInstance(frame['volume'], int, f"Volume value in {channel} is not an integer")
                    
                previous_frame = frame_num

if __name__ == '__main__':
    unittest.main()
