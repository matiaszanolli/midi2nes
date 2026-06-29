# ARR-03: program is hardcoded to 0 — the entire GM instrument table and GM-driven role/channel/duty selection are dead

**Severity:** MEDIUM · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-06-29.md

## Description
In `analyze_midi_events`, every `NoteInfo` is built with a local `program = 0` that is never updated from MIDI program-change events (`parser_fast` does not parse them, and `VoiceRoleAnalyzer.set_track_program` is never called on the live path — only the unused `arranger/__init__.py` docstring shows it). `_determine_role` therefore always calls `get_instrument_mapping(0)` = Acoustic Grand Piano (MELODY / PULSE1 / DUTY_50 / priority 8) as the GM hint for every non-drum track. The `+3.0` GM-role score and the GM duty/channel base are identical for all tracks, so the 127 other GM entries never influence a live arrangement. Effective role selection reduces to the pitch/density/velocity heuristics only.

## Location
- `arranger/pipeline_integration.py:114`, `:133`, `:146`
- consumed at `arranger/role_analyzer.py:218-224`

## Evidence
```python
# pipeline_integration.py:114
program = 0          # never reassigned anywhere in the function
# role_analyzer.py:218
gm_mapping = get_instrument_mapping(analysis.program)   # analysis.program is always 0
```
`grep set_track_program` -> only `arranger/__init__.py` + definition; no live call.

## Impact
GM-specific timbre/role intent (e.g. bass programs 32–39 → TRIANGLE, pads → PULSE2, leads → DUTY) is silently ignored; arrangements are blander and occasionally mis-roled versus the documented design. Workaround exists (pitch heuristics still drive BASS→TRIANGLE etc.), so MEDIUM. All Dimension-4 GM-table findings are gated by this: the table is correct but unreachable.

## Related
ARR-02 (drum detection shares the missing-channel/program plumbing), #44.

## Suggested Fix
Parse `program_change` in `parser_fast` (carry per-track program) and call `analyzer.set_track_program(track_idx, program)` in `analyze_midi_events`.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
