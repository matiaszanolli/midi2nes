"""Behavioral tests for the --arranger front-end (#44 / REG-04).

The arranger (`arrange_for_nes`) is one of the two front-ends that turn MIDI into
the downstream `frames` contract (the other is the legacy
`NESEmulatorCore.process_all_tracks`). It had zero test references, so role
detection, arpeggiation, channel-honoring, and the output contract were all
unguarded. These pin the behavior a polyphonic (--arranger) run relies on.
"""

import contextlib
import io
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


class TestType0MultiChannelTrackSplit(unittest.TestCase):
    """Regression (#329/ARR-NEW-5): parser_fast groups events by MIDI track
    only, never by channel, so a Type-0 MIDI (one track carrying all 16
    channels, including channel-9 drums) -- or any multi-channel Type-1
    track -- used to reach role analysis as a single merged voice: the drum
    flag was sampled from only the first event with a channel, and one GM
    program was derived across every mixed channel. analyze_midi_events must
    now split a track's events by channel before analysis."""

    def _melody_and_drums_in_one_track(self):
        melody = _held(72, 0, 40, chan=0, program=80)  # program 80: lead
        kick = _held(36, 0, 10, chan=9, program=0)
        hihat = _held(42, 0, 5, chan=9, program=0)
        return {'track_0': melody + kick + hihat}

    def test_channel_9_drums_reach_noise_and_dpcm(self):
        events = self._melody_and_drums_in_one_track()
        plan, _, _ = analyze_midi_events(events)
        self.assertTrue(plan.noise_tracks, "channel-9 events must reach NOISE")
        # A kick (GM_DRUM_MAP use_sample) must reach DPCM too.
        self.assertTrue(plan.dpcm_tracks, "channel-9 events must reach DPCM")

    def test_drum_track_is_flagged_percussion_not_melody(self):
        events = self._melody_and_drums_in_one_track()
        plan, _, _ = analyze_midi_events(events)
        drum_tracks = [t for t in plan.tracks if t.is_drum_track]
        self.assertEqual(len(drum_tracks), 1)
        self.assertEqual(drum_tracks[0].role, MusicalRole.PERCUSSION)

    def test_melodic_channel_program_not_skewed_by_drum_channel(self):
        """Before the fix, Counter(programs).most_common(1) ran across BOTH
        channels mixed together -- with equal note counts here, program 0
        (the drum channel's GM program) could win over the melody's real
        program 80. Each channel must compute its program hint from only
        its own events."""
        events = self._melody_and_drums_in_one_track()
        plan, _, _ = analyze_midi_events(events)
        melodic_tracks = [t for t in plan.tracks if not t.is_drum_track]
        self.assertEqual(len(melodic_tracks), 1)
        self.assertEqual(melodic_tracks[0].program, 80)

    def test_pitched_channel_does_not_route_to_noise_or_dpcm(self):
        events = self._melody_and_drums_in_one_track()
        plan, _, _ = analyze_midi_events(events)
        melodic_ids = {t.track_id for t in plan.tracks if not t.is_drum_track}
        self.assertTrue(melodic_ids & set(plan.pulse1_tracks + plan.pulse2_tracks
                                           + plan.triangle_tracks))
        self.assertFalse(melodic_ids & set(plan.noise_tracks))
        self.assertFalse(melodic_ids & set(plan.dpcm_tracks))

    def test_single_channel_track_name_unchanged(self):
        """A track that carries only one channel (the common Type-1 case)
        must keep its plain name -- no 'chN' suffix -- so ordinary MIDI
        input produces byte-for-byte-identical output/logging."""
        events = {'melody': _held(72, 0, 40, chan=0, program=80)}
        plan, _, _ = analyze_midi_events(events)
        self.assertEqual(plan.tracks[0].name, 'melody')

    def test_multi_channel_track_gets_suffixed_names(self):
        events = self._melody_and_drums_in_one_track()
        plan, _, _ = analyze_midi_events(events)
        names = {t.name for t in plan.tracks}
        self.assertEqual(names, {'track_0 ch0', 'track_0 ch9'})

    def test_end_to_end_frames_have_no_events_on_noise_and_dpcm(self):
        """Full arrange_for_nes output must actually carry drum content on
        noise/dpcm, not just the intermediate plan."""
        from arranger import arrange_for_nes
        events = self._melody_and_drums_in_one_track()
        frames = arrange_for_nes(events)
        self.assertTrue(frames['noise'], "expected noise frames from the drum channel")


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


