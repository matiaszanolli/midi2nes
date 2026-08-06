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
    FrameByFrameAllocator,
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
                period, _velocity, _mode = result
                self.assertGreaterEqual(period, 0)
                self.assertLessEqual(period, 15)


class TestNoiseModeBit(unittest.TestCase):
    """Regression tests for #392/NH-HW-2026-08-05-1: --arranger had no
    producer for the noise mode bit ($400E bit 7), so hi-hats/cowbell always
    rendered as generic long-mode noise instead of the metallic/periodic
    timbre the legacy front-end's METALLIC_NOISE_ROLES produces for the same
    GM roles."""

    def setUp(self):
        self.va = VoiceAllocator()
        self.track_info = TrackAnalysis(track_id=0)

    def _candidates(self, *pitches):
        return [(0, _note(p), self.track_info) for p in pitches]

    def test_hihats_and_cowbell_get_periodic_mode(self):
        for pitch in (42, 44, 46, 56):  # closed/pedal/open hi-hat, cowbell
            result = self.va._allocate_noise(self._candidates(pitch))
            self.assertIsNotNone(result)
            _period, _velocity, mode = result
            self.assertEqual(mode, 1, f"GM note {pitch} should be periodic mode")

    def test_other_percussion_stays_long_mode(self):
        for pitch in (38, 40, 41, 49, 51, 60):  # snares, tom, cymbals, bongo
            result = self.va._allocate_noise(self._candidates(pitch))
            if result is not None:
                _period, _velocity, mode = result
                self.assertEqual(mode, 0, f"GM note {pitch} should stay long-mode")

    def test_pipeline_integration_sets_control_bit_6_for_hihat(self):
        """End-to-end: arrange_for_nes's noise output must carry the mode bit
        in `control` bit 6 for a closed hi-hat, matching the legacy
        front-end's $400E bit 7 semantics."""
        from arranger.pipeline_integration import arrange_for_nes
        midi_events = {
            'drums': [
                {'frame': 0, 'note': 42, 'velocity': 100, 'channel': 9, 'duration': 4},
            ]
        }
        frames = arrange_for_nes(midi_events, arp_speed=3, verbose=False)
        noise = frames.get('noise', {})
        self.assertTrue(noise, "expected noise frames for a hi-hat note")
        self.assertTrue(
            all(entry['control'] & 0x40 for entry in noise.values()),
            "closed hi-hat frames must have control bit 6 (mode) set",
        )

    def test_pipeline_integration_leaves_non_metallic_control_bit_6_clear(self):
        from arranger.pipeline_integration import arrange_for_nes
        midi_events = {
            'drums': [
                {'frame': 0, 'note': 49, 'velocity': 100, 'channel': 9, 'duration': 4},
            ]
        }
        frames = arrange_for_nes(midi_events, arp_speed=3, verbose=False)
        noise = frames.get('noise', {})
        self.assertTrue(noise, "expected noise frames for a crash cymbal note")
        self.assertTrue(
            all(not (entry['control'] & 0x40) for entry in noise.values()),
            "crash cymbal frames must not have control bit 6 (mode) set",
        )


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


class TestDrumTrackPulse2Routing(unittest.TestCase):
    """Regression (#330/ARR-NEW-6): GM_DRUM_MAP's PULSE2-mapped percussion
    (agogo/cuica/mute+open triangle) must actually reach PULSE2 when the
    drum track owns it, instead of _route_note's NOISE catch-all firing
    first and collapsing every non-DPCM hit onto NOISE regardless of the
    mapping table."""

    def _drum_plan_with_pulse2(self, track_id=0):
        plan = ArrangementPlan()
        plan.tracks = [TrackAnalysis(track_id=track_id, is_drum_track=True)]
        # Mirrors the real VoiceRoleAnalyzer._assign_channels output for a
        # drum track: noise + dpcm + a shared (non-exclusive) pulse2 slot.
        plan.noise_tracks = [track_id]
        plan.dpcm_tracks = [track_id]
        plan.pulse2_tracks = [track_id]
        return plan

    def test_agogo_routes_to_pulse2_not_noise(self):
        va = VoiceAllocator()
        va.set_arrangement(self._drum_plan_with_pulse2())
        alloc = va.allocate_frame({0: [_note(67)]})  # High Agogo -> PULSE2
        self.assertIsNotNone(alloc.pulse2, "agogo should play on PULSE2")
        self.assertIsNone(alloc.noise, "agogo must not also fire NOISE")

    def test_cuica_and_triangle_percussion_route_to_pulse2(self):
        va = VoiceAllocator()
        for pitch in (78, 79, 80, 81):  # Mute/Open Cuica, Mute/Open Triangle
            va.set_arrangement(self._drum_plan_with_pulse2())
            alloc = va.allocate_frame({0: [_note(pitch)]})
            self.assertIsNotNone(alloc.pulse2, f"pitch {pitch} should play on PULSE2")

    def test_tom_still_falls_to_noise_with_its_own_period(self):
        """Toms are TRIANGLE-mapped, but a drum track never owns TRIANGLE
        (reserved for bass), so they still fall through to NOISE -- now with
        a curated per-tom noise_period instead of the generic fallback 5."""
        va = VoiceAllocator()
        va.set_arrangement(self._drum_plan_with_pulse2())
        alloc = va.allocate_frame({0: [_note(41)]})  # Low Floor Tom
        self.assertIsNotNone(alloc.noise)
        self.assertEqual(alloc.noise[0], 11)
        self.assertIsNone(alloc.pulse2)

    def test_hi_hat_unaffected_by_reordered_precedence(self):
        """A plain NOISE-mapped drum (mapping.channel == NESChannel.NOISE)
        must still route to NOISE -- the reordered mapped-channel check is a
        no-op for it, not a behavior change."""
        va = VoiceAllocator()
        va.set_arrangement(self._drum_plan_with_pulse2())
        alloc = va.allocate_frame({0: [_note(42)]})  # Closed Hi-Hat
        self.assertIsNotNone(alloc.noise)
        self.assertIsNone(alloc.pulse2)

    def test_kick_still_routes_to_dpcm_over_pulse2(self):
        """DPCM-sample-eligible hits must still win over the mapped-channel
        check (which precedes it in _route_note is unaffected by this
        change's reordering, both checks come before the NOISE catch-all)."""
        va = VoiceAllocator()
        va.set_arrangement(self._drum_plan_with_pulse2())
        alloc = va.allocate_frame({0: [_note(36)]})  # Bass Drum 1 -> DPCM
        self.assertIsNotNone(alloc.dpcm)
        self.assertIsNone(alloc.pulse2)
        self.assertIsNone(alloc.noise)


