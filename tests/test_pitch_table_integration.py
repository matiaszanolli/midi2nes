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
            
    def test_invalid_notes(self):
        """Test handling of notes outside valid range"""
        invalid_notes = [-1, 0, 23, 96, 127, 128]
        for note in invalid_notes:
            with self.assertRaises(ValueError):
                self.pitch_processor.note_to_timer(note)

