# TEMPO-19: tracker/parser.py builds its EnhancedTempoMap without passing ticks_per_beat, hardcoding PPQ 480

**Severity:** LOW · **Domain:** tempo · **Source:** docs/audits/AUDIT_TEMPO_2026-08-05.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/396

## Description
`tracker/parser.py` (dead/test-only, TD-26/#346) builds `EnhancedTempoMap` without
`ticks_per_beat`, defaulting to 480 regardless of the actual MIDI file's division —
unlike the fixed live-path sibling `tracker/parser_fast.py`. Since this map IS fed real
tick data and used for `get_frame_for_tick`, this is a genuine cumulative-drift bug,
distinct from #346's general "module is unreachable" framing.

## Location
`tracker/parser.py:30-34`

## Impact
None today (module unreachable in production). Would drift frame indices by
`480 / actual_ticks_per_beat` if ever reconnected.

## Suggested Fix
Delete `tracker/parser.py` per #346, or pass `ticks_per_beat=mid.ticks_per_beat` to
match `parser_fast.py`.
