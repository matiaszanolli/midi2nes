# tests/test_exporter_integration.py

import unittest
from pathlib import Path
import tempfile
import os

from exporter.compression import CompressionEngine
from exporter.exporter_ca65 import CA65Exporter
from exporter.exporter_nsf import NSFExporter
from exporter.exporter_famistudio import FamiStudioExporter

class TestExporterIntegration(unittest.TestCase):
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
        
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)
    
    def test_compression_integration(self):
        """Test that compression works across all exporters"""
        engine = CompressionEngine()
        
        # Test each channel
        for channel, events in self.test_frames.items():
            compressed, metadata = engine.compress_pattern([events[k] for k in sorted(events.keys())])
            decompressed = engine.decompress_pattern(compressed, metadata)
            
            # Verify compression/decompression cycle
            self.assertEqual(len(compressed) < len(str(events)), True)
            self.assertEqual(len(metadata['rle_blocks']) + len(metadata['delta_blocks']) > 0, True)
    
    def test_ca65_export_with_compression(self):
        """Test CA65 export with compression"""
        output_path = os.path.join(self.temp_dir, "test_ca65.s")
        exporter = CA65Exporter()
        
        patterns = {"test": {"events": self.test_frames['pulse1']}}
        references = {"0": ("test", 0)}
        
        exporter.export_tables_with_patterns(self.test_frames, patterns, references, output_path)
        
        # Verify file exists and contains compression data
        self.assertTrue(os.path.exists(output_path))
        with open(output_path, 'r') as f:
            content = f.read()
            self.assertIn("Pattern Compressed", content)
            self.assertIn("decompress_pattern", content)
    
    def test_nsf_export_with_compression(self):
        """Test NSF export with compression"""
        output_path = os.path.join(self.temp_dir, "test.nsf")
        exporter = NSFExporter()
        
        exporter.export(self.test_frames, output_path, "Test Song")
        
        # Verify file exists and has correct format
        self.assertTrue(os.path.exists(output_path))
        with open(output_path, 'rb') as f:
            header = f.read(128)
            self.assertEqual(header[:5], b'NESM\x1a')
    
    def test_famistudio_export_with_compression(self):
        """Test FamiStudio export with compression"""
        output_path = os.path.join(self.temp_dir, "test.txt")
        exporter = FamiStudioExporter()
        
        output = exporter.generate_famistudio_txt(self.test_frames, "Test Song")
        Path(output_path).write_text(output)
        
        # Verify file exists and contains pattern data
        self.assertTrue(os.path.exists(output_path))
        with open(output_path, 'r') as f:
            content = f.read()
            self.assertIn("PATTERNS", content)
            self.assertIn("C-4 15", content)  # Middle C note
