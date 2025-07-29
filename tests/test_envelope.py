# tests/test_envelope.py
import unittest
import sys
import os

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from nes.envelope_processor import EnvelopeProcessor

class TestEnvelopeProcessor(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.processor = EnvelopeProcessor()

    def test_default_envelope_definitions(self):
        """Test that default envelope definitions are properly initialized"""
        expected_envelopes = {
            "default", "piano", "pad", "pluck", "percussion"
        }
        self.assertEqual(set(self.processor.envelope_definitions.keys()), 
                        expected_envelopes)

    def test_default_envelope_behavior(self):
        """Test default envelope behavior (constant volume)"""
        envelope_type = "default"
        # Test at different frame offsets
        self.assertEqual(self.processor.get_envelope_value(envelope_type, 0, 10), 15)
        self.assertEqual(self.processor.get_envelope_value(envelope_type, 5, 10), 15)
        self.assertEqual(self.processor.get_envelope_value(envelope_type, 9, 10), 15)

    def test_piano_envelope(self):
        """Test piano envelope characteristics"""
        envelope_type = "piano"
        note_duration = 30  # frames
        
        # Test attack phase (should reach max volume quickly)
        attack_value = self.processor.get_envelope_value(envelope_type, 0, note_duration)
        self.assertLess(attack_value, 15)  # Should start below max
        
        # Test decay and sustain
        sustain_value = self.processor.get_envelope_value(envelope_type, 5, note_duration)
        self.assertEqual(sustain_value, 10)  # Piano sustain level
        
        # Test release
        release_value = self.processor.get_envelope_value(envelope_type, 29, note_duration)
        self.assertLess(release_value, sustain_value)  # Should decrease during release

    def test_percussion_envelope(self):
        """Test percussion envelope (immediate attack, quick decay)"""
        envelope_type = "percussion"
        note_duration = 10
        
        # Test immediate attack - should start at maximum volume
        start_value = self.processor.get_envelope_value(envelope_type, 0, note_duration)
        self.assertEqual(start_value, 15)  # Should start at max volume (15)
        
        # Test decay phase - should gradually decrease
        next_value = self.processor.get_envelope_value(envelope_type, 1, note_duration)
        self.assertLess(next_value, 15)  # Should be less than initial value
        self.assertGreater(next_value, 0)  # But still greater than 0
        
        # Test end of decay
        end_value = self.processor.get_envelope_value(envelope_type, note_duration - 1, note_duration)
        self.assertEqual(end_value, 0)  # Should reach zero by the end


    def test_control_byte_generation(self):
        """Test envelope control byte generation"""
        envelope_type = "default"
        frame_offset = 0
        note_duration = 10
        
        # Test with different duty cycles
        for duty in range(4):
            control_byte = self.processor.get_envelope_control_byte(
                envelope_type, frame_offset, note_duration, duty_cycle=duty
            )
            
            # Check duty cycle bits (bits 6-7)
            expected_duty_bits = (duty & 0x03) << 6
            self.assertEqual(control_byte & 0xC0, expected_duty_bits)
            
            # Check envelope bits (bits 4-5 should be 0x30)
            self.assertEqual(control_byte & 0x30, 0x30)
            
            # Check volume bits (bits 0-3)
            volume = control_byte & 0x0F
            self.assertEqual(volume, 15)  # Default envelope has full volume

    def test_invalid_envelope_type(self):
        """Test handling of invalid envelope types"""
        # Should fall back to default envelope
        value = self.processor.get_envelope_value("nonexistent", 0, 10)
        self.assertEqual(value, 15)  # Default envelope has constant volume of 15

    def test_envelope_phases(self):
        """Test all envelope phases for pad envelope"""
        envelope_type = "pad"
        note_duration = 30
        
        # Test attack phase (0-4 frames)
        attack_start = self.processor.get_envelope_value(envelope_type, 0, note_duration)
        attack_mid = self.processor.get_envelope_value(envelope_type, 2, note_duration)
        attack_end = self.processor.get_envelope_value(envelope_type, 4, note_duration)
        self.assertLess(attack_start, attack_mid)
        self.assertLess(attack_mid, attack_end)
        
        # Test decay phase (5-14 frames)
        decay_start = self.processor.get_envelope_value(envelope_type, 5, note_duration)
        decay_end = self.processor.get_envelope_value(envelope_type, 14, note_duration)
        self.assertGreater(decay_start, decay_end)
        
        # Test sustain phase (15-24 frames)
        sustain_start = self.processor.get_envelope_value(envelope_type, 15, note_duration)
        sustain_end = self.processor.get_envelope_value(envelope_type, 24, note_duration)
        self.assertEqual(sustain_start, sustain_end)
        self.assertEqual(sustain_start, 8)  # Pad sustain level
        
        # Test release phase (25-29 frames)
        release_start = self.processor.get_envelope_value(envelope_type, 25, note_duration)
        release_end = self.processor.get_envelope_value(envelope_type, 29, note_duration)
        self.assertGreater(release_start, release_end)
        self.assertGreater(release_end, 0)  # Should not necessarily end at zero

if __name__ == '__main__':
    unittest.main()
