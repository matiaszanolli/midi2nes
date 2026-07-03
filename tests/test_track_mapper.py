import io
import contextlib
import unittest
from tracker.track_mapper import (
    group_notes_by_frame,
    detect_chord,
    get_arpeggio_pattern,
    apply_arpeggio_pattern,
    apply_arpeggio_fallback,
    assign_tracks_to_nes_channels
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

class TestNoiseChannelContention(unittest.TestCase):
    """Regression (#74/D-11): the drum noise-fallback used to be silently
    discarded when the noise channel was already assigned to another track --
    with no warning, no trace. It must now warn instead of vanishing."""

    DPCM_INDEX = "tests/fixtures/test_dpcm_index.json"

    def test_noise_fallback_dropped_with_warning_when_noise_occupied(self):
        midi_events = {
            "melody": [{"frame": 0, "note": 90, "velocity": 100}],   # -> pulse1 (highest)
            "harmony": [{"frame": 0, "note": 80, "velocity": 100}],  # -> pulse2 (2nd highest)
            "bass": [{"frame": 0, "note": 30, "velocity": 100}],     # -> triangle (lowest)
            # 'drum' in the name -> claims nes_tracks['noise'] via the
            # multi-track remaining-channel heuristic.
            "drum_kit": [{"frame": 0, "note": 50, "velocity": 100}],
            # An unmapped GM percussion note (hi-hat) that ADVANCED_MIDI_DRUM_MAPPING
            # doesn't define -> falls to the noise fallback (#73/D-10).
            "extra_perc": [{"frame": 10, "note": 42, "velocity": 80}],
        }

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = assign_tracks_to_nes_channels(midi_events, self.DPCM_INDEX)

        # The noise channel keeps whatever it was already assigned (drum_kit's
        # events), not silently overwritten or left empty.
        self.assertTrue(result["noise"])
        self.assertIn("dropped", buf.getvalue())
        self.assertIn("noise", buf.getvalue().lower())

    def test_noise_fallback_used_when_noise_channel_free(self):
        # Baseline: when nothing has claimed the noise channel, the fallback
        # still lands there as before -- no regression on the happy path.
        midi_events = {
            "melody": [{"frame": 0, "note": 72, "velocity": 100}],
            "extra_perc": [{"frame": 10, "note": 42, "velocity": 80}],
        }
        result = assign_tracks_to_nes_channels(midi_events, self.DPCM_INDEX)
        self.assertTrue(result["noise"])


class TestMultiTrackChannelAllocation(unittest.TestCase):
    """Regression (#48/REG-08): the multi-track branch of
    assign_tracks_to_nes_channels (track_mapper.py ~206-240) ranks tracks by
    average pitch and assigns melody->pulse1, harmony->pulse2 (with arpeggio
    fallback), bass->triangle, drum-named->noise. This was entirely
    unverified -- a regression (e.g. bass routed to a pulse channel) would
    ship green."""

    DPCM_INDEX = "tests/fixtures/test_dpcm_index.json"

    def test_four_track_allocation_by_average_pitch(self):
        midi_events = {
            "melody": [
                {"frame": 0, "note": 84, "velocity": 100},
                {"frame": 10, "note": 88, "velocity": 100},
            ],
            "harmony": [
                {"frame": 0, "note": 64, "velocity": 100},
                {"frame": 0, "note": 67, "velocity": 100},
            ],
            "bass": [
                {"frame": 0, "note": 36, "velocity": 100},
                {"frame": 10, "note": 40, "velocity": 100},
            ],
            "drum_kit": [
                {"frame": 0, "note": 50, "velocity": 100},
            ],
        }

        result = assign_tracks_to_nes_channels(midi_events, self.DPCM_INDEX)

        # Highest average pitch (melody, avg 86) -> pulse1, untouched.
        self.assertEqual(result["pulse1"], midi_events["melody"])

        # Next highest (harmony, avg 65.5) -> pulse2, passed through the
        # arpeggio fallback (simultaneous notes at frame 0 get spread out).
        pulse2_notes = sorted(e["note"] for e in result["pulse2"])
        self.assertEqual(pulse2_notes, [64, 67])
        self.assertTrue(all(e.get("arpeggio") for e in result["pulse2"]))

        # Lowest average pitch (bass, avg 38) -> triangle, not a pulse channel.
        self.assertEqual(result["triangle"], midi_events["bass"])

        # Remaining drum-named track -> noise.
        self.assertEqual(result["noise"], midi_events["drum_kit"])
        self.assertEqual(result["pulse1"], midi_events["melody"])
        self.assertNotEqual(result["triangle"], midi_events["drum_kit"])

    def test_real_midi_two_track_pitch_ranking(self):
        # test_midi/multiple_tracks.mid has exactly 2 tracks: track_0 (avg
        # pitch ~63.7, a chord melody) and track_1 (avg pitch 50.0, a lower
        # ostinato). With only 2 tracks both pulse1 and pulse2 are claimed
        # before the triangle-assignment step runs, so the lower track lands
        # on pulse2 (with arpeggio fallback), not triangle -- pinning that
        # real-world behavior against a regression.
        from tracker.parser_fast import parse_midi_to_frames

        parsed = parse_midi_to_frames("test_midi/multiple_tracks.mid")
        midi_events = parsed["events"]

        result = assign_tracks_to_nes_channels(midi_events, self.DPCM_INDEX)

        self.assertEqual(result["pulse1"], midi_events["track_0"])
        pulse2_source_notes = sorted(
            e["note"] for e in midi_events["track_1"] if e["volume"] > 0
        )
        pulse2_notes = sorted(e["note"] for e in result["pulse2"])
        self.assertEqual(pulse2_notes, pulse2_source_notes)
        self.assertEqual(result["triangle"], [])


if __name__ == '__main__':
    unittest.main()
