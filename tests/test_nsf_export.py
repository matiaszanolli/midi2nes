# New file: tests/test_nsf_export.py

import unittest
import os
from pathlib import Path
from exporter.exporter_nsf import NSFExporter, NSFHeader

class TestNSFExport(unittest.TestCase):
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
        self.test_output = "test_output.nsf"

    def tearDown(self):
        # Clean up test file
        if os.path.exists(self.test_output):
            os.remove(self.test_output)

    def test_nsf_header(self):
        header = NSFHeader()
        header.song_name = "Test Song"
        header.artist_name = "Test Artist"
        header.copyright = "Test Copyright"
        
        packed = header.pack()
        
        # Verify header size
        self.assertEqual(len(packed), 128)
        
        # Verify magic number
        self.assertEqual(packed[:5], b'NESM\x1a')
        
        # Verify strings
        self.assertIn(b'Test Song', packed)
        self.assertIn(b'Test Artist', packed)
        self.assertIn(b'Test Copyright', packed)

    def test_nsf_export(self):
        exporter = NSFExporter()
        exporter.export(
            self.test_frames,
            self.test_output,
            song_name="Test Song",
            artist="Test Artist",
            copyright="Test Copyright"
        )
        
        # Verify file exists
        self.assertTrue(os.path.exists(self.test_output))
        
        # Verify file size
        file_size = os.path.getsize(self.test_output)
        self.assertGreater(file_size, 128)  # Should be larger than header
        
        # Read and verify header
        with open(self.test_output, 'rb') as f:
            header = f.read(128)
            self.assertEqual(header[:5], b'NESM\x1a')
            self.assertIn(b'Test Song', header)

    def test_empty_frames(self):
        exporter = NSFExporter()
        exporter.export({}, self.test_output)
        
        # Verify file exists and has minimum size
        self.assertTrue(os.path.exists(self.test_output))
        self.assertGreater(os.path.getsize(self.test_output), 128)

    def test_frame_conversion(self):
        exporter = NSFExporter()
        binary_data = exporter._convert_frames_to_binary(self.test_frames)
        
        # Verify we have data for all channels
        self.assertEqual(len(binary_data), 5)
        
        # Verify each channel ends with marker
        for channel_data in binary_data:
            self.assertEqual(channel_data[-1], 0xFF)

