# NH-24: Envelope/effects/arpeggio plumbing is inert — no producer, every note plays the flat default envelope

**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-07-01.md

## Description
No pipeline stage (parser, track mapper, arranger, drum mapper) ever sets `envelope_type`,
`effects`, or `arp` on an event/frame, and nothing consumes the `arpeggio` boolean the core
emits. Consequences on the live path: `get_envelope_value` always evaluates the `default`
`(0,0,15,0)` envelope (flat), the tremolo/vibrato/duty-sequence effects are unreachable
(the only caller passing `effects` is the dead core, #38), and every generated
`macro_arp_*`/`macro_pitch_*` beyond the note<24 artifact (NH-16) is `[0, $FF]`. The
ADSR/effects engine is, in effect, test-only code; the doc-stated goal of macro-driven
instruments is unrealized.

## Location
`nes/emulator_core.py:80-81,87` (`envelope_type` read from events, never set upstream;
`effects=None` hardcoded; `arpeggio` flag emitted at `:92,106`);
`nes/envelope_processor.py:7-28` (`piano`/`pad`/`pluck`/`percussion` envelopes and the
vibrato/tremolo/duty-sequence `effect_definitions`); `exporter/exporter_ca65.py:1019,1035`
(`frame_data.get('arp', 0)` — no stage produces an `'arp'` key).

## Evidence
Repo-wide greps: `envelope_type` producers — none outside `nes/` defaults and tests; `'arp'` producers — none; `arpeggio` consumers — none.

## Impact
No wrong bytes today (the flat path is correct and clamped); the cost is dead-but-live-looking machinery and zero timbre variety. Becomes NH-21's trigger the day it is wired up.

## Related
#34, #38, NH-21, NH-19 (drum decay would be the first real macro user).

## Hardware ref
`docs/APU_ENVELOPE_REFERENCE.md` §4/§5 (constant-volume engine-driven model these definitions exist to feed).

## Suggested Fix
Either wire a producer (instrument/GM-based `envelope_type` selection; the arranger's GM table is the natural place) or prune the unused definitions and the `arpeggio` flag until they have one.

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
