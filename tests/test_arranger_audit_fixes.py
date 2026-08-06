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

    def test_zero_gap_retrigger_starts_new_strike(self):
        """#391/ARR-2026-08-05-1: back-to-back same-period hits with no frame
        gap between them (routine under _apply_sustain's zero-gap bridging,
        e.g. fast repeated hi-hats) must each get their own peak/decay
        instead of collapsing into one truncated strike."""
        from arranger.voice_allocator import FrameByFrameAllocator
        nf = {}
        nf.update({f: {"period": 5, "volume": 8} for f in range(0, 3)})   # hit 1
        nf.update({f: {"period": 5, "volume": 12} for f in range(3, 6)})  # hit 2 (louder)
        nf.update({f: {"period": 5, "volume": 8} for f in range(6, 9)})   # hit 3
        out = FrameByFrameAllocator._apply_noise_strike_decay(nf)

        # All three hits survive with their own fresh peak...
        assert out[0]["volume"] == 8
        assert out[3]["volume"] == 12  # hit 2's peak is not discarded
        assert out[6]["volume"] == 8   # hit 3 is not dropped past the decay window
        # ...and each decays monotonically within its own 3-frame span.
        assert out[0]["volume"] >= out[1]["volume"] >= out[2]["volume"]
        assert out[3]["volume"] >= out[4]["volume"] >= out[5]["volume"]
        assert out[6]["volume"] >= out[7]["volume"] >= out[8]["volume"]

    def test_same_volume_run_still_truncates_as_one_strike(self):
        """A genuinely sustained single note (flat volume for its whole
        duration, matching _allocate_noise's per-note NoteInfo.velocity) is
        still one strike, not one-per-frame -- the volume-change check must
        not fragment a real sustain into spurious re-triggers."""
        from arranger.voice_allocator import FrameByFrameAllocator
        from nes.envelope_processor import NOISE_DECAY_FRAMES
        flat = {f: {"period": 5, "volume": 10} for f in range(12)}
        out = FrameByFrameAllocator._apply_noise_strike_decay(flat)
        assert sorted(out) == list(range(NOISE_DECAY_FRAMES))
        assert out[0]["volume"] == 10

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
