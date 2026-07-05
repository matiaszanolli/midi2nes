"""Coverage for VoiceRoleAnalyzer._assign_channels (#230 / REG-12).

`_assign_channels` is the arranger's single largest untested decision point:
it resolves channel contention (two tracks wanting the same pulse, a bass
track spilling to triangle) and decides when a track is dropped. Before this
file no test called `create_arrangement_plan()`/`_assign_channels()` or
inspected `plan.dropped_tracks`, so a regression that dropped a voice that
should have fallen back — or silently vanished a track with no
`dropped_tracks` entry — would have shipped uncaught.

The contention cases are exercised directly against `_assign_channels` with
crafted `TrackAnalysis` inputs (the roles/preferred channels are the input to
this method, so driving it directly is deterministic); one test also runs the
public `create_arrangement_plan` path end to end.
"""

import unittest

from arranger import (
    VoiceRoleAnalyzer, ArrangementPlan, TrackAnalysis, NoteInfo,
    NESChannel, MusicalRole,
)


class TestChannelAssignment(unittest.TestCase):
    def setUp(self):
        self.analyzer = VoiceRoleAnalyzer()

    def _track(self, track_id, preferred=NESChannel.FLEXIBLE,
               role=MusicalRole.MELODY, is_drum=False):
        return TrackAnalysis(
            track_id=track_id,
            name=f"T{track_id}",
            preferred_channel=preferred,
            role=role,
            is_drum_track=is_drum,
        )

    def _assign(self, *tracks):
        plan = ArrangementPlan()
        plan.tracks = list(tracks)
        self.analyzer._assign_channels(plan)
        return plan

    def test_second_pulse1_track_falls_back_to_pulse2(self):
        plan = self._assign(
            self._track(0, NESChannel.PULSE1),
            self._track(1, NESChannel.PULSE1),
        )
        self.assertEqual(plan.pulse1_tracks, [0])
        self.assertEqual(plan.pulse2_tracks, [1])
        self.assertEqual(plan.dropped_tracks, [])
        self.assertTrue(any("Pulse1 full, using Pulse2" in n for n in plan.notes))

    def test_second_pulse2_track_falls_back_to_pulse1(self):
        plan = self._assign(
            self._track(0, NESChannel.PULSE2),
            self._track(1, NESChannel.PULSE2),
        )
        self.assertEqual(plan.pulse2_tracks, [0])
        self.assertEqual(plan.pulse1_tracks, [1])
        self.assertTrue(any("Pulse2 full, using Pulse1" in n for n in plan.notes))

    def test_flexible_tracks_fill_both_pulses(self):
        plan = self._assign(
            self._track(0, NESChannel.FLEXIBLE),
            self._track(1, NESChannel.ANY_PULSE),
        )
        self.assertEqual(plan.pulse1_tracks, [0])
        self.assertEqual(plan.pulse2_tracks, [1])
        self.assertEqual(plan.dropped_tracks, [])

    def test_third_melody_track_is_dropped_with_note(self):
        """A melody track that can't fit is dropped (with a note), and is NOT
        parked on triangle — triangle is reserved for bass."""
        plan = self._assign(
            self._track(0, NESChannel.PULSE1, MusicalRole.MELODY),
            self._track(1, NESChannel.PULSE1, MusicalRole.MELODY),
            self._track(2, NESChannel.PULSE1, MusicalRole.MELODY),
        )
        self.assertEqual(plan.pulse1_tracks, [0])
        self.assertEqual(plan.pulse2_tracks, [1])
        self.assertEqual(plan.triangle_tracks, [])
        self.assertEqual(plan.dropped_tracks, [2])
        self.assertTrue(any("Dropped" in n for n in plan.notes))

    def test_bass_track_spills_to_triangle_when_pulses_full(self):
        plan = self._assign(
            self._track(0, NESChannel.PULSE1, MusicalRole.MELODY),
            self._track(1, NESChannel.PULSE1, MusicalRole.MELODY),
            self._track(2, NESChannel.PULSE1, MusicalRole.BASS),
        )
        self.assertEqual(plan.triangle_tracks, [2])
        self.assertEqual(plan.dropped_tracks, [])

    def test_drum_track_claims_noise_and_dpcm(self):
        plan = self._assign(
            self._track(0, role=MusicalRole.PERCUSSION, is_drum=True)
        )
        self.assertEqual(plan.noise_tracks, [0])
        self.assertEqual(plan.dpcm_tracks, [0])
        self.assertEqual(plan.dropped_tracks, [])

    def test_second_drum_track_is_dropped_not_silent(self):
        """A second drum track finds noise+DPCM both taken and must land in
        dropped_tracks with a note, not vanish silently (#205)."""
        plan = self._assign(
            self._track(0, is_drum=True),
            self._track(1, is_drum=True),
        )
        self.assertEqual(plan.noise_tracks, [0])
        self.assertEqual(plan.dpcm_tracks, [0])
        self.assertEqual(plan.dropped_tracks, [1])
        self.assertTrue(any("Dropped" in n for n in plan.notes))

    def test_create_arrangement_plan_accounts_for_every_track(self):
        """Public path: every input track ends up assigned or explicitly
        dropped — none silently disappears."""
        analyzer = VoiceRoleAnalyzer()
        for track_id, base in ((0, 72), (1, 60), (2, 48)):
            for i in range(8):
                analyzer.add_note(track_id, NoteInfo(
                    pitch=base + (i % 3), velocity=90,
                    start_frame=i * 10, end_frame=i * 10 + 8,
                ))
        plan = analyzer.create_arrangement_plan()
        accounted = set(
            plan.pulse1_tracks + plan.pulse2_tracks + plan.triangle_tracks
            + plan.noise_tracks + plan.dpcm_tracks + plan.dropped_tracks
        )
        self.assertEqual(accounted, {0, 1, 2})
        self.assertEqual(len(plan.tracks), 3)


if __name__ == "__main__":
    unittest.main()
