# New file: tests/test_famistudio_export.py

import unittest
import json
from pathlib import Path
from exporter.exporter_famistudio import generate_famistudio_txt, midi_note_to_famistudio

class TestFamiStudioExport(unittest.TestCase):
    def setUp(self):
        self.test_frames = {
            'pulse1': {
                '0': {'note': 60, 'volume': 15},  # Middle C
                '32': {'note': 67, 'volume': 12}  # G4
            },
            'pulse2': {
                '0': {'note': 64, 'volume': 10}   # E4
            },
            'triangle': {
                '0': {'note': 48, 'volume': 15}   # C3
            },
            'noise': {
                '16': {'volume': 12}
            },
            'dpcm': {
                '0': {'sample_id': 1}
            }
        }
        
    def test_midi_note_conversion(self):
        self.assertEqual(midi_note_to_famistudio(60), 'C-4')  # Middle C
        self.assertEqual(midi_note_to_famistudio(67), 'G-4')  # G4
        self.assertEqual(midi_note_to_famistudio(48), 'C-3')  # C3
        
    def test_generate_famistudio_txt(self):
        output = generate_famistudio_txt(
            self.test_frames,
            project_name="Test Project",
            author="Test Author",
            copyright="Test Copyright"
        )
        
        # Verify basic structure
        self.assertIn("# FamiStudio Text Export", output)
        self.assertIn("PROJECT", output)
        self.assertIn("INSTRUMENTS", output)
        self.assertIn("PATTERNS", output)
        
        # Verify project metadata
        self.assertIn("Test Project", output)
        self.assertIn("Test Author", output)
        self.assertIn("Test Copyright", output)
        
        # Verify note data
        self.assertIn("C-4 15", output)  # Middle C, full volume
        self.assertIn("G-4 12", output)  # G4, volume 12
        self.assertIn("C-3 15", output)  # C3, full volume
        
    def test_empty_frames(self):
        output = generate_famistudio_txt({})
        self.assertIn("# FamiStudio Text Export", output)
        self.assertIn("PROJECT", output)
        self.assertIn("INSTRUMENTS", output)
        
    def test_invalid_volume(self):
        frames = {
            'pulse1': {
                '0': {'note': 60, 'volume': 20}  # Volume > 15
            }
        }
        output = generate_famistudio_txt(frames)
        self.assertIn("C-4 15", output)  # Should clamp to 15
