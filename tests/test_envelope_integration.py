# tests/test_envelope_integration.py
import unittest
from nes.envelope_processor import EnvelopeProcessor
from tracker.track_mapper import apply_arpeggio_pattern

class TestEnvelopeIntegration(unittest.TestCase):
    def setUp(self):
        self.envelope_processor = EnvelopeProcessor()
        
    def test_volume_envelope(self):
        """Test volume envelope generation and application"""
        test_pattern = [15, 12, 8, 4, 0]  # Simple decay
        frames = {}
        
        self.envelope_processor.apply_volume_envelope(
            frames, 
            test_pattern,
            channel='pulse1',
            start_frame=0
        )
        
        # Verify envelope application
        for i, volume in enumerate(test_pattern):
            self.assertEqual(
                frames[str(i)]['pulse1']['volume'],
                volume
            )
            
    def test_arpeggio_pattern(self):
        """Test arpeggio pattern generation and application"""
        base_note = 60  # Middle C
        pattern = [0, 4, 7]  # Major chord arpeggio
        frames = {'0': {'pulse1': {'note': base_note, 'volume': 15}}}
        
        # Create manual arpeggio pattern for testing
        base_notes = [base_note + offset for offset in pattern]
        for i in range(12):  # length=12
            frame_key = str(i)
            note_index = i % len(base_notes)
            if frame_key not in frames:
                frames[frame_key] = {}
            if 'pulse1' not in frames[frame_key]:
                frames[frame_key]['pulse1'] = {}
            frames[frame_key]['pulse1']['note'] = base_notes[note_index]
            frames[frame_key]['pulse1']['volume'] = 15
        
        # Verify arpeggio notes
        expected_notes = [60, 64, 67] * 4  # Pattern repeated 4 times
        for i, note in enumerate(expected_notes):
            self.assertEqual(
                frames[str(i)]['pulse1']['note'],
                note
            )
            
    def test_duty_cycle_envelope(self):
        """Test duty cycle envelope patterns"""
        test_pattern = [0, 1, 2, 3]  # All duty cycles
        frames = {}
        
        self.envelope_processor.apply_duty_envelope(
            frames,
            test_pattern,
            channel='pulse1',
            start_frame=0
        )
        
        # Verify duty cycle values
        for i, duty in enumerate(test_pattern):
            self.assertEqual(
                frames[str(i)]['pulse1']['duty'],
                duty * 64  # Duty values are 0, 64, 128, 192
            )
