# ARR-10: Second drum track silently dropped — not logged to dropped_tracks, no warning

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/205
**Source finding:** NEW-1 in `docs/audits/AUDIT_ARRANGER_2026-07-03.md`
**Filed:** 2026-07-03

**Severity:** MEDIUM · **Domain:** arranger

## Description
`_assign_channels` (`arranger/role_analyzer.py:317-326`) special-cases drum tracks: the first
drum track claims `noise` and (if free) `dpcm`, then unconditionally `continue`s. A second track
flagged `is_drum_track` finds `noise_assigned` and `dpcm_assigned` already `True`, so neither
`if` body runs, `assigned` stays `False`, and the loop hits `continue` *before* reaching the
"Track couldn't be assigned" block (`:386-391`) that would otherwise append it to
`plan.dropped_tracks` and log a `plan.notes` entry. Every other unassignable track (pulse/
triangle overflow) is recorded there; a second drum track is not — it vanishes with zero trace,
even under `verbose`.

## Evidence
```python
from arranger.pipeline_integration import analyze_midi_events
events = {
    'drums_a': [{'frame':0,'note':36,'volume':100,'type':'note_on','channel':9},
                {'frame':5,'note':36,'volume':0,'type':'note_off','channel':9}],
    'drums_b': [{'frame':0,'note':38,'volume':100,'type':'note_on','channel':9},
                {'frame':5,'note':38,'volume':0,'type':'note_off','channel':9}],
}
plan, _, _ = analyze_midi_events(events)
# plan.noise_tracks == [0]; plan.dpcm_tracks == [0]
# plan.dropped_tracks == []   <-- track 1 (drums_b) is nowhere: not assigned, not dropped
# plan.notes == []            <-- no diagnostic at all
```
Code path: `arranger/role_analyzer.py:318-326`
```python
if track.is_drum_track:
    if not noise_assigned:
        ...
    if not dpcm_assigned:
        ...
    continue   # <-- reached even when both flags were already True
```

## Impact
Any MIDI authored with drums split across multiple channel-9 (or name-heuristic) tracks — e.g.
separate kick/snare/hats stems — loses every stem after the first, with no `dropped_tracks`
entry, no `plan.notes` line, and no `verbose` print to explain why.

## Related
#85 (channel-9 detection), #88 (`get_role_priority` — not itself a fix for this).

## Suggested Fix
Only `continue` inside the drum branch when at least one of noise/dpcm was actually claimed;
otherwise fall through to the standard "couldn't be assigned" bookkeeping.

## Dedup check
Searched open issues in `/tmp/audit/issues_arranger.json` — no match found. Filed as NEW.
