# TEMPO-15
**Filed as:** #344

**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-18.md

## Description
Both the `_collapse_same_frame_events` docstring ("ties keep the later event", `nes/emulator_core.py:22`) and the inline comment ("equal velocity keeps the later one", `:38`) claim that when two note-ons quantize to the same 60Hz frame and have equal velocity, the *later* event is retained. The code does the opposite. Events are stably sorted by frame only (`key=lambda e: e['frame']`), so among same-frame events original input order is preserved and the first-encountered is appended to `kept` first. The tie-break is `if vel > prev_vel: kept[-1] = e` — a *strict* greater-than, so on equal velocity the already-kept (earlier) event is retained and the later one is dropped.

## Evidence
```python
for e in note_ons:                       # note_ons sorted by frame (stable)
    vel = e.get('velocity', e.get('volume', 0))
    if kept and kept[-1]['frame'] == e['frame']:
        dropped += 1
        prev_vel = kept[-1].get('velocity', kept[-1].get('volume', 0))
        if vel > prev_vel:               # strict '>' → tie keeps kept[-1] (earlier)
            kept[-1] = e
    else:
        kept.append(e)
```

## Impact
Deterministic but incorrect per the documented contract. Blast radius is a single note on a monophonic channel when two equal-velocity note-ons collapse to one frame (legacy/default non-arranger path; the arranger arpeggiates polyphony and does not hit this). Musically the choice between two equal-velocity simultaneous notes is arbitrary, so audible impact is minimal — this is a doc/code contradiction, not timing drift.

## Related
Fix of #96/TEMPO-04 (the collapse itself, correct otherwise).

## Suggested Fix
Change `if vel > prev_vel` to `if vel >= prev_vel` so a tie keeps the later event as documented; or, if the earlier note is intentional, correct the docstring/comment instead. Add a test asserting the tie outcome.

## Completeness Checks
- [ ] **SIBLING**: the noise-channel same-frame collapse (if any) uses the same tie policy
- [ ] **TESTS**: a regression test pins the equal-velocity tie outcome
- [ ] **DOC**: docstring + inline comment match the code after the fix