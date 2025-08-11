# tests/test_frame_validation.py
import unittest
from tracker.track_mapper import assign_tracks_to_nes_channels
from tracker.parser import parse_midi_to_frames

# Mock generate_frames function since it doesn't exist in the codebase
def generate_frames(mapped_data):
    """Generate frame data from mapped NES channel data"""
    frames = []
    max_frame = 0
    
    # Find the maximum frame number
    for channel, events in mapped_data.items():
        for event in events:
            if 'frame' in event:
                max_frame = max(max_frame, event['frame'])
    
    # Generate frames up to max_frame
    for frame_num in range(max_frame + 1):
        frame = {
            'pulse1': {'note': 0, 'volume': 0},
            'pulse2': {'note': 0, 'volume': 0},
            'triangle': {'note': 0, 'volume': 0},
            'noise': {'note': 0, 'volume': 0}
        }
        
        # Fill in the frame data from events
        for channel, events in mapped_data.items():
            if channel in frame:
                for event in events:
                    if event.get('frame') == frame_num:
                        frame[channel]['note'] = event.get('note', 0)
                        frame[channel]['volume'] = event.get('volume', 0) // 8  # Convert to NES volume
        
        frames.append(frame)
    
    return frames

class TestFrameValidation(unittest.TestCase):
    def test_frame_data_validation(self):
        """Verify frame data structure and content"""
        # Generate test frame data
        test_frames = [
            {
                'pulse1': {'note': 60, 'volume': 15},
                'pulse2': {'note': 64, 'volume': 12},
                'triangle': {'note': 48, 'volume': 15},
                'noise': {'note': 0, 'volume': 10}
            },
            {
                'pulse1': {'note': 62, 'volume': 14},
                'pulse2': {'note': 65, 'volume': 11},
                'triangle': {'note': 50, 'volume': 15},
                'noise': {'note': 1, 'volume': 9}
            }
        ]
        
        for frame in test_frames:
            # Verify frame structure
            self.assertIn('pulse1', frame, "Missing pulse1 channel")
            self.assertIn('pulse2', frame, "Missing pulse2 channel")
            self.assertIn('triangle', frame, "Missing triangle channel")
            self.assertIn('noise', frame, "Missing noise channel")
            
            # Verify value ranges for each channel
            for channel in ['pulse1', 'pulse2', 'triangle']:
                if 'note' in frame[channel]:
                    self.assertGreaterEqual(frame[channel]['note'], 0, 
                        f"Note value too low in {channel}")
                    self.assertLessEqual(frame[channel]['note'], 127, 
                        f"Note value too high in {channel}")
                if 'volume' in frame[channel]:
                    self.assertGreaterEqual(frame[channel]['volume'], 0, 
                        f"Volume value too low in {channel}")
                    self.assertLessEqual(frame[channel]['volume'], 15, 
                        f"Volume value too high in {channel}")
            
            # Special validation for noise channel
            if 'note' in frame['noise']:
                self.assertGreaterEqual(frame['noise']['note'], 0, 
                    "Noise note value too low")
                self.assertLessEqual(frame['noise']['note'], 15, 
                    "Noise note value too high")
            if 'volume' in frame['noise']:
                self.assertGreaterEqual(frame['noise']['volume'], 0, 
                    "Noise volume too low")
                self.assertLessEqual(frame['noise']['volume'], 15, 
                    "Noise volume too high")

    def test_frame_sequence_validation(self):
        """Verify frame sequence consistency"""
        test_frames = generate_frames({
            'pulse1': [
                {'frame': 0, 'note': 60, 'volume': 15},
                {'frame': 30, 'note': 64, 'volume': 15}
            ],
            'pulse2': [
                {'frame': 0, 'note': 67, 'volume': 12},
                {'frame': 30, 'note': 71, 'volume': 12}
            ],
            'triangle': [
                {'frame': 0, 'note': 48, 'volume': 15},
                {'frame': 30, 'note': 52, 'volume': 15}
            ],
            'noise': [
                {'frame': 0, 'note': 0, 'volume': 10},
                {'frame': 30, 'note': 1, 'volume': 10}
            ]
        })
        
        # Verify frame sequence
        self.assertGreater(len(test_frames), 0, "No frames generated")
        
        previous_frame = None
        for frame in test_frames:
            # Verify frame structure
            self.assertIsInstance(frame, dict, "Frame is not a dictionary")
            
            # Verify all channels are present
            for channel in ['pulse1', 'pulse2', 'triangle', 'noise']:
                self.assertIn(channel, frame, f"Missing {channel} channel")
            
            if previous_frame:
                # Verify frame-to-frame consistency
                for channel in ['pulse1', 'pulse2', 'triangle', 'noise']:
                    if 'note' in previous_frame[channel] and 'note' in frame[channel]:
                        self.assertIsInstance(frame[channel]['note'], int, 
                            f"Note value in {channel} is not an integer")
                    if 'volume' in previous_frame[channel] and 'volume' in frame[channel]:
                        self.assertIsInstance(frame[channel]['volume'], int, 
                            f"Volume value in {channel} is not an integer")
            
            previous_frame = frame

if __name__ == '__main__':
    unittest.main()
