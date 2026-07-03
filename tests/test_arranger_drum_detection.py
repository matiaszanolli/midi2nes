"""Regression tests for arranger drum-track detection (issue #85).

GM percussion lives on MIDI channel 10 (index 9). parser_fast now preserves
``channel`` on each event, and analyze_midi_events flags channel-9 tracks as
drums so their content routes to the noise/DPCM channels instead of stealing a
pulse/triangle. The old code only recognised drums when the track *name*
contained "drum" or equalled "9", which ordinary GM MIDI never satisfies.
"""
import unittest

from arranger.pipeline_integration import analyze_midi_events


def _drum_events(channel):
    """A kick+snare drum track on the given MIDI channel."""
    return [
        {'frame': 0, 'note': 36, 'volume': 100, 'type': 'note_on', 'channel': channel},
        {'frame': 5, 'note': 36, 'volume': 0, 'type': 'note_off', 'channel': channel},
        {'frame': 10, 'note': 38, 'volume': 100, 'type': 'note_on', 'channel': channel},
        {'frame': 15, 'note': 38, 'volume': 0, 'type': 'note_off', 'channel': channel},
    ]


class TestArrangerDrumDetection(unittest.TestCase):
    def test_channel_9_track_detected_as_drums(self):
        """A neutrally-named track on channel 9 must be routed to noise/DPCM."""
        events = {
            'track_0': [
                {'frame': 0, 'note': 60, 'volume': 100, 'type': 'note_on', 'channel': 0},
                {'frame': 30, 'note': 60, 'volume': 0, 'type': 'note_off', 'channel': 0},
            ],
            'track_1': _drum_events(channel=9),  # no "drum" in the name
        }
        plan, _, _ = analyze_midi_events(events)
        self.assertTrue(
            plan.noise_tracks or plan.dpcm_tracks,
            "channel-9 percussion should populate noise/DPCM tracks",
        )
        self.assertIn(1, plan.noise_tracks + plan.dpcm_tracks)

    def test_non_drum_channel_not_detected(self):
        """A melodic track on channel 0 must not be flagged as drums."""
        events = {'track_0': _drum_events(channel=0)}
        plan, _, _ = analyze_midi_events(events)
        self.assertEqual(plan.noise_tracks, [])
        self.assertEqual(plan.dpcm_tracks, [])

    def test_name_heuristic_still_works_without_channel(self):
        """Fallback: a track named with 'drum' is detected even without channel info."""
        events = {
            'Drums': [
                {'frame': 0, 'note': 36, 'volume': 100, 'type': 'note_on'},
                {'frame': 5, 'note': 36, 'volume': 0, 'type': 'note_off'},
            ]
        }
        plan, _, _ = analyze_midi_events(events)
        self.assertTrue(plan.noise_tracks or plan.dpcm_tracks)

    def test_definitive_non_drum_channel_wins_over_drum_name(self):
        """Regression (#206/ARR-11): a pitched track on a known, non-percussion
        channel must not be rerouted to noise/DPCM just because its name
        happens to contain "drum" (e.g. a reference/scratch track name) --
        definitive channel info must be authoritative over the name fallback."""
        events = {
            'Drum Fill Reference': [
                {'frame': 0, 'note': 60, 'volume': 100, 'type': 'note_on', 'channel': 0},
                {'frame': 30, 'note': 60, 'volume': 0, 'type': 'note_off', 'channel': 0},
                {'frame': 40, 'note': 64, 'volume': 100, 'type': 'note_on', 'channel': 0},
                {'frame': 70, 'note': 64, 'volume': 0, 'type': 'note_off', 'channel': 0},
            ]
        }
        plan, _, _ = analyze_midi_events(events)
        self.assertFalse(plan.tracks[0].is_drum_track)
        self.assertEqual(plan.noise_tracks, [])
        self.assertIn(0, plan.pulse1_tracks + plan.pulse2_tracks + plan.triangle_tracks)

    def test_channel_9_wins_even_with_non_drum_name(self):
        """Channel 9 must still be authoritative when the name doesn't match
        the drum heuristic at all (no false negative from the restructure)."""
        events = {'Lead Synth': _drum_events(channel=9)}
        plan, _, _ = analyze_midi_events(events)
        self.assertTrue(plan.tracks[0].is_drum_track)
        self.assertIn(0, plan.noise_tracks + plan.dpcm_tracks)

    def test_second_drum_track_recorded_as_dropped_not_silently_lost(self):
        """Regression (#205/ARR-10): a second drum-flagged track finding both
        noise and DPCM already claimed by the first drum track used to hit an
        unconditional `continue`, vanishing with no dropped_tracks entry and
        no plan.notes diagnostic -- unlike every other channel-overflow case."""
        events = {
            'drums_a': _drum_events(channel=9),
            'drums_b': _drum_events(channel=9),
        }
        plan, _, _ = analyze_midi_events(events)
        self.assertIn(0, plan.noise_tracks + plan.dpcm_tracks)
        self.assertIn(1, plan.dropped_tracks)
        self.assertTrue(
            any('1' in note or 'drums_b' in note for note in plan.notes),
            f"expected a plan.notes entry for the dropped second drum track, got {plan.notes}",
        )


if __name__ == '__main__':
    unittest.main()
