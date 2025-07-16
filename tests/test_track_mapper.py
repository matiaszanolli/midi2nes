import unittest
from track_mapper import (
    group_notes_by_frame,
    detect_chord,
    get_arpeggio_pattern,
    apply_arpeggio_pattern,
    apply_arpeggio_fallback
)

class TestChordDetection(unittest.TestCase):
    def test_major_chord(self):
        # C major: C(60), E(64), G(67)
        notes = [60, 64, 67]
        chord = detect_chord(notes)
        self.assertEqual(chord["type"], "major")
        self.assertEqual(chord["root"], 60)

    def test_minor_chord(self):
        # C minor: C(60), Eb(63), G(67)
        notes = [60, 63, 67]
        chord = detect_chord(notes)
        self.assertEqual(chord["type"], "minor")
        self.assertEqual(chord["root"], 60)

    def test_diminished_chord(self):
        # C diminished: C(60), Eb(63), Gb(66)
        notes = [60, 63, 66]
        chord = detect_chord(notes)
        self.assertEqual(chord["type"], "diminished")
        self.assertEqual(chord["root"], 60)

    def test_augmented_chord(self):
        # C augmented: C(60), E(64), G#(68)
        notes = [60, 64, 68]
        chord = detect_chord(notes)
        self.assertEqual(chord["type"], "augmented")
        self.assertEqual(chord["root"], 60)

    def test_unknown_chord(self):
        # Random notes that don't form a recognized chord
        notes = [60, 65, 68]
        chord = detect_chord(notes)
        self.assertEqual(chord["type"], "unknown")
        self.assertEqual(chord["root"], 60)

    def test_single_note(self):
        notes = [60]
        chord = detect_chord(notes)
        self.assertIsNone(chord)

class TestArpeggioPatterns(unittest.TestCase):
    def setUp(self):
        self.test_notes = [60, 64, 67]  # C major triad

    def test_up_pattern(self):
        result = apply_arpeggio_pattern(self.test_notes, "up")
        self.assertEqual(result, [60, 64, 67])

    def test_down_pattern(self):
        result = apply_arpeggio_pattern(self.test_notes, "down")
        self.assertEqual(result, [67, 64, 60])

    def test_up_down_pattern(self):
        result = apply_arpeggio_pattern(self.test_notes, "up_down")
        self.assertEqual(result, [60, 64, 67, 64])

    def test_down_up_pattern(self):
        result = apply_arpeggio_pattern(self.test_notes, "down_up")
        self.assertEqual(result, [67, 64, 60, 64, 67])

    def test_random_pattern(self):
        result = apply_arpeggio_pattern(self.test_notes, "random")
        # Check that all original notes are present (might be duplicated)
        for note in self.test_notes:
            self.assertIn(note, result)

    def test_invalid_pattern(self):
        result = apply_arpeggio_pattern(self.test_notes, "invalid_pattern")
        self.assertEqual(result, [60, 64, 67])  # Should default to "up"

class TestArpeggioFallback(unittest.TestCase):
    def test_single_note_passthrough(self):
        events = [
            {"frame": 0, "note": 60, "velocity": 100}
        ]
        result = apply_arpeggio_fallback(events)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["note"], 60)
        self.assertFalse(result[0]["arpeggio"])

    def test_chord_arpeggio(self):
        events = [
            {"frame": 0, "note": 60, "velocity": 100},
            {"frame": 0, "note": 64, "velocity": 100},
            {"frame": 0, "note": 67, "velocity": 100}
        ]
        result = apply_arpeggio_fallback(events)
        self.assertTrue(all(e["arpeggio"] for e in result))
        self.assertEqual(len(result), 3)
        self.assertEqual([e["note"] for e in result], [60, 64, 67])

    def test_max_notes_limit(self):
        events = [
            {"frame": 0, "note": 60, "velocity": 100},
            {"frame": 0, "note": 64, "velocity": 100},
            {"frame": 0, "note": 67, "velocity": 100},
            {"frame": 0, "note": 72, "velocity": 100}
        ]
        result = apply_arpeggio_fallback(events, max_notes=3)
        self.assertEqual(len(result), 3)  # Should only take first 3 notes

    def test_velocity_variation(self):
        events = [
            {"frame": 0, "note": 60, "velocity": 100},
            {"frame": 0, "note": 64, "velocity": 100},
            {"frame": 0, "note": 67, "velocity": 100}
        ]
        result = apply_arpeggio_fallback(events)
        velocities = [e["velocity"] for e in result]
        self.assertTrue(velocities[0] > velocities[1] > velocities[2])

    def test_frame_ordering(self):
        events = [
            {"frame": 10, "note": 60, "velocity": 100},
            {"frame": 0, "note": 64, "velocity": 100},
            {"frame": 5, "note": 67, "velocity": 100}
        ]
        result = apply_arpeggio_fallback(events)
        frames = [e["frame"] for e in result]
        self.assertEqual(frames, sorted(frames))

class TestGroupNotesByFrame(unittest.TestCase):
    def test_basic_grouping(self):
        events = [
            {"frame": 0, "note": 60, "velocity": 100},
            {"frame": 0, "note": 64, "velocity": 100},
            {"frame": 10, "note": 67, "velocity": 100}
        ]
        grouped = group_notes_by_frame(events)
        self.assertEqual(len(grouped[0]), 2)
        self.assertEqual(len(grouped[10]), 1)

    def test_ignore_note_offs(self):
        events = [
            {"frame": 0, "note": 60, "velocity": 100},
            {"frame": 0, "note": 64, "velocity": 0},  # note off
            {"frame": 0, "note": 67, "velocity": 100}
        ]
        grouped = group_notes_by_frame(events)
        self.assertEqual(len(grouped[0]), 2)
        self.assertEqual(grouped[0], [60, 67])

if __name__ == '__main__':
    unittest.main()