class TestOverlappingSamePitchNotesArePreserved(unittest.TestCase):
    """Regression (#449/ARR-2026-08-21-2): a note-on for a pitch that's
    already active used to silently overwrite the active slot -- the first
    onset never became a NoteInfo at all, and the note-off that followed
    closed the *second* onset, truncating it to the overlap window. This
    is routine in real MIDI (DAW legato exports, doubled unison voices)."""

    def test_second_note_on_closes_the_first_at_its_own_onset(self):
        events = [
            {'frame': 0, 'note': 60, 'velocity': 100, 'channel': 0},
            {'frame': 98, 'note': 60, 'velocity': 100, 'channel': 0},
            {'frame': 100, 'note': 60, 'velocity': 0, 'channel': 0},
        ]
        _, notes_by_track, _ = analyze_midi_events(
            {'melody': events}, sustain=False)
        notes = sorted(notes_by_track[0], key=lambda n: n.start_frame)
        # Both onsets survive: the first note-on closes at the second
        # note-on's frame instead of vanishing entirely.
        self.assertEqual(len(notes), 2)
        self.assertEqual((notes[0].start_frame, notes[0].end_frame), (0, 98))
        self.assertEqual((notes[1].start_frame, notes[1].end_frame), (98, 100))

    def test_zero_duration_retrigger_does_not_emit_a_ghost_note(self):
        """Two note-ons on the exact same frame (a malformed but real-world
        duplicate) must not manufacture a zero-length NoteInfo."""
        events = [
            {'frame': 0, 'note': 60, 'velocity': 100, 'channel': 0},
            {'frame': 0, 'note': 60, 'velocity': 100, 'channel': 0},
            {'frame': 10, 'note': 60, 'velocity': 0, 'channel': 0},
        ]
        _, notes_by_track, _ = analyze_midi_events(
            {'melody': events}, sustain=False)
        notes = notes_by_track[0]
        self.assertEqual(len(notes), 1)
        self.assertEqual((notes[0].start_frame, notes[0].end_frame), (0, 10))


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


class TestSubC1BassNotePitchMatchesChannelClampedTable(unittest.TestCase):
    """End-to-end regression for #431/NH-HW-2026-08-21-4: a sub-C1 bass note
    routed to triangle through the full arrange_for_nes pipeline must carry
    a frame `pitch` clamped to CHANNEL_RANGES['triangle'] (floor 24), the
    same floor the bytecode serializer's base timer uses -- not the raw,
    unclamped table lookup that produced a detuned runtime pitch."""

    def test_bass_note_below_c1_clamps_pitch_to_channel_floor(self):
        from nes.pitch_table import NES_TRIANGLE_TABLE, CHANNEL_RANGES

        # MIDI 21 (A0) -- below triangle's channel-range floor of 24 (C1).
        bass = {'bass': _held(21, 0, 18)}
        out = arrange_for_nes(bass)
        self.assertGreater(len(out['triangle']), 0, "sub-C1 bass should still route to triangle")

        floor_pitch = NES_TRIANGLE_TABLE[CHANNEL_RANGES['triangle'][0]]
        for fd in out['triangle'].values():
            self.assertEqual(fd['pitch'], floor_pitch,
                              "frame pitch must clamp to the channel-range floor "
                              "(table[24]), matching what the serializer's base "
                              "timer uses for a note this low")
            # The raw, unclamped table lookup (the pre-fix behavior) would have
            # produced a different, higher timer value -- confirm we're not
            # accidentally still returning it.
            self.assertNotEqual(fd['pitch'], NES_TRIANGLE_TABLE[21])


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
    """Regression tests for #89/ARR-06, #90/ARR-07, and #431/NH-HW-2026-08-21-4.

    midi_note_to_nes_pitch used to hand-roll its own float timer formula
    (a second pitch source diverging from nes/pitch_table.py and the
    exporter's midi_note_to_timer_value) with a floor-0 clamp instead of the
    hardware-correct floor-8 clamp, plus a dead, unclamped noise branch.

    It was later delegated to the canonical tables (#89/#90) but only
    clamped to the full MIDI 0-127 range, not the per-channel range
    PitchProcessor.get_channel_pitch (nes/pitch_table.py) clamps to before
    its own table lookup -- so an out-of-channel-range note (e.g. a sub-C1
    bass note on triangle) produced a `pitch` the bytecode serializer's
    channel-range-floored base timer disagreed with, detuning the note
    (#431). midi_note_to_nes_pitch must clamp to CHANNEL_RANGES[channel]
    exactly like get_channel_pitch."""

    def test_matches_canonical_pulse_table_within_channel_range(self):
        from arranger.pipeline_integration import midi_note_to_nes_pitch
        from nes.pitch_table import NES_NOTE_TABLE, CHANNEL_RANGES
        min_note, max_note = CHANNEL_RANGES['pulse1']
        for note in range(min_note, max_note + 1):
            self.assertEqual(midi_note_to_nes_pitch(note, 'pulse1'), NES_NOTE_TABLE[note])
            self.assertEqual(midi_note_to_nes_pitch(note, 'pulse2'), NES_NOTE_TABLE[note])

    def test_matches_canonical_triangle_table_within_channel_range(self):
        from arranger.pipeline_integration import midi_note_to_nes_pitch
        from nes.pitch_table import NES_TRIANGLE_TABLE, CHANNEL_RANGES
        min_note, max_note = CHANNEL_RANGES['triangle']
        for note in range(min_note, max_note + 1):
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

    def test_out_of_midi_range_notes_clamp_to_channel_range(self):
        """A note outside 0-127 must clamp to the channel's own range
        boundary (24-108 for pulse), not just the full MIDI range -- the
        clamp target IS the note whose table entry gets returned."""
        from arranger.pipeline_integration import midi_note_to_nes_pitch
        from nes.pitch_table import NES_NOTE_TABLE
        self.assertEqual(midi_note_to_nes_pitch(-5, 'pulse1'), NES_NOTE_TABLE[24])
        self.assertEqual(midi_note_to_nes_pitch(200, 'pulse1'), NES_NOTE_TABLE[108])

    def test_sub_channel_range_notes_clamp_to_channel_floor_not_full_midi_floor(self):
        """Regression for #431: a note below the channel's own range floor
        (e.g. 21 on triangle, whose floor is 24, not MIDI's 0) must clamp to
        the CHANNEL range floor -- matching PitchProcessor.get_channel_pitch
        -- not just the full 0-127 MIDI range. Before the fix, notes 0-23
        indexed the table directly instead of clamping to 24, producing a
        pitch the bytecode serializer's channel-floored base timer (also 24)
        disagreed with."""
        from arranger.pipeline_integration import midi_note_to_nes_pitch
        from nes.pitch_table import NES_TRIANGLE_TABLE, NES_NOTE_TABLE, CHANNEL_RANGES

        for note in range(0, CHANNEL_RANGES['triangle'][0]):
            self.assertEqual(midi_note_to_nes_pitch(note, 'triangle'),
                              NES_TRIANGLE_TABLE[CHANNEL_RANGES['triangle'][0]])
        for note in range(0, CHANNEL_RANGES['pulse1'][0]):
            self.assertEqual(midi_note_to_nes_pitch(note, 'pulse1'),
                              NES_NOTE_TABLE[CHANNEL_RANGES['pulse1'][0]])

    def test_matches_pitch_processor_get_channel_pitch_exactly(self):
        """midi_note_to_nes_pitch and PitchProcessor.get_channel_pitch are two
        independent call sites that must agree bit-for-bit on every MIDI note
        for every tone channel -- a drift between them is exactly the #431
        defect class."""
        from arranger.pipeline_integration import midi_note_to_nes_pitch
        from nes.pitch_table import PitchProcessor

        processor = PitchProcessor()
        for channel in ('pulse1', 'pulse2', 'triangle'):
            for note in range(0, 128):
                self.assertEqual(
                    midi_note_to_nes_pitch(note, channel),
                    processor.get_channel_pitch(note, channel),
                    f"mismatch at note={note} channel={channel}")


