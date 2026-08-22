# New file: tests/test_famistudio_export.py

import unittest
import json
import re
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
        
    def test_tone_channel_missing_note_or_volume_does_not_raise(self):
        # Regression (#370/EXP-2026-07-19-2): pulse1/pulse2/triangle read
        # event['note']/event['volume'] via direct subscript, raising
        # KeyError on a frame dict missing either key -- unlike the CA65
        # exporter (frame_data.get('note', 0)/.get('volume', 0)) and this
        # same function's dpcm branch (already hardened in #82), which both
        # tolerate it. The two exporters must agree on what's a valid frame.
        frames = {
            'pulse1': {'0': {'volume': 15}},   # missing 'note'
            'pulse2': {'0': {'note': 60}},     # missing 'volume'
            'triangle': {'0': {}},             # missing both
        }
        output = generate_famistudio_txt(frames)  # must not raise
        self.assertIn('PATTERN "pulse1_0"', output)
        self.assertIn('PATTERN "pulse2_0"', output)
        self.assertIn('PATTERN "triangle_0"', output)

    def test_generate_famistudio_txt(self):
        output = generate_famistudio_txt(
            self.test_frames,
            project_name="Test Project",
            author="Test Author",
            copyright="Test Copyright"
        )
        
        # Verify basic structure. No bare assertIn("PATTERNS") here (#339/
        # REG-20): a section-header-only check would still pass if every note
        # in the pattern rows were wrong -- TestFamiStudioGoldenBytes below
        # pins the exact pattern-row content for that emit path instead.
        self.assertIn("# FamiStudio Text Export", output)
        self.assertIn("PROJECT", output)
        self.assertIn("INSTRUMENTS", output)

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
        # LENGTH 3, not the old hardcoded 64 (#440/EXP-2026-08-21-2): this
        # song's only pattern is the 3-row remainder, so its declared
        # LENGTH must match its actual row count.
        self._assert_block("\n".join([
            '  PATTERN "pulse1_0"',
            '    CHANNEL PULSE1',
            '    LENGTH 3',
            '    00 | C-4 15',
            '    01 | ... ..',
            '    02 | D-4 10',
            '  END',
        ]))

    def test_triangle_pattern_rows_exact(self):
        self._assert_block("\n".join([
            '  PATTERN "triangle_0"',
            '    CHANNEL TRIANGLE',
            '    LENGTH 3',
            '    00 | ... ..',
            '    01 | C-3 15',
            '    02 | ... ..',
            '  END',
        ]))

    def test_noise_pattern_rows_exact(self):
        self._assert_block("\n".join([
            '  PATTERN "noise_0"',
            '    CHANNEL NOISE',
            '    LENGTH 3',
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
            '    LENGTH 3',
            '    00 | C-4 3',
            '    01 | ... ..',
            '    02 | ... ..',
            '  END',
        ]))


