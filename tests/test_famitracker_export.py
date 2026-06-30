import re
import unittest

from exporter.exporter import generate_famitracker_txt_with_patterns, midi_note_to_ft


class TestFamiTrackerExport(unittest.TestCase):
    """Regression tests for EXP-06 / #82: the FamiTracker text export declared
    five channels but wrote a single note column, and emitted negative octaves on
    low notes."""

    def test_octave_clamped_to_valid_range(self):
        self.assertEqual(midi_note_to_ft(60), 'C-4')   # middle C unchanged
        self.assertEqual(midi_note_to_ft(5), 'F-0')    # was 'F--1' (octave -1)
        self.assertEqual(midi_note_to_ft(0), 'C-0')    # was 'C--1'
        self.assertEqual(midi_note_to_ft(119), 'B-7')  # was 'B-8' (above 7)

    def test_row_has_one_cell_per_declared_channel(self):
        patterns = {'p0': {'events': [{'note': 60, 'volume': 15},
                                      {'note': 5, 'volume': 8}]}}
        refs = {'p0': [0]}
        out = generate_famitracker_txt_with_patterns({}, patterns, refs,
                                                     rows_per_pattern=4)
        # Five 2A03 channels are declared...
        self.assertIn("COLUMNS 1 1 1 1 1", out)
        # ...so every data row must carry exactly five channel cells.
        data_rows = [l for l in out.splitlines() if re.match(r'^[0-9A-F]{2} \| ', l)]
        self.assertTrue(data_rows)
        for line in data_rows:
            cells = line.split(' | ')[1:]
            self.assertEqual(len(cells), 5, f"{line!r} -> {cells}")
        # And no negative octave leaks into the output.
        self.assertNotIn('--1', out)


if __name__ == '__main__':
    unittest.main()