def _melodic_track(pitch, channel=0):
    return [
        {'frame': 0, 'note': pitch, 'volume': 100, 'channel': channel},
        {'frame': 10, 'note': pitch, 'volume': 0, 'channel': channel},
    ]


class TestDroppedTracksAreSurfaced(unittest.TestCase):
    """Regression (#451/ARR-2026-08-21-4): plan.dropped_tracks/plan.notes
    were faithfully recorded but never shown anywhere on the live path --
    an entire musical part could vanish from the ROM with zero indication,
    even under --verbose."""

    def _six_melodic_tracks(self):
        # 6 monophonic melodic tracks compete for pulse1/pulse2 -- more than
        # the pitched channels can hold, so several are dropped.
        return {f'track_{i}': _melodic_track(60 + i) for i in range(6)}

    def test_drops_are_warned_about_without_verbose(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            arrange_for_nes(self._six_melodic_tracks(), verbose=False)
        output = buf.getvalue()
        self.assertIn("Dropped", output)
        self.assertIn("Warning:", output)

    def test_no_drops_means_no_drop_warnings(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            arrange_for_nes({'melody': _melodic_track(60)}, verbose=False)
        self.assertNotIn("Dropped", buf.getvalue())

    def test_verbose_still_shows_the_full_analysis_and_the_drops(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            arrange_for_nes(self._six_melodic_tracks(), verbose=True)
        output = buf.getvalue()
        self.assertIn("NES ARRANGEMENT ANALYSIS", output)
        self.assertIn("DROPPED", output)
        self.assertIn("Dropped", output)


class TestMissingVelocityDefaultsToNoteOff(unittest.TestCase):
    """Regression (#460/TD-40): analyze_midi_events's velocity read used to
    default to 100 when an event carried neither 'velocity' nor 'volume' --
    treating a malformed/keyless event as a spurious note-on, diverging from
    every other velocity-reading site in the codebase (which default to 0,
    i.e. note-off/no-op). Migrated to core.events.event_velocity's shared
    default of 0."""

    def test_keyless_event_produces_no_note(self):
        from arranger import analyze_midi_events
        events = {'track': [
            {'frame': 0, 'note': 60},  # no 'velocity'/'volume' at all
        ]}
        _, notes_by_track, _ = analyze_midi_events(events, sustain=False)
        # No note-on ever registers, so no NoteInfo is produced for it.
        all_notes = [n for notes in notes_by_track.values() for n in notes]
        self.assertEqual(all_notes, [])


if __name__ == '__main__':
    unittest.main()
