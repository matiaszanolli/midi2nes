# ARR-2026-07-19-1: Arranger percussion emits flat-volume noise with no strike decay

Issue: #359 · Source: AUDIT_ARRANGER_2026-07-19.md

**Severity:** MEDIUM · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-07-19.md

## Description
The legacy front-end deliberately renders each noise/percussion hit as a short **decaying** strike — `NESEmulatorCore` writes a per-frame volume ramp over `NOISE_DECAY_FRAMES = 6` (~100 ms), cutting off on re-trigger (`nes/emulator_core.py:152, 172-178`), precisely because the engine forces constant-volume+halt (`$30` on `$400C`) and there is no hardware envelope to lean on (#162/NH-19). The arranger's noise path does none of this: `process_song` writes a single flat `volume = max(1, vel // 8)` for **every** frame the note is active (`arranger/voice_allocator.py:455-460`), so a percussion hit plays at constant amplitude for its whole duration rather than as a "tsh"/"tk" strike.

This is compounded by two arranger behaviors:
- (a) a drum note that never receives a note-off is given a fixed `end_frame = start_frame + 15` (`arranger/pipeline_integration.py:172-178`) = 250 ms of continuous noise;
- (b) `_apply_sustain` (default `sustain=True`, `sustain_gap=12`) extends and bridges drum notes across gaps, lengthening the burst further.

## Location
- `arranger/voice_allocator.py:455-460` (`process_song` noise emit)
- `arranger/pipeline_integration.py:172-183` (15-frame default duration)

## Evidence
Legacy `nes/emulator_core.py:172-178` builds `decayed_volume = max(1, round(peak_volume * (span - offset) / span))` per frame; arranger `arranger/voice_allocator.py:457-460` emits `{"period": period, "volume": max(1, vel // 8)}` with no offset/decay term.

## Impact
On the `--arranger` path, drum tracks (all noise-routed percussion: hi-hats, snares-not-sampled, cymbals, claps, toms-misrouted-to-noise) sound like sustained hiss bursts instead of crisp strikes. Playable, but audibly worse than legacy mode; workaround is to use the default (non-arranger) front-end. Blast radius: noise channel on every polyphonic `--arranger` build.

## Related
- #330 (toms→noise makes more instruments hit this path)
- Legacy decay is #162/NH-19.

## Suggested Fix
Apply the same short decay ramp used by `NESEmulatorCore` when materializing noise frames in `process_song` (or post-process the arranger's noise dict through the shared decay helper), and reconsider whether `_apply_sustain` should run on drum-detected tracks.

## Completeness Checks
- [ ] **RANGE**: The emitted noise `volume` stays clamped to the 4-bit range (0-15) after any decay ramp is added
- [ ] **CHANNEL**: Noise has no pitch table; the decay affects `volume` only (period is untouched)
- [ ] **SIBLING**: Decay/strike handling matches the legacy `NESEmulatorCore` noise path so both front-ends sound alike
- [ ] **TESTS**: A regression test pins the per-frame decay ramp on an arranger noise hit
- [ ] **DOC**: If behavior contradicts `docs/APU_NOISE_REFERENCE.md` / `docs/APU_ENVELOPE_REFERENCE.md`, the doc/comment is corrected
