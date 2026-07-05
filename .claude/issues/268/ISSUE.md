# NH-30: Arranger pulse channels silence the softest notes — vel // 8 floors to volume 0 with no max(1, …) guard

**Severity:** MEDIUM · **Domain:** nes-hardware · **Source:** AUDIT_NES-HARDWARE_2026-07-05.md · **Dimension:** 6 (Velocity → 4-bit volume)

## Description
In `--arranger` mode the pulse1/pulse2 per-frame volume is derived as `vel // 8` from the MIDI velocity (0-127) with **no floor**. Any note with velocity 1-7 integer-divides to `0`, so the 4-bit volume nibble is `0` in both the stored `volume` field and the control byte (`… | 0x30 | 0` → e.g. `0xB0`): pitch and duty are written but the channel plays at **zero amplitude** — the note is inaudible.

The legacy `emulator_core` front-end deliberately avoids this with `max(1, int(15 * math.pow(velocity / 127.0, 1.5)))` (`nes/emulator_core.py:112,118`). The arranger applies neither the floor nor the power curve. The sibling arranger channels *do* floor (noise: `max(1, min(15, data['volume']))` at `arranger/pipeline_integration.py:276`; triangle: `15 if vel > 0 else 0` at `arranger/voice_allocator.py:378`), so only the pulse channels are exposed. The exporter's own velocity rescue (`is_midi_velocity` power curve) is dead code (#165/NH-23), so nothing downstream restores these notes.

## Location
- `arranger/voice_allocator.py:362,370` — `"volume": vel // 8`
- Consumed at `arranger/pipeline_integration.py:256-257` — `'volume': data['volume']`, `'control': (data.get('duty', 2) << 6) | 0x30 | data['volume']`

## Evidence
`voice_allocator.py:362` `"volume": vel // 8` (127//8 = 15 max, 7//8 = 0); `pipeline_integration.py:256-257` copies `data['volume']` straight into both the `volume` field and the control byte low nibble with no `max(1, …)`. Contrast the floored siblings at `pipeline_integration.py:276` (noise) and `voice_allocator.py:378` (triangle). The 2026-06-29 arranger audit checked this control byte (`(duty<<6)|0x30|volume`) and concluded "volume 0-15 stays in range" — correct as a *range* check, but it did not notice that the bottom of that range is reached for ordinary soft (ppp) notes and means silence.

## Impact
On `--arranger` arrangements, every pulse note softer than MIDI velocity 8 (the bottom ~6% of the velocity scale — ppp phrasing, fade-ins/outs, ghost notes) is emitted silently. The note is not dropped from the data (pitch/duty are written), so it passes validation and consumes a frame, but nothing is heard. Blast radius: pulse1 (melody/lead) and pulse2 (harmony) in arranger mode only; the legacy default pipeline and the triangle/noise arranger channels are unaffected. Secondary: because the arranger uses linear `vel // 8` while the legacy path uses a 1.5-power curve, the same MIDI plays at a different loudness through the two front-ends.

## Hardware ref
`docs/APU_PULSE_REFERENCE.md` §1 (4-bit volume 0-15 in the control byte, `EPPP.VVVV`; volume 0 with the constant-volume flag = silent channel).

## Suggested Fix
Floor the pulse volume at 1 for any active note, mirroring the legacy path — e.g. `"volume": max(1, vel // 8)` in `voice_allocator.py:362,370`, or apply `max(1, …)` in `pipeline_integration.py:257` where the noise path already does. For parity with the legacy loudness curve, consider reusing `max(1, int(15 * math.pow(vel / 127.0, 1.5)))` in both front-ends.

## Related
#165/NH-23 (dead exporter velocity rescue that would otherwise have masked this), #166/NH-24 (arranger/legacy front-ends diverge on note shaping), AUDIT_ARRANGER_2026-06-29.md §"Pulse control byte range".

## Completeness Checks
- [ ] **RANGE**: Volume nibble stays clamped 1-15 for active notes after the floor is applied
- [ ] **CHANNEL**: Fix is scoped to pulse1/pulse2 only; triangle (no volume) and noise floors are untouched
- [ ] **SIBLING**: All `vel // 8` sites in `voice_allocator.py` (pulse) reviewed for the same floor
- [ ] **TESTS**: A regression test pins that a velocity 1-7 pulse note yields volume >= 1 through the arranger
- [ ] **DOC**: If arranger loudness behavior contradicted a `docs/*.md`, the doc was corrected
