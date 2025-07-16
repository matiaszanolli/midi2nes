# tests/test_core.py
import unittest
from nes_emulator_core import NESEmulatorCore, EnvelopeProcessor
from nes_pitch_table import PitchProcessor

class TestNESCore(unittest.TestCase):
    def setUp(self):
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

    def test_frame_compilation(self):
        """Test basic frame compilation logic"""
        events = [
            {'frame': 0, 'note': 60, 'velocity': 100},  # Middle C
            {'frame': 4, 'note': 62, 'velocity': 100},  # D above middle C
        ]
        
        frames = self.emulator.compile_channel_to_frames(events, channel_type='pulse1')
        
        self.assertIn(0, frames)
        self.assertIn(4, frames)
        
        # Test that pitch values are correctly converted
        self.assertEqual(
            frames[0]['pitch'],
            self.emulator.pitch_processor.get_channel_pitch(60, 'pulse1')
        )
        self.assertEqual(
            frames[4]['pitch'],
            self.emulator.pitch_processor.get_channel_pitch(62, 'pulse1')
        )

    def test_basic_track_structure(self):
        """Test that process_all_tracks maintains expected channel structure"""
        result = self.emulator.process_all_tracks(self.test_tracks)
        
        expected_channels = {'pulse1', 'pulse2', 'triangle', 'noise', 'dpcm'}
        self.assertEqual(set(result.keys()), expected_channels)
        
        for channel in expected_channels:
            self.assertIsInstance(result[channel], dict)

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


class TestEnvelopeIntegration(unittest.TestCase):
    def setUp(self):
        self.emulator = NESEmulatorCore()
        
    def test_envelope_integration_basic(self):
        """Test basic envelope integration in frame compilation"""
        events = [{'frame': 0, 'note': 60, 'velocity': 100}]
        frames = self.emulator.compile_channel_to_frames(
            events, 
            channel_type='pulse1',
            sustain_frames=4
        )
        
        # Check frame 0 has correct envelope control byte
        self.assertIn('control', frames[0])
        control_byte = frames[0]['control']
        
        # Default envelope with duty cycle 2
        expected_control = (2 << 6) | 0x30 | 15  # duty(2) << 6 | envelope_bits(0x30) | volume(15)
        self.assertEqual(control_byte, expected_control)

    def test_envelope_types(self):
        """Test different envelope types integration"""
        envelope_types = ['default', 'piano', 'pad', 'pluck', 'percussion']
        
        for env_type in envelope_types:
            events = [{
                'frame': 0,
                'note': 60,
                'velocity': 100,
                'envelope_type': env_type
            }]
            
            frames = self.emulator.compile_channel_to_frames(
                events,
                channel_type='pulse1',
                sustain_frames=10
            )
            
            # Verify envelope processing for each frame
            for frame in range(10):
                self.assertIn(frame, frames)
                self.assertIn('control', frames[frame])
                
                # Get the actual volume from the control byte
                volume = frames[frame]['control'] & 0x0F
                
                # Verify volume is within valid range
                self.assertGreaterEqual(volume, 0)
                self.assertLessEqual(volume, 15)
                
                # Verify envelope characteristics
                if env_type == 'default':
                    # Default envelope should maintain full volume
                    self.assertEqual(volume, 15)
                elif env_type == 'pluck':
                    # Pluck should decrease over time
                    if frame > 0:
                        prev_volume = frames[frame-1]['control'] & 0x0F
                        self.assertLessEqual(volume, prev_volume)

    def test_duty_cycle_integration(self):
        """Test duty cycle integration with envelope"""
        events = [{'frame': 0, 'note': 60, 'velocity': 100}]
        
        for duty in range(4):  # Test all valid duty cycles (0-3)
            frames = self.emulator.compile_channel_to_frames(
                events,
                channel_type='pulse1',
                default_duty=duty
            )
            
            control_byte = frames[0]['control']
            actual_duty = (control_byte >> 6) & 0x03
            self.assertEqual(actual_duty, duty)

    def test_envelope_timing(self):
        """Test envelope timing and transitions"""
        events = [{
            'frame': 0,
            'note': 60,
            'velocity': 100,
            'envelope_type': 'piano'  # Using piano envelope for clear ADSR
        }]
        
        frames = self.emulator.compile_channel_to_frames(
            events,
            channel_type='pulse1',
            sustain_frames=20
        )
        
        # Test attack phase (frame 0-1)
        attack_volume = frames[0]['control'] & 0x0F
        self.assertLess(attack_volume, 15)  # Should start below max volume
        
        # Test decay phase (frames 1-4)
        decay_start_volume = frames[1]['control'] & 0x0F
        decay_end_volume = frames[4]['control'] & 0x0F
        self.assertGreater(decay_start_volume, decay_end_volume)
        
        # Test sustain phase (frames 4-18)
        sustain_volume = frames[10]['control'] & 0x0F
        self.assertEqual(sustain_volume, 10)  # Piano envelope sustain level
        
        # Test release phase (frames 18-20)
        release_start_volume = frames[18]['control'] & 0x0F
        release_end_volume = frames[19]['control'] & 0x0F
        self.assertGreater(release_start_volume, release_end_volume)

    def test_multiple_notes_envelope(self):
        """Test envelope processing with multiple sequential notes"""
        events = [
            {'frame': 0, 'note': 60, 'velocity': 100, 'envelope_type': 'piano'},
            {'frame': 5, 'note': 62, 'velocity': 100, 'envelope_type': 'piano'}
        ]
        
        frames = self.emulator.compile_channel_to_frames(
            events,
            channel_type='pulse1',
            sustain_frames=10
        )
        
        # First note should be cut off when second note starts
        self.assertNotEqual(
            frames[4]['control'] & 0x0F,  # Last frame of first note
            frames[5]['control'] & 0x0F   # First frame of second note
        )
        
        # Second note should start its own envelope
        second_note_volume = frames[5]['control'] & 0x0F
        self.assertLess(second_note_volume, 15)  # Should start in attack phase
