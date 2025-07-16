import unittest
from nes_pitch_table import NES_NOTE_TABLE, PitchProcessor, get_noise_period


class TestPitchTables(unittest.TestCase):
    def setUp(self):
        self.processor = PitchProcessor()
        
    def test_note_table_range(self):
        """Test that note table values are within valid NES timer range"""
        for timer_value in NES_NOTE_TABLE.values():
            self.assertGreaterEqual(timer_value, 0)
            self.assertLessEqual(timer_value, 0x07FF)
    
    def test_middle_c(self):
        """Test that middle C (MIDI note 60) produces expected timer value"""
        middle_c = self.processor.get_channel_pitch(60, "pulse1")
        # Middle C should be approximately timer value 0x0A2E
        self.assertAlmostEqual(middle_c, 0x0A2E, delta=1)
    
    def test_noise_channel(self):
        """Test noise channel note conversion"""
        # Test lowest note
        low_note = get_noise_period(24)  # C1
        self.assertEqual(low_note, 0xF)
        
        # Test highest note
        high_note = get_noise_period(60)  # C4
        self.assertEqual(high_note, 0x0)
    
    def test_pitch_bend(self):
        """Test pitch bend calculations"""
        base_pitch = self.processor.get_channel_pitch(60, "pulse1")
        
        # No bend
        self.assertEqual(
            self.processor.apply_pitch_bend(base_pitch, 0, "pulse1"),
            base_pitch
        )
        
        # Maximum bend up (should be higher frequency = lower timer value)
        bent_up = self.processor.apply_pitch_bend(base_pitch, 8191, "pulse1")
        self.assertLess(bent_up, base_pitch)
        
        # Maximum bend down (should be lower frequency = higher timer value)
        bent_down = self.processor.apply_pitch_bend(base_pitch, -8192, "pulse1")
        self.assertGreater(bent_down, base_pitch)

if __name__ == '__main__':
    unittest.main()
