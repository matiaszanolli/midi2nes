"""Behavioral tests for the --arranger front-end (#44 / REG-04).

The arranger (`arrange_for_nes`) is one of the two front-ends that turn MIDI into
the downstream `frames` contract (the other is the legacy
`NESEmulatorCore.process_all_tracks`). It had zero test references, so role
detection, arpeggiation, channel-honoring, and the output contract were all
unguarded. These pin the behavior a polyphonic (--arranger) run relies on.
"""

import unittest

from arranger import arrange_for_nes, analyze_midi_events, MusicalRole
from nes.emulator_core import NESEmulatorCore

NES_CHANNELS = {'pulse1', 'pulse2', 'triangle', 'noise', 'dpcm'}
DEFAULT_ARP_SPEED = 3  # frames per arp step == 20Hz at 60fps (docs/arpeggio.md)


def _held(pitch, start, dur, vel=100, chan=0, program=None):
    """A note-on/note-off event pair for one held note (arranger input format:
    note-off is velocity 0)."""
    on = {'frame': start, 'note': pitch, 'velocity': vel, 'channel': chan}
    off = {'frame': start + dur, 'note': pitch, 'velocity': 0, 'channel': chan}
    if program is not None:
        on['program'] = program
        off['program'] = program
    return [on, off]


class TestArrangerRoleAnalysis(unittest.TestCase):
    def test_lowest_track_is_bass_highest_is_melody(self):
        """Role detection must tag the lowest-average-pitch track as BASS and the
        highest as MELODY (#44)."""
        events = {
            'low':  _held(36, 0, 40) + _held(38, 40, 40),   # bass register
            'high': _held(72, 0, 40) + _held(74, 40, 40),   # melody register
        }
        plan, _, _ = analyze_midi_events(events)
        roles = {t.name: t.role for t in plan.tracks}
        self.assertEqual(roles['low'], MusicalRole.BASS)
        self.assertEqual(roles['high'], MusicalRole.MELODY)


class TestApplySustainDoesNotMergeFastSequentialNotes(unittest.TestCase):
    """Regression (#296/ARR-NEW-4): _apply_sustain grouped any notes starting
    within chord_tolerance (2 frames) of each other into a "chord" and
    stretched every member to the group's max end_frame, regardless of
    whether they actually overlapped. A fast sequential monophonic run
    (notes <=2 frames apart, non-overlapping) got merged this way,
    manufacturing false polyphony that the arpeggiator then silently
    dropped every other note of."""

    def test_fast_sequential_run_keeps_every_note(self):
        pitches = [60, 62, 64, 65, 67, 69, 71, 72]
        events = []
        for i, p in enumerate(pitches):
            events.extend(_held(p, i * 2, 2))  # back-to-back, 2 frames apart
        _, notes_by_track, _ = analyze_midi_events({'melody': events})
        surviving_pitches = sorted(n.pitch for n in notes_by_track[0])
        self.assertEqual(surviving_pitches, sorted(pitches))

    def test_genuine_chord_still_extends_to_shared_end(self):
        """A real chord (near-simultaneous onset, genuinely overlapping
        durations) must still be recognized and extended together -- the fix
        must only stop merging non-overlapping notes, not chords."""
        events = (
            _held(60, 0, 20) +   # bass note: start=0, end=20
            _held(64, 1, 19) +   # third: start=1, end=20, overlaps the bass note
            _held(67, 2, 15)     # fifth: start=2, end=17, overlaps both -- shorter
        )
        _, notes_by_track, _ = analyze_midi_events({'chord': events})
        ends = {n.pitch: n.end_frame for n in notes_by_track[0]}
        # All three overlap in time, so they form one chord and extend to
        # the group's max end_frame (20).
        self.assertEqual(ends[60], 20)
        self.assertEqual(ends[64], 20)
        self.assertEqual(ends[67], 20)


