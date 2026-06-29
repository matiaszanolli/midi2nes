# TEMPO-02: Valid out-of-range and large-jump tempo changes silently dropped in fast parser

Issue: #94

**Severity:** HIGH · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-06-29.md

## Description
The fast parser overrides the tempo range to 40-250 BPM and swallows any `TempoValidationError` from `add_tempo_change` with a bare `continue` ("Skip invalid tempo changes silently for performance", `tracker/parser_fast.py:39-48`). Two classes of **legitimate** MIDI tempo are therefore discarded with no warning: (a) tempos below 40 BPM or above 250 BPM (largo / very fast pieces), and (b) any tempo change whose ratio to the previous tempo exceeds 3.0 (`tracker/tempo_map.py:344-353`, `max_tempo_change_ratio = 3.0`) — a normal section-boundary jump such as 200->60 BPM. When a change is dropped, the previous (or default 120 BPM) tempo persists, so **the song plays at the wrong tempo from that point on**, silently.

## Location
`tracker/parser_fast.py:39-48` (`except TempoValidationError: continue`); thresholds at `:18-23` (40-250 BPM) and ratio gate in `tracker/tempo_map.py:344-353` (default `TempoValidationConfig` `:27`).

## Evidence
With the parser's own config (40-250 BPM):
```
add_tempo_change(480, us(30 BPM))   -> TempoValidationError (REJECTED, then `continue`)
add_tempo_change(960, us(280 BPM))  -> TempoValidationError (REJECTED)
add_tempo_change(480, us(200)); add_tempo_change(960, us(60))
                                    -> "Tempo change ratio 3.33 exceeds maximum 3.0" (REJECTED)
```

## Impact
Wrong global/sectional tempo for any MIDI outside the narrow 40-250 BPM band or with a sharp tempo change — common in classical/film transcriptions. Silent wrong output -> HIGH. Distinct from the *note*-drop already filed in SAFE-07.

## Related
SAFE-07 (`docs/audits/AUDIT_SAFETY_2026-06-29.md:107`) covers the per-note `except Exception` at `:77` and explicitly scopes itself away from this tempo skip.

## Suggested Fix
Widen the fast-parser `TempoValidationConfig` to the full musically-valid range and relax/remove `max_tempo_change_ratio` for parsing (it is an authoring heuristic, not a hardware limit), or — at minimum — count and warn on dropped tempo changes instead of silently continuing.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same swallow pattern checked in `parser.py` tempo collection
- [ ] **TESTS**: A regression test pins out-of-range / large-jump tempo retention or a warning
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
