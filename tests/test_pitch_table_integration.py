# tests/test_pitch_table_integration.py
import unittest
from nes.pitch_table import PitchProcessor, CPU_CLOCK_RATE

class TestPitchTableIntegration(unittest.TestCase):
    def setUp(self):
        self.pitch_processor = PitchProcessor()
        
    def test_note_to_timer_conversion(self):
        """Test MIDI note to NES timer value conversion"""
        # Test all notes in valid range
        for note in range(24, 96):  # MIDI notes C1 to C7
            timer = self.pitch_processor.note_to_timer(note)
            self.assertGreater(timer, 0)
            self.assertLessEqual(timer, 0x7FF)  # Max timer value
            
    def test_frequency_accuracy(self):
        """Test frequency accuracy of generated timer values"""
        test_frequencies = [
            (440.0, 69),  # A4
            (261.63, 60), # C4
            (329.63, 64)  # E4
        ]
        
        for freq, midi_note in test_frequencies:
            timer = self.pitch_processor.note_to_timer(midi_note)
            actual_freq = CPU_CLOCK_RATE / (16 * (timer + 1))
            # Allow 0.5% frequency deviation
            self.assertLess(abs(actual_freq - freq) / freq, 0.005)
            
    def test_out_of_range_notes_clamp(self):
        """Regression (#41/NH-11): note_to_timer clamps to the pulse channel
        range (24-108) instead of raising, matching the rest of the module's
        clamp policy. The old 24-95 guard wrongly rejected legal pulse notes."""
        table = self.pitch_processor.note_table
        # Legal pulse notes 96-108 (previously rejected by the stale 95 ceiling)
        # are now accepted and return their own table entry.
        for note in (96, 100, 108):
            self.assertEqual(self.pitch_processor.note_to_timer(note), table[note])
        # Below the range clamps up to 24; above (incl. non-MIDI values) clamps
        # down to 108 -- never raises.
        for low in (-5, 0, 23):
            self.assertEqual(self.pitch_processor.note_to_timer(low), table[24])
        for high in (109, 127, 128, 200):
            self.assertEqual(self.pitch_processor.note_to_timer(high), table[108])