class TestDrumTrackAnalysisNoDeadAttribute(unittest.TestCase):
    """Regression (#207/ARR-12): _analyze_drum_track used to set an ad-hoc
    `analysis.notes` instance attribute -- not a declared TrackAnalysis
    field, and nothing ever read it (the only `.notes` reader in arranger/ is
    the distinct ArrangementPlan.notes list). Pin that a drum track with
    kicks/snares no longer carries this dead, misleading attribute."""

    def test_drum_track_with_kicks_and_snares_has_no_notes_attribute(self):
        events = {
            'drums': [
                {'frame': 0, 'note': 36, 'volume': 100, 'type': 'note_on', 'channel': 9},   # kick
                {'frame': 5, 'note': 36, 'volume': 0, 'type': 'note_off', 'channel': 9},
                {'frame': 10, 'note': 38, 'volume': 100, 'type': 'note_on', 'channel': 9},  # snare
                {'frame': 15, 'note': 38, 'volume': 0, 'type': 'note_off', 'channel': 9},
            ]
        }
        plan, _, _ = analyze_midi_events(events)
        track = plan.tracks[0]
        self.assertTrue(track.is_drum_track)
        self.assertFalse(hasattr(track, 'notes'))


class TestArrangerGMProgramHint(unittest.TestCase):
    """Regression (#86 / ARR-03): `program` used to be hardcoded to 0 in
    analyze_midi_events and never updated, making the entire GM instrument
    table and GM-driven role/channel/duty selection dead code."""

    def test_program_is_carried_from_events_to_track_analysis(self):
        events = {'bass_track': _held(40, 0, 40, program=33)}  # GM 33: Electric Bass
        plan, _, _ = analyze_midi_events(events)
        track = next(t for t in plan.tracks if t.name == 'bass_track')
        self.assertEqual(track.program, 33)

    def test_program_defaults_to_zero_when_absent(self):
        """Events without a 'program' field (e.g. an older upstream parse)
        must default to GM program 0, not crash."""
        events = {'melody_track': _held(72, 0, 40)}  # no program kwarg
        plan, _, _ = analyze_midi_events(events)
        track = next(t for t in plan.tracks if t.name == 'melody_track')
        self.assertEqual(track.program, 0)

    def test_notes_pick_up_program_active_at_note_on(self):
        """A mid-track instrument change must be reflected per-note (the
        program active when each note started), not just at the track level."""
        events = {
            'track': (_held(40, 0, 40, program=33)      # Electric Bass
                      + _held(67, 60, 40, program=56)),  # Trumpet
        }
        _, notes_by_track, _ = analyze_midi_events(events)
        notes = notes_by_track[0]
        bass_note = next(n for n in notes if n.pitch == 40)
        trumpet_note = next(n for n in notes if n.pitch == 67)
        self.assertEqual(bass_note.program, 33)
        self.assertEqual(trumpet_note.program, 56)

    def test_track_program_uses_most_common_not_first_note(self):
        """Regression (#308): a program_change arriving after the first note-on
        (e.g. a leading pickup note) must not misidentify the track as program 0.
        The representative program is the most frequent across the track, not the
        first note's."""
        events = {
            'track': (_held(60, 0, 2, program=0)       # leading pickup, default piano
                      + _held(43, 4, 4, program=38)    # Synth Bass — the real instrument
                      + _held(45, 10, 4, program=38)
                      + _held(47, 16, 4, program=38)),
        }
        plan, _, _ = analyze_midi_events(events)
        track = next(t for t in plan.tracks if t.name == 'track')
        self.assertEqual(track.program, 38)


