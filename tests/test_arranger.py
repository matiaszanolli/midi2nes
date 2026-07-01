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


def _held(pitch, start, dur, vel=100, chan=0):
    """A note-on/note-off event pair for one held note (arranger input format:
    note-off is velocity 0)."""
    return [{'frame': start, 'note': pitch, 'velocity': vel, 'channel': chan},
            {'frame': start + dur, 'note': pitch, 'velocity': 0, 'channel': chan}]


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


if __name__ == '__main__':
    unittest.main()
