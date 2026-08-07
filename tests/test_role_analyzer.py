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

    def test_harmony_track_no_longer_steals_triangle_from_higher_priority_melody(self):
        """Regression (#409/ARR-2026-08-06-2): the triangle-overflow fallback
        used to be gated on `role != MELODY` (any non-MELODY role, including
        HARMONY/DECORATIVE, could claim it), not `role == BASS`. Because the
        exclusion was role-based rather than priority-based, a
        HIGHER-priority MELODY track processed earlier could be dropped for
        lack of a channel while a LOWER-priority HARMONY track processed
        later still claimed the now-idle triangle -- the opposite of
        create_arrangement_plan's own "highest priority survives" policy
        (plan.tracks is priority-sorted before _assign_channels runs, so the
        passed order here already reflects that sort: 3 MELODY tracks ahead
        of 1 HARMONY track, no BASS)."""
        plan = self._assign(
            self._track(0, NESChannel.PULSE1, MusicalRole.MELODY),
            self._track(1, NESChannel.PULSE1, MusicalRole.MELODY),
            self._track(2, NESChannel.PULSE1, MusicalRole.MELODY),
            self._track(3, NESChannel.ANY_PULSE, MusicalRole.HARMONY),
        )
        self.assertEqual(plan.pulse1_tracks, [0])
        self.assertEqual(plan.pulse2_tracks, [1])
        # Triangle must stay empty -- no BASS track exists to claim it.
        self.assertEqual(plan.triangle_tracks, [])
        # Both the MELODY overflow AND the HARMONY track must drop; neither
        # survives at the other's expense.
        self.assertEqual(plan.dropped_tracks, [2, 3])

    def test_decorative_track_also_cannot_claim_triangle(self):
        """Sibling of the above for DECORATIVE, the other role that used to
        be eligible for the triangle-overflow fallback."""
        plan = self._assign(
            self._track(0, NESChannel.PULSE1, MusicalRole.MELODY),
            self._track(1, NESChannel.PULSE1, MusicalRole.MELODY),
            self._track(2, NESChannel.PULSE2, MusicalRole.DECORATIVE),
        )
        self.assertEqual(plan.triangle_tracks, [])
        self.assertEqual(plan.dropped_tracks, [2])

    def test_drum_track_claims_noise_and_dpcm(self):
        plan = self._assign(
            self._track(0, role=MusicalRole.PERCUSSION, is_drum=True)
        )
        self.assertEqual(plan.noise_tracks, [0])
        self.assertEqual(plan.dpcm_tracks, [0])
        self.assertEqual(plan.dropped_tracks, [])

    def test_drum_track_also_shares_pulse2(self):
        """Regression (#330/ARR-NEW-6): a drum track must also land in
        plan.pulse2_tracks (non-exclusively) so GM_DRUM_MAP's PULSE2-mapped
        percussion (agogo/cuica/mute+open triangle) can actually reach
        PULSE2 via _route_note instead of always collapsing onto NOISE."""
        plan = self._assign(
            self._track(0, role=MusicalRole.PERCUSSION, is_drum=True)
        )
        self.assertEqual(plan.pulse2_tracks, [0])

    def test_drum_track_sharing_pulse2_does_not_block_melodic_track(self):
        """The drum track's PULSE2 share must not be exclusive: a melodic
        track preferring PULSE2 must still land there (drum sharing doesn't
        set pulse2_assigned)."""
        plan = self._assign(
            self._track(0, role=MusicalRole.PERCUSSION, is_drum=True),
            self._track(1, NESChannel.PULSE2, MusicalRole.MELODY),
        )
        self.assertIn(0, plan.pulse2_tracks)
        self.assertIn(1, plan.pulse2_tracks)
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
        # A fully-dropped drum track (won neither noise nor DPCM) must not
        # still pick up a PULSE2 slot (#330/ARR-NEW-6) -- that would
        # contradict "dropped" and give it a channel assignment anyway.
        self.assertNotIn(1, plan.pulse2_tracks)

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


class TestDetermineRoleChannelCuration(unittest.TestCase):
    """Coverage for _determine_role's GM-curated channel handling (#408/
    ARR-2026-08-06-1). Previously every non-drum track's preferred_channel
    was unconditionally overwritten by a 4-bucket role->channel table after
    being seeded from GM_INSTRUMENT_MAP, so a curated choice like Ocarina/
    Whistle/Blown Bottle -> TRIANGLE (a breathy timbre) never survived."""

    def setUp(self):
        self.analyzer = VoiceRoleAnalyzer()

    def test_curated_triangle_channel_survives_when_role_agrees_with_gm_hint(self):
        """Ocarina (program 79) is curated MELODY/TRIANGLE. A track whose
        musical characteristics also score highest for MELODY must keep the
        curated TRIANGLE channel instead of being collapsed to PULSE1."""
        analysis = TrackAnalysis(
            track_id=0, name="ocarina", program=79,
            avg_pitch=66.0,       # mid-high range -> favors MELODY, not BASS
            note_density=1.0,     # neither sparse nor dense
            avg_velocity=80.0,    # neutral
            max_polyphony=1,
        )
        self.analyzer._determine_role(analysis)

        self.assertEqual(analysis.role, MusicalRole.MELODY)
        self.assertEqual(analysis.preferred_channel, NESChannel.TRIANGLE)

    def test_curated_channel_is_overridden_when_analysis_disagrees_with_gm_hint(self):
        """Same Ocarina GM hint (MELODY/TRIANGLE), but musical analysis
        strongly indicates BASS (very low average pitch) -- the override
        must still apply since actual analysis disagrees with the GM hint,
        landing on TRIANGLE via the BASS branch rather than via curation."""
        analysis = TrackAnalysis(
            track_id=0, name="ocarina_bass_register", program=79,
            avg_pitch=30.0,        # well below BASS_THRESHOLD (48)
            note_density=1.0,
            avg_velocity=80.0,
            max_polyphony=1,
        )
        self.analyzer._determine_role(analysis)

        self.assertEqual(analysis.role, MusicalRole.BASS)
        self.assertEqual(analysis.preferred_channel, NESChannel.TRIANGLE)
        self.assertGreaterEqual(analysis.priority, 8)

    def test_curated_any_pulse_channel_survives_when_role_agrees(self):
        """Electric Piano 1 (program 4) is curated HARMONY/ANY_PULSE. When
        the detected role agrees, ANY_PULSE should survive rather than being
        hardcoded to PULSE2 -- ANY_PULSE already resolves flexibly in
        _assign_channels, so this is strictly more capable, not a behavior
        loss."""
        analysis = TrackAnalysis(
            track_id=0, name="epiano", program=4,
            avg_pitch=60.0, note_density=0.3, avg_velocity=70.0,
            max_polyphony=3,   # pushes toward HARMONY (chords)
        )
        self.analyzer._determine_role(analysis)

        self.assertEqual(analysis.role, MusicalRole.HARMONY)
        self.assertEqual(analysis.preferred_channel, NESChannel.ANY_PULSE)


if __name__ == "__main__":
    unittest.main()
