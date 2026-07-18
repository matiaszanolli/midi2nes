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

    def test_low_note_octave_clamped(self):
        # Regression (EXP-06 / #82): low MIDI notes gave octave -1 (e.g. 'F--1'),
        # which FamiStudio rejects. Octave must be clamped into 0-7.
        self.assertEqual(midi_note_to_famistudio(5), 'F-0')    # was 'F--1'
        self.assertEqual(midi_note_to_famistudio(0), 'C-0')    # was 'C--1'
        self.assertEqual(midi_note_to_famistudio(119), 'B-7')  # high end clamps to 7

    def test_dpcm_uses_note_field_without_keyerror(self):
        # Regression (EXP-06 / #82): the frames dict encodes DPCM as note =
        # sample_id + 1 (no 'sample_id' key), so reading event['sample_id'] raised
        # KeyError. The exporter must recover sample_id from note.
        frames = {'dpcm': {'0': {'note': 4, 'volume': 15}}}  # sample_id 3
        output = generate_famistudio_txt(frames)  # must not raise
        self.assertIn("C-4 3", output)
        
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

    def test_dpcm_sample_map_side_table_does_not_crash(self):
        # Regression (#313/EXP-11, coverage gap #322/REG-16): nes/emulator_core.py
        # attaches a dpcm_sample_map side table (dense_id -> catalog_id) to frames
        # for any DPCM-using song. Iterating it as a playable channel produced a
        # "dpcm_sample_map_N" pattern key that crashed
        # channel, index = pattern_key.split('_') with ValueError. The dpcm_sample_map
        # value shape here matches what emulator_core emits (dense_id -> catalog_id).
        frames = {
            'pulse1': {str(f): {'note': 60, 'volume': 15} for f in range(0, 400, 50)},
            'dpcm': {'0': {'note': 5, 'volume': 15}},
            'dpcm_sample_map': {'0': 1318, '1': 1620},
        }
        output = generate_famistudio_txt(frames)  # must not raise
        self.assertIn('PATTERN "pulse1_0"', output)
        # The side table must not leak into the output as a pseudo-channel or a
        # "dpcm_sample_map_*" PATTERN block.
        self.assertNotIn("dpcm_sample_map", output)
        self.assertNotIn('PATTERN "dpcm_sample_map', output)


class TestFamiStudioGoldenBytes(unittest.TestCase):
    """Exact-output regression for the FamiStudio pattern rows (#232 / REG-14).

    The other FamiStudio tests only assert section markers ("PATTERNS") and a
    few substring notes, so a wrong note-name/octave for an unchecked note, a
    pattern row at the wrong frame, or a dropped note would slip through. This
    pins the *entire* emitted pattern block for every channel type — tone
    (pulse/triangle), noise (F#4 sentinel), the DPCM sample_id-from-note
    recovery, and the "... .." empty-row sentinel at exact frame positions.
    This is the FamiStudio equivalent of TestCA65GoldenBytes.
    """

    # Global max_frame is 2, so every channel emits exactly rows 00..02.
    FRAMES = {
        'pulse1':   {'0': {'note': 60, 'volume': 15},   # C-4
                     '2': {'note': 62, 'volume': 10}},   # D-4
        'triangle': {'1': {'note': 48, 'volume': 15}},   # C-3
        'noise':    {'2': {'volume': 7}},                # F#4 sentinel
        'dpcm':     {'0': {'note': 4, 'volume': 15}},    # sample_id 3 (note-1)
    }

    def setUp(self):
        self.output = generate_famistudio_txt(self.FRAMES)

    def _assert_block(self, expected):
        self.assertIn(expected, self.output)

    def test_pulse1_pattern_rows_exact(self):
        self._assert_block("\n".join([
            '  PATTERN "pulse1_0"',
            '    CHANNEL PULSE1',
            '    LENGTH 64',
            '    00 | C-4 15',
            '    01 | ... ..',
            '    02 | D-4 10',
            '  END',
        ]))

    def test_triangle_pattern_rows_exact(self):
        self._assert_block("\n".join([
            '  PATTERN "triangle_0"',
            '    CHANNEL TRIANGLE',
            '    LENGTH 64',
            '    00 | ... ..',
            '    01 | C-3 15',
            '    02 | ... ..',
            '  END',
        ]))

    def test_noise_pattern_rows_exact(self):
        self._assert_block("\n".join([
            '  PATTERN "noise_0"',
            '    CHANNEL NOISE',
            '    LENGTH 64',
            '    00 | ... ..',
            '    01 | ... ..',
            '    02 | F#4 7',
            '  END',
        ]))

    def test_dpcm_pattern_rows_exact(self):
        # sample_id recovered from note (4 - 1 = 3), emitted as "C-4 3".
        self._assert_block("\n".join([
            '  PATTERN "dpcm_0"',
            '    CHANNEL DPCM',
            '    LENGTH 64',
            '    00 | C-4 3',
            '    01 | ... ..',
            '    02 | ... ..',
            '  END',
        ]))
