# tests/test_pitch_table_integration.py
import unittest
from nes.pitch_table import PitchProcessor, CPU_CLOCK_RATE

class TestPitchTableIntegration(unittest.TestCase):
    def setUp(self):
        self.pitch_processor = PitchProcessor()
        
    def test_note_to_timer_conversion(self):
        """Test MIDI note to NES timer value conversion"""
        # Test all notes in the pulse channel's valid range (24-108, #41/NH-11)
        for note in range(24, 109):
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
            
    def test_out_of_pulse_range_notes_are_clamped_not_rejected(self):
        """Regression (#41/NH-11): note_to_timer used to raise for MIDI notes
        96-127, even though CHANNEL_RANGES/channel_ranges declare pulse's
        valid range as (24, 108) and the note table is generated for the full
        0-127 range. Legal pulse notes must clamp like get_channel_pitch,
        not raise."""
        # Below pulse's floor clamps up to note 24's timer.
        self.assertEqual(self.pitch_processor.note_to_timer(0),
                          self.pitch_processor.note_to_timer(24))
        self.assertEqual(self.pitch_processor.note_to_timer(23),
                          self.pitch_processor.note_to_timer(24))
        # 96-108 (previously rejected) are legal pulse notes and must not raise.
        for note in (96, 100, 108):
            timer = self.pitch_processor.note_to_timer(note)
            self.assertGreater(timer, 0)
            self.assertLessEqual(timer, 0x7FF)
        # Above pulse's ceiling clamps down to note 108's timer.
        self.assertEqual(self.pitch_processor.note_to_timer(127),
                          self.pitch_processor.note_to_timer(108))

    def test_invalid_midi_protocol_notes_still_raise(self):
        """A genuinely invalid MIDI value (outside 0-127) still raises -- only
        the NES-specific 24-95 sub-range guard was wrong, not the MIDI
        protocol bound."""
        for note in (-1, 128, 200):
            with self.assertRaises(ValueError):
                self.pitch_processor.note_to_timer(note)

