"""Regression coverage for the 2026-07-19 arranger audit fixes #359 and #360.

- #359/ARR-2026-07-19-1: arranger percussion is reshaped into a decaying strike
  (via the shared decay helper) instead of a flat sustained-hiss burst, matching
  the legacy NESEmulatorCore noise path.
- #360/ARR-2026-07-19-2: analyze_midi_events no longer declares the dead
  ticks_per_beat/tempo/fps parameters.
"""

import inspect


# ---------------------------------------------------------------------------
# #359: arranger noise strike-decay
# ---------------------------------------------------------------------------

class TestArrangerNoiseStrikeDecay:
    def test_flat_run_becomes_short_decay(self):
        from arranger.voice_allocator import FrameByFrameAllocator
        from nes.envelope_processor import NOISE_DECAY_FRAMES
        # A 15-frame flat percussion hold (the old sustained-hiss behavior).
        flat = {f: {"period": 5, "volume": 8} for f in range(15)}
        out = FrameByFrameAllocator._apply_noise_strike_decay(flat)
        frames = sorted(out)
        # Truncated to a single strike length...
        assert frames == list(range(NOISE_DECAY_FRAMES))
        vols = [out[f]["volume"] for f in frames]
        # ...that decays monotonically from the peak and never hits 0.
        assert vols[0] == 8
        assert all(a >= b for a, b in zip(vols, vols[1:]))
        assert all(1 <= v <= 15 for v in vols)
        # Period is untouched (noise has no pitch table).
        assert all(out[f]["period"] == 5 for f in frames)

    def test_separate_hits_each_decay(self):
        from arranger.voice_allocator import FrameByFrameAllocator
        nf = {f: {"period": 5, "volume": 8} for f in range(15)}
        nf.update({f: {"period": 7, "volume": 10} for f in range(20, 32)})
        out = FrameByFrameAllocator._apply_noise_strike_decay(nf)
        assert out[0]["volume"] == 8 and out[20]["volume"] == 10  # both peaks kept
        assert max(f for f in out if f < 15) < 6   # first hit truncated
        assert 20 in out and out[20]["period"] == 7  # second hit starts fresh

    def test_period_change_starts_new_strike(self):
        from arranger.voice_allocator import FrameByFrameAllocator
        # Contiguous frames but a period change mid-run = a re-trigger.
        nf = {0: {"period": 5, "volume": 9}, 1: {"period": 5, "volume": 9},
              2: {"period": 8, "volume": 9}, 3: {"period": 8, "volume": 9}}
        out = FrameByFrameAllocator._apply_noise_strike_decay(nf)
        assert out[2]["volume"] == 9  # frame 2 is a fresh peak, not mid-decay

    def test_empty_noise_is_noop(self):
        from arranger.voice_allocator import FrameByFrameAllocator
        assert FrameByFrameAllocator._apply_noise_strike_decay({}) == {}

    def test_shared_helper_matches_legacy_formula(self):
        from nes.envelope_processor import noise_strike_decay_volume
        # Both front-ends use this; ramp = round(peak*(span-offset)/span), min 1.
        assert noise_strike_decay_volume(15, 0, 6) == 15
        # round(15*(6-5)/6) = round(2.5) = 2 (Python banker's rounding)
        assert noise_strike_decay_volume(15, 5, 6) == 2
        assert noise_strike_decay_volume(1, 5, 6) == 1   # floored, never silent
        assert noise_strike_decay_volume(8, 0, 0) == 8   # degenerate span guard


# ---------------------------------------------------------------------------
# #360: analyze_midi_events dead-parameter removal
# ---------------------------------------------------------------------------

class TestAnalyzeMidiEventsSignature:
    def test_no_dead_tempo_params(self):
        from arranger.pipeline_integration import analyze_midi_events
        params = inspect.signature(analyze_midi_events).parameters
        for dead in ("ticks_per_beat", "tempo", "fps"):
            assert dead not in params, f"{dead} should have been dropped"
        assert set(params) == {"midi_events", "sustain", "sustain_gap"}

    def test_still_callable_with_events_only(self):
        from arranger.pipeline_integration import analyze_midi_events
        events = {"melody": [
            {"frame": 0, "note": 60, "velocity": 100},
            {"frame": 8, "note": 0, "velocity": 0},
        ]}
        _, _, total_frames = analyze_midi_events(events)
        assert total_frames >= 8
