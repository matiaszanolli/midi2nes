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
        
    def test_nsf_export_unsupported(self):
        """Regression (EXP-05 / #81): NSF export is not a playable NSF and is now
        explicitly unsupported, so export_nsf must raise rather than write a file
        whose header looks valid but whose body is JSON-as-data."""
        nsf_file = self.project_path / "test.nsf"
        with self.assertRaises(NotImplementedError):
            self.exporter.export_nsf({'title': 'Test Song', 'artist': 'A'}, nsf_file)
        with self.assertRaises(NotImplementedError):
            self.exporter.export_nsf({'patterns': {f'p{i}': {'data': [0]} for i in range(16)}}, nsf_file)
        with self.assertRaises(NotImplementedError):
            self.exporter.export_nsf({'load_address': 0x8000}, nsf_file)
        self.assertFalse(nsf_file.exists())


if __name__ == '__main__':
    unittest.main()
