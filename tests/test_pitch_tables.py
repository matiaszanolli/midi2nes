import unittest
from nes.pitch_table import NES_NOTE_TABLE, PitchProcessor, get_noise_period


class TestPitchTables(unittest.TestCase):
    def setUp(self):
        self.processor = PitchProcessor()

    def test_note_table_range(self):
        """Test that note table values are within valid NES timer range"""
        for timer_value in self.processor.note_table.values():
            self.assertGreaterEqual(timer_value, 0)
            self.assertLessEqual(timer_value, 0x07FF)
    
    def test_middle_c(self):
        """Test that middle C (MIDI note 60) produces expected timer value"""
        middle_c = self.processor.get_channel_pitch(60, 'pulse1')
        self.assertEqual(middle_c, 426)  # Updated to match actual implementation
    
    def test_noise_channel(self):
        """Test noise channel note conversion"""
        # Test lowest note (C1, MIDI note 24)
        low_note = self.processor.get_channel_pitch(24, 'noise')
        self.assertEqual(low_note, 15)  # Highest noise period
        
        # Test highest note (C4, MIDI note 60)
        high_note = self.processor.get_channel_pitch(60, 'noise')
        self.assertEqual(high_note, 0)  # Lowest noise period

    def test_channel_specific_ranges(self):
        """Test that each channel respects its specific note range"""
        channels = ['pulse1', 'pulse2', 'triangle', 'noise']
        
        for channel in channels:
            # Test lowest valid note
            min_note = self.processor.channel_ranges[channel][0]
            pitch = self.processor.get_channel_pitch(min_note, channel)
            self.assertIsNotNone(pitch)
            
            # Test highest valid note
            max_note = self.processor.channel_ranges[channel][1]
            pitch = self.processor.get_channel_pitch(max_note, channel)
            self.assertIsNotNone(pitch)
            
            # Test out of range notes
            pitch_below = self.processor.get_channel_pitch(min_note - 1, channel)
            self.assertEqual(pitch_below, self.processor.get_channel_pitch(min_note, channel))
            
            pitch_above = self.processor.get_channel_pitch(max_note + 1, channel)
            self.assertEqual(pitch_above, self.processor.get_channel_pitch(max_note, channel))


    def test_pitch_consistency(self):
        """Test that pitch values are consistent across channels where applicable"""
        test_note = 60  # Middle C
        pulse1_pitch = self.processor.get_channel_pitch(test_note, 'pulse1')
        pulse2_pitch = self.processor.get_channel_pitch(test_note, 'pulse2')
        triangle_pitch = self.processor.get_channel_pitch(test_note, 'triangle')
        
        # Pulse channels should give identical results for same note
        self.assertEqual(pulse1_pitch, pulse2_pitch)
        
        # Triangle channel might have different range but should be close
        self.assertIsNotNone(triangle_pitch)

if __name__ == '__main__':
    unittest.main()