class TestArrangerArpeggiation(unittest.TestCase):
    def _chord_events(self):
        # C-E-G triad struck together and released together on one track.
        ev = []
        for pitch in (60, 64, 67):
            ev += _held(pitch, 0, 30)
        return {'chords': ev}

    @staticmethod
    def _arp_channel(out):
        """The pulse channel carrying the arpeggiated chord (most populated)."""
        return max(('pulse1', 'pulse2'), key=lambda c: len(out[c]))

    def test_chord_becomes_alternating_single_notes(self):
        """A 3-note chord must collapse to an alternating SINGLE-note sequence on
        one monophonic channel that cycles through all three chord tones — not a
        dropped-to-one-note or a simultaneous (impossible) triad."""
        out = arrange_for_nes(self._chord_events())
        ch = self._arp_channel(out)
        frames = out[ch]
        self.assertGreater(len(frames), 0)
        # Each frame is a single note (monophonic channel).
        for fd in frames.values():
            self.assertIn('note', fd)
        # All three chord tones appear over the arpeggio window.
        early = [frames[f]['note'] for f in sorted(frames)[:9]]
        self.assertEqual(set(early), {60, 64, 67},
                         "arpeggiation must cycle through every chord tone")

    def test_arpeggio_step_is_frame_aligned_at_arp_speed(self):
        """The arp note holds for arp_speed frames then steps — 20Hz on the 60Hz
        grid (docs/arpeggio.md: arpeggio speed aligns to frame boundaries)."""
        out = arrange_for_nes(self._chord_events())
        frames = out[self._arp_channel(out)]
        ordered = [frames[f]['note'] for f in sorted(frames)[:DEFAULT_ARP_SPEED * 2]]
        # First arp_speed frames identical, then a change (a real step).
        self.assertTrue(all(n == ordered[0] for n in ordered[:DEFAULT_ARP_SPEED]))
        self.assertNotEqual(ordered[DEFAULT_ARP_SPEED], ordered[DEFAULT_ARP_SPEED - 1])

    def test_arpeggio_starts_on_chord_root(self):
        """The first emitted arp note must be the chord root (lowest tone). The
        old code advanced the arp index before the first read, so the root was
        skipped on the attack and only sounded after a full cycle (#252)."""
        out = arrange_for_nes(self._chord_events())
        frames = out[self._arp_channel(out)]
        first_note = frames[sorted(frames)[0]]['note']
        self.assertEqual(first_note, 60,
                         "arpeggio must start on the lowest chord tone (root)")


class TestDrumNoisePeriodRendering(unittest.TestCase):
    """Pins how a period-0 drum renders (#253).

    GM_DRUM_MAP curates the Closed Hi-Hat at noise_period=0 (top frequency), but
    0 is the noise-bytecode rest sentinel and is floored to 1 downstream. This
    tension is accepted rather than remapping the sentinel scheme, so the closed
    hi-hat renders at period 1 — pin that so the behavior is deliberate, not an
    accidental regression. (Observable only since #251 stopped dropping noise.)
    """

    def _closed_hihat_events(self):
        return {'drums': [
            {'frame': 0, 'note': 42, 'volume': 100, 'type': 'note_on', 'channel': 9},
            {'frame': 3, 'note': 42, 'volume': 0, 'type': 'note_off', 'channel': 9},
        ]}

    def test_closed_hihat_renders_at_period_one(self):
        from arranger.gm_instruments import get_drum_mapping
        # The curated intent is the top frequency (period 0)...
        self.assertEqual(get_drum_mapping(42).noise_period, 0)

        out = arrange_for_nes(self._closed_hihat_events())
        self.assertGreater(len(out['noise']), 0, "closed hi-hat should hit noise")
        periods = {fd['note'] for fd in out['noise'].values()}
        # ...but 0 is the rest sentinel, so every emitted hit floors to 1.
        self.assertNotIn(0, periods,
                         "period 0 is the rest sentinel and must never be emitted")
        self.assertEqual(periods, {1},
                         "closed hi-hat (curated period 0) must render at period 1")


class TestChannelHonoringInvariant(unittest.TestCase):
    """Triangle has no duty (docs/APU_TRIANGLE_REFERENCE.md). BOTH front-ends
    must keep the triangle channel duty-free (#44 SIBLING)."""

    def test_arranger_triangle_has_no_duty(self):
        bass = {'bass': _held(36, 0, 18) + _held(38, 20, 18) + _held(41, 40, 18)}
        out = arrange_for_nes(bass)
        self.assertGreater(len(out['triangle']), 0, "bass should route to triangle")
        for fd in out['triangle'].values():
            self.assertNotIn('duty', fd)
            # Triangle control is the linear-counter byte ($81), never a pulse
            # (duty<<6) control byte.
            self.assertEqual(fd['control'], 0x81)

    def test_legacy_triangle_has_no_duty(self):
        core = NESEmulatorCore()
        out = core.process_all_tracks(
            {'triangle': [{'frame': 0, 'note': 36, 'volume': 100},
                          {'frame': 10, 'note': 38, 'volume': 100}]})
        self.assertGreater(len(out['triangle']), 0)
        for fd in out['triangle'].values():
            self.assertNotIn('duty', fd)
            self.assertNotIn('control', fd)  # legacy triangle emits no control byte


