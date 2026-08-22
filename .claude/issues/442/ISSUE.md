# EXP-2026-08-21-7: Volume macro bytes bypass reserved-byte encoding — out-of-contract volume >= $FE silently becomes end-of-macro control byte

GitHub: https://github.com/matiaszanolli/midi2nes/issues/442

**Severity:** LOW · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-08-21.md

## Description
Every in-pipeline producer clamps volume to 0–15 (`velocity_to_volume`), but the step-by-step CLI (`main.py export frames.json …`) accepts a user-editable frames JSON, and the exporter applies no mask. Verified: a frame with `volume: 255` exports `macro_vol_1: .byte $FF, $FF` — the first data byte *is* the end-of-macro control byte, so `EVAL_MACRO` reads end-at-step-0 and plays the null default (15) instead; values 16–253 emit and are masked to `& $0F` by the engine at write time (silent modulo). No crash, but macro semantics silently change for malformed input the exporter elsewhere rejects loudly.

## Location
`exporter/exporter_ca65.py:1171` (`vol = frame_data.get('volume', 0)` — raw), `:1270`/`:1286` (`vol_seq` appended unencoded, unlike `pitch`/`arp` which route through `_encode_macro_offset`), `:1343` (`.byte` emission with no mask/clamp)

## Spec ref
`docs/AUDIO_BYTECODE_SPEC.md` §2.3 ("Volume Macros: absolute values (0-15)"; `$FF`/`$FE` reserved as control bytes)

## Impact
Requires out-of-contract input; wrong volume, never a broken ROM.

## Related
#77 (same reserved-byte hazard, fixed for pitch/arp only via `_encode_macro_offset`).

## Suggested Fix
Clamp/mask `vol` to 0–15 at collection time (matching the spec's stated domain), or raise like the DPCM range guard does.

## Completeness Checks
- [ ] **RANGE**: Volume values are clamped to the spec's 0-15 domain before emission, not just masked implicitly at engine write time
- [ ] **SIBLING**: Same pattern checked in related files (pitch/arp already route through `_encode_macro_offset` per #77 — apply the equivalent guard to volume)
- [ ] **TESTS**: A regression test pins this specific fix (out-of-range volume input does not silently become an end-of-macro/loop control byte)
