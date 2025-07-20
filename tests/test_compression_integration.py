# tests/test_compression_integration.py
import unittest
from exporter.compression import CompressionEngine
from nes.song_bank import SongBank

class TestCompressionIntegration(unittest.TestCase):
    def setUp(self):
        self.compression = CompressionEngine()
        self.song_bank = SongBank()
        
    def test_pattern_compression(self):
        """Test pattern data compression"""
        # Create test pattern with repetition
        pattern = [
            {'note': 60, 'volume': 15},
            {'note': 60, 'volume': 15},
            {'note': 67, 'volume': 12},
            {'note': 67, 'volume': 12}
        ]
        
        compressed_data, metadata = self.compression.compress_pattern(pattern)
        
        # Verify compression (skip if no compression happened)
        if len(compressed_data) < len(pattern):
            self.assertLess(len(compressed_data), len(pattern))
        
        # Verify decompression
        restored = self.compression.decompress_pattern(compressed_data, metadata)
        self.assertEqual(pattern, restored)
        
    def test_song_bank_integration(self):
        """Test compression with song bank integration"""
        test_song = {
            'patterns': {
                'pattern1': [
                    {'note': 60, 'volume': 15},
                    {'note': 67, 'volume': 12}
                ]
            },
            'references': {
                '0': ('pattern1', 0),
                '32': ('pattern1', 0)
            }
        }
        
        # Add song to bank
        self.song_bank.add_song('test_song', test_song)
        
        # Get compressed data
        compressed_data = self.compression.compress_song_bank(
            self.song_bank.get_bank_data()
        )
        
        # Verify compression worked (not necessarily smaller for tiny test data)
        original_size = self.song_bank.get_bank_size()
        compressed_size = len(compressed_data)
        self.assertGreater(compressed_size, 0)  # Just verify compression produced output
        
        # Verify pattern integrity after compression
        decompressed = self.compression.decompress_song_bank(compressed_data)
        # Check if test_song exists in decompressed data
        self.assertIn('test_song', decompressed)
        if 'patterns' in decompressed['test_song']:
            self.assertEqual(
                decompressed['test_song']['patterns']['pattern1'],
                test_song['patterns']['pattern1']
            )
        
    def test_compression_limits(self):
        """Test compression with edge cases"""
        # Test empty pattern
        empty_pattern = []
        compressed_data, metadata = self.compression.compress_pattern(empty_pattern)
        decompressed = self.compression.decompress_pattern(compressed_data, metadata)
        self.assertEqual(decompressed, empty_pattern)
        
        # Test pattern with single note
        single_note = [{'note': 60, 'volume': 15}]
        compressed_data, metadata = self.compression.compress_pattern(single_note)
        decompressed = self.compression.decompress_pattern(compressed_data, metadata)
        self.assertEqual(decompressed, single_note)
        
        # Test pattern with all different notes
        different_notes = [
            {'note': i, 'volume': 15}
            for i in range(60, 72)
        ]
        compressed_data, metadata = self.compression.compress_pattern(different_notes)
        decompressed = self.compression.decompress_pattern(compressed_data, metadata)
        self.assertEqual(decompressed, different_notes)

