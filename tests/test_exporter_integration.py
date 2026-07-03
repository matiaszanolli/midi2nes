# tests/test_exporter_integration.py

import unittest
from pathlib import Path
import tempfile
import os

from exporter.compression import CompressionEngine
from exporter.exporter_ca65 import CA65Exporter
from exporter.exporter_nsf import NSFExporter
from exporter.exporter_famistudio import FamiStudioExporter
from tracker.parser_fast import parse_midi_to_frames
from tracker.track_mapper import assign_tracks_to_nes_channels
from nes.emulator_core import NESEmulatorCore

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
        
        # Create test data that can actually be compressed
        # RLE test data (repeating events)
        rle_pattern = [
            {'note': 60, 'volume': 15},
            {'note': 60, 'volume': 15},
            {'note': 60, 'volume': 15}  # 3 identical events for RLE
        ]
        
        # Delta test data (sequential note changes)
        delta_pattern = [
            {'note': 60, 'volume': 15},
            {'note': 62, 'volume': 15},
            {'note': 64, 'volume': 15},
            {'note': 66, 'volume': 15}  # Sequential notes for delta compression
        ]
        
        # Test RLE compression
        compressed, metadata = engine.compress_pattern(rle_pattern)
        decompressed = engine.decompress_pattern(compressed, metadata)
        
        # Verify RLE compression worked
        self.assertEqual(len(compressed), 1)  # Should compress to 1 RLE block
        self.assertEqual(len(metadata['rle_blocks']), 1)
        self.assertEqual(decompressed, rle_pattern)
        
        # Test delta compression
        compressed, metadata = engine.compress_pattern(delta_pattern)
        decompressed = engine.decompress_pattern(compressed, metadata)
        
        # Verify delta compression worked
        self.assertEqual(len(metadata['delta_blocks']), 1)
        self.assertEqual(decompressed, delta_pattern)
    
    def test_ca65_export_with_compression(self):
        """Test CA65 export with compression"""
        output_path = os.path.join(self.temp_dir, "test_ca65.s")
        exporter = CA65Exporter()
        
        patterns = {"test": {"events": self.test_frames['pulse1']}}
        references = {"0": ("test", 0)}
        
        exporter.export_tables_with_patterns(self.test_frames, patterns, references, output_path)
        
        # Verify file exists and contains expected CA65 assembly
        self.assertTrue(os.path.exists(output_path))
        with open(output_path, 'r') as f:
            content = f.read()
            self.assertIn("instrument_table:", content)
            self.assertIn("pulse1_sequence:", content)
    
    def test_nsf_export_unsupported(self):
        """Regression (EXP-05 / #81): NSF export is not a playable NSF and is now
        explicitly unsupported, so the exporter must raise rather than write a
        garbage file."""
        output_path = os.path.join(self.temp_dir, "test.nsf")
        exporter = NSFExporter()

        with self.assertRaises(NotImplementedError):
            exporter.export(self.test_frames, output_path, "Test Song")
        self.assertFalse(os.path.exists(output_path))
    
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


class TestCA65GoldenBytes(unittest.TestCase):
    """Regression (#45/REG-05): the register-boundary tests above (and in
    test_midi_parser_integration.py) only assert that a section/substring is
    present, so a regression that emits the right *structure* with wrong
    *values* (an off-by-one pitch, a wrong length nibble, a swapped duty)
    would still pass. Pin the actual emitted bytes for a known input instead.

    patterns is passed as a non-empty dummy dict purely to select the
    MMC3 macro-bytecode path in export_tables_with_patterns -- its content
    is never consumed (only `frames` drives the emitted bytes, see that
    method's docstring / #4), so this is deterministic regardless of what
    the (parallel, worker-count-dependent) pattern detector would produce.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def _export_simple_loop(self):
        midi_data = parse_midi_to_frames("test_midi/simple_loop.mid")
        mapped = assign_tracks_to_nes_channels(midi_data["events"], "dpcm_index.json")
        frames = NESEmulatorCore().process_all_tracks(mapped)

        output_path = os.path.join(self.temp_dir, "golden.asm")
        CA65Exporter().export_tables_with_patterns(
            frames, {"dummy": {}}, {}, output_path, standalone=False
        )
        return Path(output_path).read_text()

    def test_pulse1_sequence_golden_bytes(self):
        content = self._export_simple_loop()
        start = content.index("pulse1_sequence:")
        end = content.index("pulse2_sequence:")
        sequence_block = content[start:end].strip()

        expected = (
            "pulse1_sequence:\n"
            "    .byte $80, $01 ; CMD_INSTRUMENT\n"
            "    .byte $7D, $3C ; Length 30, Note 60\n"
            "    .byte $7D, $00 ; Length 30, Note 0\n"
            "    .byte $7D, $40 ; Length 30, Note 64\n"
            "    .byte $7D, $00 ; Length 30, Note 0\n"
            "    .byte $7D, $43 ; Length 30, Note 67\n"
            "    .byte $7D, $00 ; Length 30, Note 0\n"
            "    .byte $7D, $3C ; Length 30, Note 60\n"
            "    .byte $7D, $00 ; Length 30, Note 0\n"
            "    .byte $7D, $40 ; Length 30, Note 64\n"
            "    .byte $7D, $00 ; Length 30, Note 0\n"
            "    .byte $7D, $43 ; Length 30, Note 67\n"
            "    .byte $7D, $00 ; Length 30, Note 0\n"
            "    .byte $7D, $3C ; Length 30, Note 60\n"
            "    .byte $7D, $00 ; Length 30, Note 0\n"
            "    .byte $7D, $40 ; Length 30, Note 64\n"
            "    .byte $7D, $00 ; Length 30, Note 0\n"
            "    .byte $7D, $43 ; Length 30, Note 67\n"
            "    .byte $7D, $00 ; Length 30, Note 0\n"
            "    .byte $7D, $3C ; Length 30, Note 60\n"
            "    .byte $7D, $00 ; Length 30, Note 0\n"
            "    .byte $7D, $40 ; Length 30, Note 64\n"
            "    .byte $7D, $00 ; Length 30, Note 0\n"
            "    .byte $7D, $43 ; Length 30, Note 67\n"
            "    .byte $FF"
        )
        self.assertEqual(sequence_block, expected)

    def test_ntsc_period_low_golden_bytes(self):
        content = self._export_simple_loop()
        start = content.index("ntsc_period_low:")
        end = content.index("ntsc_period_high:")
        table_block = content[start:end].strip()

        expected = (
            "ntsc_period_low:\n"
            "  .byte $ff, $ff, $ff, $ff, $ff, $ff, $ff, $ff\n"
            "  .byte $ff, $ff, $ff, $ff, $ff, $ff, $ff, $ff\n"
            "  .byte $ff, $ff, $ff, $ff, $ff, $ff, $ff, $ff\n"
            "  .byte $ff, $ff, $ff, $ff, $ff, $ff, $ff, $ff\n"
            "  .byte $ff, $f0, $7e, $12, $ad, $4d, $f2, $9d"
        )
        self.assertTrue(table_block.startswith(expected),
                         f"ntsc_period_low table drifted from golden bytes:\n{table_block[:250]}")
