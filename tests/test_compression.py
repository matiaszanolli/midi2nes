# New file: tests/test_compression.py

import unittest
from exporter.compression import CompressionEngine

class TestCompressionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = CompressionEngine()
        self.test_pattern = [
            {'note': 60, 'volume': 15},              # C4
            {'note': 60, 'volume': 15},              # C4 (repeated)
            {'note': 60, 'volume': 15},              # C4 (repeated)
            {'note': 60, 'volume': 15},              # C4 (repeated)
            {'note': 62, 'volume': 14},              # D4 (step up)
            {'note': 64, 'volume': 13},              # E4 (step up)
            {'note': 65, 'volume': 12},              # F4 (step up)
            {'note': 67, 'volume': 11},              # G4 (step up)
            {'note': 48, 'volume': 15, 'sample_id': 1},  # C3 with sample
            {'note': 48, 'volume': 15, 'sample_id': 1},  # C3 with sample (repeated)
            {'note': 48, 'volume': 15, 'sample_id': 1},  # C3 with sample (repeated)
        ]
    
    def test_rle_compression(self):
        """Test Run-Length Encoding compression"""
        # First 4 events are identical - should be RLE compressed
        compressed, metadata = self.engine.compress_pattern(self.test_pattern[:4])
        
        # Verify RLE block is created
        self.assertEqual(len(metadata['rle_blocks']), 1)
        self.assertEqual(metadata['rle_blocks'][0], (0, 4))
        
        # Decompress and verify
        decompressed = self.engine.decompress_pattern(compressed, metadata)
        self.assertEqual(decompressed, self.test_pattern[:4])
    
    def test_delta_compression(self):
        """Test delta compression for sequential notes"""
        # Events 4-8 form an ascending scale - should be delta compressed
        compressed, metadata = self.engine.compress_pattern(self.test_pattern[4:8])
        
        # Verify delta block is created
        self.assertEqual(len(metadata['delta_blocks']), 1)
        
        # Decompress and verify
        decompressed = self.engine.decompress_pattern(compressed, metadata)
        self.assertEqual(decompressed, self.test_pattern[4:8])
    
    def test_mixed_compression(self):
        """Test combination of RLE and delta compression"""
        compressed, metadata = self.engine.compress_pattern(self.test_pattern)
        
        # Verify both RLE and delta blocks exist
        self.assertGreater(len(metadata['rle_blocks']), 0)
        self.assertGreater(len(metadata['delta_blocks']), 0)
        
        # Decompress and verify
        decompressed = self.engine.decompress_pattern(compressed, metadata)
        self.assertEqual(decompressed, self.test_pattern)
    
    def test_sample_events(self):
        """Test compression with sample ID events"""
        sample_events = self.test_pattern[-3:]  # Last 3 events with sample_id
        compressed, metadata = self.engine.compress_pattern(sample_events)
        
        # Verify RLE compression of sample events
        self.assertEqual(len(metadata['rle_blocks']), 1)
        
        # Decompress and verify
        decompressed = self.engine.decompress_pattern(compressed, metadata)
        self.assertEqual(decompressed, sample_events)
    
    def test_empty_pattern(self):
        """Test compression of empty pattern"""
        compressed, metadata = self.engine.compress_pattern([])
        
        self.assertEqual(len(compressed), 0)
        self.assertEqual(len(metadata['rle_blocks']), 0)
        self.assertEqual(len(metadata['delta_blocks']), 0)
        
        decompressed = self.engine.decompress_pattern(compressed, metadata)
        self.assertEqual(decompressed, [])
    
    def test_single_event(self):
        """Test compression of single event"""
        event = {'note': 60, 'volume': 15}
        compressed, metadata = self.engine.compress_pattern([event])
        
        # Should be stored as raw event (no compression)
        self.assertEqual(len(metadata['rle_blocks']), 0)
        self.assertEqual(len(metadata['delta_blocks']), 0)
        
        decompressed = self.engine.decompress_pattern(compressed, metadata)
        self.assertEqual(decompressed, [event])
