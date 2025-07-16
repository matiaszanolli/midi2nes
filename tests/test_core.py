# tests/test_core.py
import unittest
from nes_emulator_core import NESEmulatorCore, EnvelopeProcessor
from nes_pitch_table import PitchProcessor

class TestNESCore(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.emulator = NESEmulatorCore()
        self.test_tracks = {
            'pulse1': [{'frame': 0, 'note': 60, 'velocity': 100}],
            'pulse2': [{'frame': 0, 'note': 64, 'velocity': 100}],
            'triangle': [{'frame': 0, 'note': 48, 'velocity': 100}],
            'noise': [{'frame': 0, 'note': 60, 'velocity': 100}],
            'dpcm': [{'frame': 0, 'note': 60, 'velocity': 100}]
        }

    def test_pitch_processor_integration(self):
        """Test that PitchProcessor is properly integrated"""
        self.assertIsInstance(self.emulator.pitch_processor, PitchProcessor)
        
        # Test pitch conversion through the integrated pitch processor
        test_note = 60  # Middle C
        pitch = self.emulator.midi_to_nes_pitch(test_note, 'pulse1')
        expected_pitch = self.emulator.pitch_processor.get_channel_pitch(test_note, 'pulse1')
        self.assertEqual(pitch, expected_pitch)

    def test_basic_note_processing(self):
        """Test basic note event processing"""
        events = [{'frame': 0, 'note': 60, 'velocity': 100}]
        
        frames = self.emulator.compile_channel_to_frames(events, channel_type='pulse1')
        
        self.assertIn(0, frames)
        frame_data = frames[0]
        self.assertIn('pitch', frame_data)
        expected_pitch = self.emulator.pitch_processor.get_channel_pitch(60, 'pulse1')
        self.assertEqual(frame_data['pitch'], expected_pitch)


    def test_basic_note_processing(self):
        """Test basic note event processing"""
        events = [{'frame': 0, 'note': 60, 'velocity': 100}]
        
        frames = self.emulator.compile_channel_to_frames(events, channel_type='pulse1')
        
        self.assertIn(0, frames)
        frame_data = frames[0]
        self.assertIn('pitch', frame_data)
        # Middle C should be approximately timer value 0x0A2E
        self.assertEqual(frame_data['pitch'], 0x0A2E)

    def test_basic_track_structure(self):
        """Test that process_all_tracks maintains expected channel structure"""
        result = self.emulator.process_all_tracks(self.test_tracks)
        
        expected_channels = {'pulse1', 'pulse2', 'triangle', 'noise', 'dpcm'}
        self.assertEqual(set(result.keys()), expected_channels)
        
        for channel in expected_channels:
            self.assertIsInstance(result[channel], dict)

    def test_frame_compilation(self):
        """Test basic frame compilation logic"""
        events = [
            {'frame': 0, 'note': 60, 'velocity': 100},
            {'frame': 4, 'note': 62, 'velocity': 100},
        ]
        
        frames = self.emulator.compile_channel_to_frames(events, channel_type='pulse1')
        
        self.assertIn(0, frames)
        self.assertIn(4, frames)
        
        # Test that pitch values are correctly converted
        self.assertEqual(frames[0]['pitch'], 0x0A2E)  # Middle C
        self.assertEqual(frames[4]['pitch'], 0x0986)  # D above middle C

    def test_empty_track_handling(self):
        """Test handling of empty tracks"""
        empty_tracks = {
            'pulse1': [], 'pulse2': [], 'triangle': [],
            'noise': [], 'dpcm': []
        }
        
        result = self.emulator.process_all_tracks(empty_tracks)
        
        for channel_frames in result.values():
            self.assertIsInstance(channel_frames, dict)
            self.assertEqual(len(channel_frames), 0)