class TestArrangerContract(unittest.TestCase):
    """arrange_for_nes must be structurally interchangeable with
    process_all_tracks: {channel: {frame(int): {field: ...}}} (#44)."""

    @staticmethod
    def _assert_frames_shape(tc, out):
        tc.assertIsInstance(out, dict)
        for channel, ch_frames in out.items():
            tc.assertIn(channel, NES_CHANNELS)
            tc.assertIsInstance(ch_frames, dict)
            for frame, fd in ch_frames.items():
                tc.assertIsInstance(frame, int)
                tc.assertIsInstance(fd, dict)
                tc.assertIn('note', fd)

    def test_arranger_output_shape(self):
        out = arrange_for_nes({'melody': _held(60, 0, 20) + _held(64, 20, 20)})
        self._assert_frames_shape(self, out)
        # Channel vocabulary is a subset of the canonical NES channels.
        self.assertTrue(set(out).issubset(NES_CHANNELS))

    def test_both_front_ends_share_the_frames_shape(self):
        arr = arrange_for_nes({'melody': _held(60, 0, 20) + _held(64, 20, 20)})
        legacy = NESEmulatorCore().process_all_tracks(
            {'pulse1': [{'frame': 0, 'note': 60, 'volume': 100},
                        {'frame': 20, 'note': 64, 'volume': 100}]})
        self._assert_frames_shape(self, arr)
        self._assert_frames_shape(self, legacy)
        # Both draw channel names from the same NES vocabulary.
        self.assertTrue(set(arr).issubset(NES_CHANNELS))
        self.assertTrue(set(legacy).issubset(NES_CHANNELS))


class TestMidiNoteToNesPitchMatchesCanonicalTable(unittest.TestCase):
    """Regression tests for #89/ARR-06 and #90/ARR-07.

    midi_note_to_nes_pitch used to hand-roll its own float timer formula
    (a second pitch source diverging from nes/pitch_table.py and the
    exporter's midi_note_to_timer_value) with a floor-0 clamp instead of the
    hardware-correct floor-8 clamp, plus a dead, unclamped noise branch."""

    def test_matches_canonical_pulse_table(self):
        from arranger.pipeline_integration import midi_note_to_nes_pitch
        from nes.pitch_table import NES_NOTE_TABLE
        for note in range(0, 128):
            self.assertEqual(midi_note_to_nes_pitch(note, 'pulse1'), NES_NOTE_TABLE[note])
            self.assertEqual(midi_note_to_nes_pitch(note, 'pulse2'), NES_NOTE_TABLE[note])

    def test_matches_canonical_triangle_table(self):
        from arranger.pipeline_integration import midi_note_to_nes_pitch
        from nes.pitch_table import NES_TRIANGLE_TABLE
        for note in range(0, 128):
            self.assertEqual(midi_note_to_nes_pitch(note, 'triangle'), NES_TRIANGLE_TABLE[note])

    def test_high_notes_floor_at_8_not_0(self):
        """The old hand-rolled formula clamped to max(0, min(2047, period)),
        which could emit a timer below 8 for extreme high notes -- silencing
        the channel per APU_PULSE_REFERENCE §3/§7 instead of floor-ing at the
        lowest audible timer like every other pitch source in this codebase."""
        from arranger.pipeline_integration import midi_note_to_nes_pitch
        for note in (120, 125, 127):
            self.assertGreaterEqual(midi_note_to_nes_pitch(note, 'pulse1'), 8)
            self.assertGreaterEqual(midi_note_to_nes_pitch(note, 'triangle'), 8)

    def test_out_of_range_midi_notes_are_clamped(self):
        from arranger.pipeline_integration import midi_note_to_nes_pitch
        from nes.pitch_table import NES_NOTE_TABLE
        self.assertEqual(midi_note_to_nes_pitch(-5, 'pulse1'), NES_NOTE_TABLE[0])
        self.assertEqual(midi_note_to_nes_pitch(200, 'pulse1'), NES_NOTE_TABLE[127])


if __name__ == '__main__':
    unittest.main()