class TestPulseVolumeFloor(unittest.TestCase):
    """Regression (#268/NH-30): FrameByFrameAllocator.process_song derived
    pulse volume as a bare `vel // 8` with no floor, so any note with MIDI
    velocity 1-7 (ppp phrasing, fade-ins/outs, ghost notes) integer-divided
    to volume 0 -- pitch/duty were still written, but the channel played at
    zero amplitude. Mirrors the legacy front-end's max(1, ...) volume floor
    in nes/emulator_core.py; triangle/noise already floor elsewhere."""

    def _pulse1_plan(self, track_id=1):
        plan = ArrangementPlan()
        plan.tracks = [TrackAnalysis(track_id=track_id)]
        plan.pulse1_tracks = [track_id]
        return plan

    def _pulse2_plan(self, track_id=1):
        plan = ArrangementPlan()
        plan.tracks = [TrackAnalysis(track_id=track_id)]
        plan.pulse2_tracks = [track_id]
        return plan

    def test_soft_velocity_pulse1_note_is_not_silenced(self):
        notes_by_track = {1: [_note(60, vel=5)]}  # 5 // 8 == 0 without a floor
        processor = FrameByFrameAllocator(total_frames=10)
        frames = processor.process_song(notes_by_track, self._pulse1_plan())
        self.assertIn(0, frames['pulse1'])
        self.assertGreaterEqual(frames['pulse1'][0]['volume'], 1)

    def test_soft_velocity_pulse2_note_is_not_silenced(self):
        notes_by_track = {1: [_note(60, vel=5)]}
        processor = FrameByFrameAllocator(total_frames=10)
        frames = processor.process_song(notes_by_track, self._pulse2_plan())
        self.assertIn(0, frames['pulse2'])
        self.assertGreaterEqual(frames['pulse2'][0]['volume'], 1)

    def test_loud_velocity_pulse1_volume_still_caps_at_15(self):
        notes_by_track = {1: [_note(60, vel=127)]}
        processor = FrameByFrameAllocator(total_frames=10)
        frames = processor.process_song(notes_by_track, self._pulse1_plan())
        self.assertEqual(frames['pulse1'][0]['volume'], 15)


class TestArpSpeedValidation(unittest.TestCase):
    """Regression (#91/ARR-08): arp_speed=0 raised ZeroDivisionError in
    _allocate_pulse (`state.arp_frame % self.arp_speed`). arp_speed is clamped
    to >= 1 at the VoiceAllocator property boundary so any caller (arrange_for_nes
    exposes it) is safe."""

    def test_zero_arp_speed_is_clamped(self):
        self.assertEqual(VoiceAllocator(arp_speed=0).arp_speed, 1)
        self.assertEqual(VoiceAllocator(arp_speed=-5).arp_speed, 1)
        self.assertEqual(VoiceAllocator(arp_speed=3).arp_speed, 3)

    def test_reassigning_zero_is_clamped(self):
        # allocate_with_arpeggiation reassigns processor.allocator.arp_speed
        # directly, bypassing __init__ — the property setter must guard it too.
        alloc = VoiceAllocator(arp_speed=3)
        alloc.arp_speed = 0
        self.assertEqual(alloc.arp_speed, 1)

    def test_zero_arp_speed_does_not_crash_arrangement(self):
        from arranger import arrange_for_nes
        events = {'chord': [
            {'frame': 0, 'note': 60, 'velocity': 100, 'channel': 0},
            {'frame': 0, 'note': 64, 'velocity': 100, 'channel': 0},
            {'frame': 0, 'note': 67, 'velocity': 100, 'channel': 0},
            {'frame': 30, 'note': 60, 'velocity': 0, 'channel': 0},
            {'frame': 30, 'note': 64, 'velocity': 0, 'channel': 0},
            {'frame': 30, 'note': 67, 'velocity': 0, 'channel': 0},
        ]}
        # Must not raise ZeroDivisionError.
        out = arrange_for_nes(events, arp_speed=0)
        self.assertIn('pulse1', out)
