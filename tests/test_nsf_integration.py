# tests/test_nsf_integration.py
import unittest
import tempfile
from pathlib import Path
from exporter.exporter_nsf import NSFExporter
from nes.project_builder import NESProjectBuilder

class TestNSFIntegration(unittest.TestCase):
    def setUp(self):
        self.exporter = NSFExporter()
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir)
        
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
        
    def test_nsf_header_generation(self):
        """Test NSF header generation with various metadata"""
        test_data = {
            'title': 'Test Song',
            'artist': 'Test Artist',
            'copyright': '2024'
        }
        nsf_file = self.project_path / "test.nsf"
        self.exporter.export_nsf(test_data, nsf_file)
        
        with open(nsf_file, 'rb') as f:
            header = f.read(128)  # NSF header is 128 bytes
            # Verify NSF magic number (5 bytes)
            self.assertEqual(header[:5], b'NESM\x1a')
            # Verify version number
            self.assertEqual(header[5], 1)
            # Verify number of songs
            self.assertEqual(header[6], 1)
            # Verify starting song
            self.assertEqual(header[7], 1)
            
    def test_bank_switching(self):
        """Test NSF bank switching configuration"""
        large_data = {
            'patterns': {f'pattern_{i}': {'data': [0] * 1024} for i in range(16)}
        }
        nsf_file = self.project_path / "large.nsf"
        self.exporter.export_nsf(large_data, nsf_file)
        
        with open(nsf_file, 'rb') as f:
            header = f.read(128)
            # Verify bank switching is enabled
            self.assertNotEqual(header[0x70:0x78], b'\x00' * 8)
            
    def test_load_address(self):
        """Test NSF load address configuration"""
        test_data = {'load_address': 0x8000}
        nsf_file = self.project_path / "load.nsf"
        self.exporter.export_nsf(test_data, nsf_file)
        
        with open(nsf_file, 'rb') as f:
            header = f.read(128)
            load_addr = int.from_bytes(header[0x08:0x0A], byteorder='little')
            self.assertEqual(load_addr, 0x8000)