class TestFamiStudioSequenceReferencesResolveToPatterns(unittest.TestCase):
    """Regression for #440/EXP-2026-08-21-2: full-pattern PATTERN keys used
    to be numbered by a GLOBAL count of every channel's patterns emitted so
    far (`len(patterns)`), while the remainder pattern and every SEQUENCE
    reference used a PER-CHANNEL 0-based count. The first channel processed
    happened to work (the two counts coincide before anything else has been
    emitted), but every later channel's full patterns landed on the wrong
    indices -- its SEQUENCE then pointed at undefined (or another channel's)
    PATTERN names. Every SEQUENCE reference must resolve to a defined
    PATTERN, for >=2 channels spanning >=64 frames (the minimum needed to
    exercise a full, non-remainder pattern on more than one channel)."""

    @staticmethod
    def _defined_patterns(output):
        return set(re.findall(r'PATTERN "([^"]+)"', output))

    @staticmethod
    def _sequence_references(output):
        refs = set()
        for seq_line in re.findall(r'SEQUENCE (.+)', output):
            refs.update(re.findall(r'"([^"]+)"', seq_line))
        return refs

    def test_two_channels_multiple_patterns_all_sequence_refs_defined(self):
        # 130 frames -> two full 64-row patterns plus a 2-row remainder per
        # channel, on two channels -- exactly the shape the issue reproduced.
        frames = {
            'pulse1': {str(i): {'note': 60, 'volume': 10} for i in range(130)},
            'pulse2': {str(i): {'note': 64, 'volume': 8} for i in range(130)},
        }
        output = generate_famistudio_txt(frames)

        defined = self._defined_patterns(output)
        refs = self._sequence_references(output)
        self.assertTrue(refs, "expected at least one SEQUENCE reference")
        missing = refs - defined
        self.assertFalse(missing, f"SEQUENCE references undefined PATTERN(s): {missing}")

        # pulse2 (the second channel) must have its own correctly-numbered
        # patterns, not collide with or skip past pulse1's.
        self.assertIn('pulse2_0', defined)
        self.assertIn('pulse2_1', defined)
        self.assertIn('pulse2_2', defined)

    def test_three_channels_all_sequence_refs_defined(self):
        frames = {
            'pulse1': {str(i): {'note': 60, 'volume': 10} for i in range(200)},
            'pulse2': {str(i): {'note': 64, 'volume': 8} for i in range(70)},
            'triangle': {str(i): {'note': 48, 'volume': 15} for i in range(64)},
        }
        output = generate_famistudio_txt(frames)

        defined = self._defined_patterns(output)
        refs = self._sequence_references(output)
        missing = refs - defined
        self.assertFalse(missing, f"SEQUENCE references undefined PATTERN(s): {missing}")

    def test_remainder_pattern_length_matches_actual_row_count(self):
        # 130 frames = two full 64-row patterns + a 2-row remainder.
        frames = {'pulse1': {str(i): {'note': 60, 'volume': 10} for i in range(130)}}
        output = generate_famistudio_txt(frames)
        self.assertIn('PATTERN "pulse1_2"\n    CHANNEL PULSE1\n    LENGTH 2', output)


class TestFamiStudioAcceptsIntKeyedFrames(unittest.TestCase):
    """Regression for #441/EXP-2026-08-21-3: both CA65 emitters accept int OR
    str frame keys (in-memory frames carry int keys; JSON round-trips
    produce str keys), but the FamiStudio path checked only `str(frame) in
    events` -- an in-memory, int-keyed frames dict silently exported nothing
    but "... .." rest rows, with no error or warning."""

    def _non_rest_row_count(self, output):
        rows = [line for line in output.splitlines() if '|' in line]
        return sum(1 for row in rows if '... ..' not in row)

    def test_int_keyed_pulse_frames_export_non_rest_rows(self):
        frames = {'pulse1': {i: {'note': 60 + (i % 5), 'volume': 10} for i in range(10)}}
        output = generate_famistudio_txt(frames)
        self.assertEqual(self._non_rest_row_count(output), 10)
        self.assertIn('C-4 10', output)

    def test_int_keyed_and_str_keyed_frames_produce_identical_output(self):
        """An int-keyed frames dict and its JSON-round-tripped (str-keyed)
        equivalent must export byte-for-byte identical output."""
        int_keyed = {'triangle': {i: {'note': 48, 'volume': 15} for i in range(5)}}
        str_keyed = {'triangle': {str(i): {'note': 48, 'volume': 15} for i in range(5)}}
        self.assertEqual(generate_famistudio_txt(int_keyed), generate_famistudio_txt(str_keyed))

    def test_int_keyed_dpcm_frames_export_non_rest_rows(self):
        frames = {'dpcm': {i: {'note': 4, 'volume': 15} for i in (0, 3, 6)}}
        output = generate_famistudio_txt(frames)
        self.assertEqual(self._non_rest_row_count(output), 3)
