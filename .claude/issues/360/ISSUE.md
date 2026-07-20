# ARR-2026-07-19-2: analyze_midi_events declares three unused parameters

Issue: #360 · Source: AUDIT_ARRANGER_2026-07-19.md

**Severity:** LOW · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-07-19.md

## Description
`analyze_midi_events(midi_events, ticks_per_beat=480, tempo=500000, fps=60, sustain=True, sustain_gap=12)` never references `ticks_per_beat`, `tempo`, or `fps` in its body (verified via AST/grep: each appears only in the signature and docstring). Frame numbers come pre-computed from `parser_fast` (`event.get('frame', 0)`), and note density uses `VoiceRoleAnalyzer.tempo_fps` (hardcoded 60.0), not this `fps`. The parameters imply the arranger does tempo/tick-aware frame math here — it does not — which is misleading to a maintainer and invites a caller to pass a real tempo expecting it to matter.

## Location
- `arranger/pipeline_integration.py:86-99`

## Evidence
`grep -nE 'ticks_per_beat|tempo|fps'` over the function body (lines 106-200) returns no match — the three names occur only on signature/docstring lines. `arrange_for_nes` calls `analyze_midi_events` with all defaults.

## Impact
Documentation/maintainability only; no runtime effect.

## Related
- —

## Suggested Fix
Drop the three unused parameters (and their docstring lines), or wire `fps` through to `VoiceRoleAnalyzer.tempo_fps` if per-song FPS is intended.

## Completeness Checks
- [ ] **CONTRACT**: If the signature changes, every caller of `analyze_midi_events` (and `arrange_for_nes`) is updated in lockstep
- [ ] **SIBLING**: Other arranger entry points are checked for the same dead tempo/fps parameters
- [ ] **TESTS**: Existing arranger tests still pass after the signature change
- [ ] **DOC**: The docstring is updated to match the real (frame-prefilled) behavior
