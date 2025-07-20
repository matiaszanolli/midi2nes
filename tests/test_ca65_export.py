import unittest
import json
from pathlib import Path
from exporter.exporter_ca65 import CA65Exporter

class TestCA65Export(unittest.TestCase):
    def setUp(self):
        self.exporter = CA65Exporter()
        self.test_frames = {
            'pulse1': {
                '0': {'note': 60, 'volume': 15},  # Middle C
                '32': {'note': 67, 'volume': 12}  # G4
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
        # Create a temporary file for testing
        test_output = Path("test_output.asm")
        
        try:
            self.exporter.export_tables_with_patterns(
                self.test_frames,
                self.test_patterns,
                self.test_references,
                test_output
            )
            
            # Read the generated file
            with open(test_output, 'r') as f:
                output = f.read()
            
            # Test basic structure
            self.assertIn("; CA65 Assembly Export", output)
            self.assertIn(".segment \"RODATA\"", output)
            self.assertIn(".segment \"CODE\"", output)
            
            # Test pattern data
            self.assertIn("pattern_1:", output)
            
            # Test pattern reference table
            self.assertIn("pattern_refs:", output)
            
            # Test music routines
            self.assertIn("init_music:", output)
            self.assertIn("update_music:", output)
            self.assertIn("play_pattern_frame", output)
            
            # Test that we don't define variables (should be in main.asm)
            self.assertNotIn(".segment \"ZEROPAGE\"", output)
            self.assertNotIn(".res", output)
            
            # Test that we don't export variables (should be in main.asm)
            self.assertNotIn(".exportzp", output)
            
            # Test that we use variables from main.asm
            self.assertIn("frame_counter", output)
            self.assertIn("ptr1", output)
            self.assertIn("temp1", output)
            self.assertIn("temp2", output)
            
        finally:
            # Clean up
            if test_output.exists():
                test_output.unlink()
                
    def test_empty_patterns(self):
        test_output = Path("test_empty.asm")
        
        try:
            self.exporter.export_tables_with_patterns(
                {},  # Empty frames
                {},  # Empty patterns
                {},  # Empty references
                test_output
            )
            
            with open(test_output, 'r') as f:
                output = f.read()
            
            # Should still have basic structure
            self.assertIn("; CA65 Assembly Export", output)
            self.assertIn(".segment \"RODATA\"", output)
            self.assertIn(".segment \"CODE\"", output)
            self.assertIn("pattern_refs:", output)
            
            # Should have empty pattern reference table
            self.assertIn("    .word 0", output)
            self.assertIn("    .byte 0", output)
            
        finally:
            # Clean up
            if test_output.exists():
                test_output.unlink()

if __name__ == '__main__':
    unittest.main()
