import unittest
import json
from pathlib import Path
from exporter.exporter_ca65 import CA65Exporter

class TestCA65Export(unittest.TestCase):
    def setUp(self):
        self.exporter = CA65Exporter()
        self.test_frames = {
            'pulse1': {
                '0': {'note': 60, 'volume': 15},
                '32': {'note': 67, 'volume': 12}
            }
        }
        self.test_patterns = {
            'pattern_1': {
                'events': [
                    {'note': 60, 'volume': 15},
                    {'note': 67, 'volume': 12}
                ]
            }
        }
        self.test_references = {
            '0': ('pattern_1', 0),
            '32': ('pattern_1', 1)
        }
        
    def test_midi_note_to_timer_value(self):
        # Test valid notes
        self.assertGreater(self.exporter.midi_note_to_timer_value(60), 0)  # Middle C
        self.assertGreater(self.exporter.midi_note_to_timer_value(67), 0)  # G4
        
        # Test invalid notes
        self.assertEqual(self.exporter.midi_note_to_timer_value(20), 0)  # Too low
        self.assertEqual(self.exporter.midi_note_to_timer_value(120), 0)  # Too high
        
    def test_export_tables_with_patterns(self):
        test_output = Path("test_output.asm")
        try:
            self.exporter.export_tables_with_patterns(
                self.test_frames,
                self.test_patterns,
                self.test_references,
                test_output
            )
            with open(test_output, 'r') as f:
                output = f.read()
                
            # Test file header and imports/exports
            self.assertIn("; CA65 Assembly Export", output)
            self.assertIn(".importzp ptr1, temp1, temp2, frame_counter", output)
            self.assertIn(".export init_music", output)
            self.assertIn(".export update_music", output)
            
            # Test segments
            self.assertIn(".segment \"RODATA\"", output)
            self.assertIn(".segment \"CODE\"", output)
            self.assertNotIn(".segment \"ZEROPAGE\"", output)
            
            # Test pattern data
            self.assertIn("pattern_1:", output)
            self.assertIn("pattern_refs:", output)
            
            # Test music engine routines
            self.assertIn("init_music:", output)
            self.assertIn("update_music:", output)
            self.assertIn("play_pattern_frame", output)
            
            # Test APU initialization values
            self.assertIn("sta $4015", output)  # APU enable
            self.assertIn("sta $4000", output)  # Pulse 1
            self.assertIn("sta $4004", output)  # Pulse 2
            self.assertIn("sta $4008", output)  # Triangle
            self.assertIn("sta $400C", output)  # Noise
            
            # Test frame counter handling
            self.assertIn("lda frame_counter", output)
            self.assertIn("inc frame_counter", output)
            self.assertIn("inc frame_counter+1", output)
            
            # Test pattern playback
            self.assertIn("lda pattern_refs,x", output)
            self.assertIn("sta ptr1", output)
            self.assertIn("sta temp1", output)
            self.assertIn("sta temp2", output)
            
            # Test that we don't have any undefined values
            self.assertNotIn("lda\n", output)  # No empty LDA instructions
            self.assertNotIn("sta\n", output)  # No empty STA instructions
            
            # Test proper initialization values
            self.assertIn("lda #$0F", output)  # APU enable value
            self.assertIn("lda #$30", output)  # APU channel setup
            
        finally:
            if test_output.exists():
                test_output.unlink()
                
    def test_empty_patterns(self):
        test_output = Path("test_empty.asm")
        try:
            self.exporter.export_tables_with_patterns({}, {}, {}, test_output)
            with open(test_output, 'r') as f:
                output = f.read()
            
            # Basic structure should still be present
            self.assertIn(".segment \"RODATA\"", output)
            self.assertIn(".segment \"CODE\"", output)
            self.assertIn("pattern_refs:", output)
            
            # Should have proper imports/exports
            self.assertIn(".importzp ptr1, temp1, temp2, frame_counter", output)
            self.assertIn(".export init_music", output)
            self.assertIn(".export update_music", output)
            
            # Should have proper initialization
            self.assertIn("lda #$0F", output)  # APU enable value
            self.assertIn("lda #$30", output)  # APU channel setup
            
        finally:
            if test_output.exists():
                test_output.unlink()

if __name__ == '__main__':
    unittest.main()
