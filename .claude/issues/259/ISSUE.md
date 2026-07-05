**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-05.md

## Description
The default parser `parse_midi_to_frames` was fixed under #94 (TEMPO-02) to never drop a tempo change silently — it counts rejections in `dropped_tempo_changes` and prints a warning after the tempo pass. Its sibling `parse_midi_to_frames_with_analysis` rebuilds its own tempo map and still uses the pre-#94 idiom: a bare `except TempoValidationError: continue` with no counter and no user-facing warning. A tempo change rejected here (e.g. a tempo outside the widened 1–2000 BPM band, or a `tempo <= 0` now caught by #209) vanishes with no trace, and the affected section is analyzed at the preceding tempo.

## Location
`tracker/parser_fast.py:199-202` (`except TempoValidationError: continue`, no counter, no warning), contrasted with the fixed default path at `tracker/parser_fast.py:80-94` (`dropped_tempo_changes += 1` + post-pass `print(...)`).

## Evidence
```python
# parser_fast.py:198-202  (with_analysis path)
if msg.type == 'set_tempo':
    try:
        tempo_map.add_tempo_change(current_tick, msg.tempo, TempoChangeType.IMMEDIATE)
    except TempoValidationError:
        continue        # <- silent; no count, no warning
```
vs. the fixed default path:
```python
# parser_fast.py:85-94
except TempoValidationError:
    dropped_tempo_changes += 1
    continue
...
if dropped_tempo_changes:
    print(f"Warning: dropped {dropped_tempo_changes} out-of-range tempo change(s); ...")
```

## Impact
Off the live ROM path (`--with-analysis` only; the metadata it produces — patterns/loops/jump_table — is not consumed by the default `parse → map → frames → export → compile` pipeline), so no ROM ships wrong music because of it. It is a consistency/observability gap: analysis run interactively can silently mis-tempo a section.

## Related
#94 (TEMPO-02, closed — introduced the count-and-warn this path missed); TEMPO-13 (same function, same cluster).

## Suggested Fix
Mirror the default path: count rejected changes in a local and `print` a single warning after the loop (or refactor the two tempo-collection passes into one shared helper so they cannot drift again).

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (the default `parse_midi_to_frames` pass is the correct reference; TEMPO-13 is the sibling in the same function)
- [ ] **TESTS**: A regression test pins this specific fix (a rejected tempo change on the analysis path surfaces a warning)
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
