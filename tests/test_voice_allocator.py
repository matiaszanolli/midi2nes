"""Regression tests for VoiceAllocator's drum routing (#87 / ARR-04).

_allocate_dpcm and _allocate_noise used to re-derive drum routing with
hardcoded note lists and a recomputed noise-period formula instead of
consulting GM_DRUM_MAP (get_drum_mapping). Two concrete divergences: note 40
(Electric Snare) was treated as a DPCM snare even though GM_DRUM_MAP routes it
to NOISE, and the noise period was a linear (pitch-36)//6 formula instead of
GM_DRUM_MAP's curated per-drum values.
"""

import unittest

from arranger import (
    VoiceAllocator, NoteInfo, TrackAnalysis, ArrangementPlan, NESChannel,
)


def _note(pitch, vel=100):
    return NoteInfo(pitch=pitch, velocity=vel, start_frame=0, end_frame=10,
                     channel=9, program=0)


class TestDpcmRouting(unittest.TestCase):
    def setUp(self):
        self.va = VoiceAllocator()
        self.track_info = TrackAnalysis(track_id=0)

    def _candidates(self, *pitches):
        return [(0, _note(p), self.track_info) for p in pitches]

    def test_electric_snare_not_routed_to_dpcm(self):
        """Regression: note 40 is Electric Snare -> NOISE in GM_DRUM_MAP, but
        the old code hardcoded it as a DPCM snare (note.pitch in [38, 40])."""
        self.assertIsNone(self.va._allocate_dpcm(self._candidates(40)))

    def test_kick_notes_get_slot_zero(self):
        self.assertEqual(self.va._allocate_dpcm(self._candidates(35)), 0)
        self.assertEqual(self.va._allocate_dpcm(self._candidates(36)), 0)

    def test_acoustic_snare_gets_slot_one(self):
        self.assertEqual(self.va._allocate_dpcm(self._candidates(38)), 1)

    def test_kick_outranks_snare_when_both_present(self):
        """GM_DRUM_MAP gives kicks higher priority (9) than the acoustic
        snare (8); the higher-priority hit must win."""
        self.assertEqual(self.va._allocate_dpcm(self._candidates(38, 36)), 0)

    def test_no_dpcm_eligible_notes_returns_none(self):
        """A hi-hat (noise-only in GM_DRUM_MAP) must not fall through to a
        'generic sample' slot -- it simply has no DPCM allocation."""
        self.assertIsNone(self.va._allocate_dpcm(self._candidates(42)))

    def test_empty_notes_returns_none(self):
        self.assertIsNone(self.va._allocate_dpcm([]))


class TestNoisePeriodRouting(unittest.TestCase):
    def setUp(self):
        self.va = VoiceAllocator()
        self.track_info = TrackAnalysis(track_id=0)

    def _candidates(self, *pitches):
        return [(0, _note(p), self.track_info) for p in pitches]

    def test_uses_curated_gm_drum_map_period(self):
        """Regression: the old (pitch-36)//6 formula gave note 42 (closed
        hi-hat) and note 56 (cowbell) periods 1 and 3; GM_DRUM_MAP curates
        them as 0 and 8 respectively."""
        result = self.va._allocate_noise(self._candidates(42))
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 0)
        result = self.va._allocate_noise(self._candidates(56))
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 8)

    def test_electric_snare_uses_its_curated_period(self):
        result = self.va._allocate_noise(self._candidates(40))
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 4)

    def test_empty_notes_returns_none(self):
        self.assertIsNone(self.va._allocate_noise([]))

    def test_period_stays_in_valid_range(self):
        """Every mapped GM drum note must produce a period in 0-15."""
        for pitch in range(35, 82):
            result = self.va._allocate_noise(self._candidates(pitch))
            if result is not None:
                period, _ = result
                self.assertGreaterEqual(period, 0)
                self.assertLessEqual(period, 15)


class TestDrumTrackDualRouting(unittest.TestCase):
    """End-to-end set_arrangement -> allocate_frame for a drum track (#251).

    A drum track claims NOISE *and* DPCM. The old 1:1 Dict[int, NESChannel]
    let the DPCM assignment overwrite NOISE, so _allocate_noise always got an
    empty list and every noise-routed percussion hit (hi-hats, cymbals, toms,
    electric snare) was silently dropped. These tests route through the real
    set_arrangement -> allocate_frame path, which the direct-allocator tests
    above never exercised.
    """

    def _drum_plan(self, track_id=0):
        plan = ArrangementPlan()
        plan.tracks = [TrackAnalysis(track_id=track_id, is_drum_track=True)]
        # Mirrors VoiceRoleAnalyzer._assign_channels: a drum track lands in
        # both lists.
        plan.noise_tracks = [track_id]
        plan.dpcm_tracks = [track_id]
        return plan

    def test_drum_track_maps_to_both_noise_and_dpcm(self):
        va = VoiceAllocator()
        va.set_arrangement(self._drum_plan())
        self.assertEqual(
            va.track_assignments[0], [NESChannel.NOISE, NESChannel.DPCM]
        )

    def test_mixed_kit_emits_both_noise_and_dpcm(self):
        """A kick (DPCM) + closed hi-hat (NOISE) on the same frame must light
        up both channels, not just DPCM."""
        va = VoiceAllocator()
        va.set_arrangement(self._drum_plan())
        notes = {0: [_note(36), _note(42)]}  # kick -> DPCM, closed hat -> NOISE
        alloc = va.allocate_frame(notes)
        self.assertIsNotNone(alloc.dpcm, "kick should play on DPCM")
        self.assertIsNotNone(alloc.noise, "closed hi-hat should play on NOISE")

    def test_full_noise_kit_survives(self):
        """Every noise-routed percussion note reaches the noise channel across
        the song instead of being clobbered by DPCM."""
        va = VoiceAllocator()
        va.set_arrangement(self._drum_plan())
        # Two NOISE-only hits (open hat 46, pedal hat 44) and one DPCM hit.
        noise_frames = 0
        for pitch in (46, 44, 42):
            alloc = va.allocate_frame({0: [_note(pitch)]})
            if alloc.noise is not None:
                noise_frames += 1
        self.assertEqual(noise_frames, 3)

    def test_kick_does_not_double_hit_noise(self):
        """A DPCM-routed kick alone must NOT also fire the noise channel —
        per-note dispatch sends it to DPCM only."""
        va = VoiceAllocator()
        va.set_arrangement(self._drum_plan())
        alloc = va.allocate_frame({0: [_note(36)]})  # kick only
        self.assertIsNotNone(alloc.dpcm)
        self.assertIsNone(alloc.noise)

    def test_single_channel_track_unchanged(self):
        """A plain melodic track still routes every note to its one channel."""
        plan = ArrangementPlan()
        plan.tracks = [TrackAnalysis(track_id=1)]
        plan.pulse1_tracks = [1]
        va = VoiceAllocator()
        va.set_arrangement(plan)
        self.assertEqual(va.track_assignments[1], [NESChannel.PULSE1])
        alloc = va.allocate_frame({1: [_note(60)]})
        self.assertIsNotNone(alloc.pulse1)
