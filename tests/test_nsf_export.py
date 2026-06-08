# New file: tests/test_nsf_export.py

import unittest
import os
import struct
from pathlib import Path
from exporter.exporter_nsf import NSFExporter, NSFHeader, NSFMacroPacker

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

    def test_nsf_macro_packer_pointer_resolution(self):
        """Verify that NSFMacroPacker properly calculates absolute memory pointers"""
        packer = NSFMacroPacker(base_address=0x8000)
        
        macros = {
            'vol_0': [15, 14, 0xFF],
            'duty_0': [2, 2, 0xFF]
        }
        instruments = {
            # References vol_0 and duty_0, leaves arp and pitch null
            'inst_0': {'vol': 'vol_0', 'arp': None, 'pitch': None, 'duty': 'duty_0'}
        }
        sequences = {
            'pulse1': [0x80, 0x00, 0x64, 0x3C, 0xFF],
            'triangle': [0x80, 0x00, 0xFF]
        }
        
        payload = packer.pack(macros, instruments, sequences)
        
        # Verify Total Size
        # Macros: 3 bytes + 3 bytes = 6 bytes
        # Instruments: 1 inst * 8 bytes = 8 bytes
        # Sequences: 5 bytes + 3 bytes = 8 bytes
        # Total: 22 bytes
        self.assertEqual(len(payload), 22)
        
        # Verify absolute memory addresses were tracked correctly
        self.assertEqual(packer.pointers['vol_0'], 0x8000)
        self.assertEqual(packer.pointers['duty_0'], 0x8003)
        self.assertEqual(packer.pointers['inst_0'], 0x8006)
        self.assertEqual(packer.pointers['seq_pulse1'], 0x800E)
        self.assertEqual(packer.pointers['seq_triangle'], 0x8013)
        
        # Verify instrument table formatting (Little Endian pointers + null fallbacks)
        inst_table = payload[6:14]
        vol_ptr, arp_ptr, pitch_ptr, duty_ptr = struct.unpack('<HHHH', inst_table)
        self.assertEqual(vol_ptr, 0x8000)
        self.assertEqual(arp_ptr, 0x0000)
        self.assertEqual(pitch_ptr, 0x0000)
        self.assertEqual(duty_ptr, 0x8003)
        
        # Verify song header layout
        header = packer.build_song_header(initial_tempo=150)
        self.assertEqual(len(header), 11)
        p1, p2, tri, noise, dpcm = struct.unpack('<HHHHH', header[:10])
        self.assertEqual(p1, 0x800E)
        self.assertEqual(p2, 0x0000)  # Pulse2 wasn't provided, should be null
        self.assertEqual(tri, 0x8013)
        self.assertEqual(header[10], 150)
