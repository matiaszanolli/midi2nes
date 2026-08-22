"""Regression tests for core/events.py's event_velocity (#460/TD-40).

Pins the single documented precedence/default the 15 former hand-rolled
dual-key call sites (tracker/track_mapper.py, tracker/pattern_detector.py,
dpcm_sampler/enhanced_drum_mapper.py, arranger/pipeline_integration.py,
nes/emulator_core.py) were migrated to, so a future edit can't silently
re-diverge them.
"""
import unittest

from core.events import event_velocity


class TestEventVelocity(unittest.TestCase):
    def test_reads_velocity_key(self):
        self.assertEqual(event_velocity({'velocity': 90}), 90)

    def test_reads_volume_key_when_velocity_absent(self):
        self.assertEqual(event_velocity({'volume': 80}), 80)

    def test_velocity_takes_precedence_when_both_present(self):
        """The documented precedence: velocity wins over volume when an
        event (a hand-built/malformed one -- real producers emit exactly
        one key) carries both with different values."""
        self.assertEqual(event_velocity({'velocity': 90, 'volume': 40}), 90)

    def test_defaults_to_zero_when_neither_key_present(self):
        """0 (silent/note-off) is the safe default for the vast majority
        of call sites -- a missing-both event reads as no-op rather than
        a spurious note-on."""
        self.assertEqual(event_velocity({}), 0)

    def test_custom_default_is_honored(self):
        """A handful of call sites deliberately want a non-zero default
        (e.g. pattern-similarity scoring, where "missing" should read as
        "typical" rather than "silent")."""
        self.assertEqual(event_velocity({}, default=100), 100)

    def test_zero_velocity_is_not_treated_as_missing(self):
        """A genuine note-off (velocity/volume == 0) must read as 0, not
        fall through to the default -- .get()'s own semantics already
        guarantee this, but pin it explicitly since every caller's
        note-on/note-off branching depends on it."""
        self.assertEqual(event_velocity({'velocity': 0}), 0)
        self.assertEqual(event_velocity({'volume': 0}), 0)
        self.assertEqual(event_velocity({'velocity': 0}, default=100), 0)

    def test_does_not_mutate_the_event(self):
        event = {'volume': 50}
        event_velocity(event)
        self.assertEqual(event, {'volume': 50})


if __name__ == '__main__':
    unittest.main()
