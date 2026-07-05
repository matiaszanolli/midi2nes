# ARR-10: Second drum track silently dropped — not logged to dropped_tracks, no warning

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/205
**Severity:** MEDIUM
**Domain:** arranger
**Source:** docs/audits/AUDIT_ARRANGER_2026-07-03.md (NEW-1)
**Labels:** medium, arranger, bug

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
plan, _, _ = analyze_midi_events(events)  # two drum-tagged tracks
# plan.noise_tracks == [0]; plan.dpcm_tracks == [0]
# plan.dropped_tracks == []   <-- track 1 is nowhere: not assigned, not dropped
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
Any MIDI authored with drums split across multiple channel-9 (or name-heuristic) tracks loses
every stem after the first, with no `dropped_tracks` entry, no `plan.notes` line, and no
`verbose` print to explain why. MEDIUM.

## Suggested Fix
Only `continue` inside the drum branch when at least one of noise/dpcm was actually claimed;
otherwise fall through to the standard "couldn't be assigned" bookkeeping so
`plan.dropped_tracks`/`plan.notes` records it like any other overflow.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# ARR-11: Drum-name heuristic overrides definitive non-drum channel info

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/206
**Severity:** MEDIUM
**Domain:** arranger
**Source:** docs/audits/AUDIT_ARRANGER_2026-07-03.md (NEW-2)
**Labels:** medium, arranger, bug

## Description
`analyze_midi_events` (`arranger/pipeline_integration.py:110-116`) computes `track_channel` from
the first event that carries channel info, then marks a track as drums if
`track_channel == 9 **or** 'drum' in name.lower() or name in ('9', 9)`. The channel check and the
name heuristic are combined with `or`, not applied as "channel info wins when present, name is
only a fallback." So when a track *does* carry definitive, non-percussion channel info (e.g.
channel 0) but its name happens to contain "drum", the name heuristic still fires and the track
is entirely rerouted through `_analyze_drum_track` — discarding its actual pitch content and
playing it as noise/DPCM hits instead of melody.

## Evidence
Two-note melodic track on channel 0 named "Drum Fill Reference":
```python
plan, _, _ = analyze_midi_events(events)
# plan.tracks[0].is_drum_track == True, role == PERCUSSION
# plan.noise_tracks == [0]; plan.pulse1_tracks == []; plan.triangle_tracks == []
```

## Impact
A pitched track is silently reduced to unpitched noise/DPCM hits whenever its name happens to
match the heuristic, even though the MIDI's own channel metadata says it isn't percussion. MEDIUM.

## Suggested Fix
When `track_channel` is known (not `None`), let it be authoritative
(`is_drum = track_channel == 9`); only fall back to the name heuristic when no event carries
channel info (`track_channel is None`).

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# ARR-12: _analyze_drum_track writes a dead analysis.notes attribute with a stale description

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/207
**Severity:** LOW
**Domain:** arranger
**Source:** docs/audits/AUDIT_ARRANGER_2026-07-03.md (NEW-3)
**Labels:** low, arranger, bug

## Description
`_analyze_drum_track` (`arranger/role_analyzer.py:186-193`) sets
`analysis.notes = "Uses DPCM for kicks/snares"` when `n.pitch in [35, 36]` (kicks) or
`n.pitch in [38, 40]` (snares) is present. `TrackAnalysis` declares no `notes` field (only 19
fields, none named `notes`), so this creates an ad-hoc instance attribute that nothing reads
(only reader of any `.notes` in `arranger/` is `plan.notes`, a distinct field on
`ArrangementPlan`). The string is also stale: `GM_DRUM_MAP[40]` ("Electric Snare") routes to
`NESChannel.NOISE`, not DPCM (fixed under #87), so grouping 40 with DPCM-routed 35/36/38 is wrong
even if the attribute were read.

## Evidence
`dataclasses.fields(TrackAnalysis)` has no `notes` entry; only reader of any `.notes` attribute
in `arranger/` is `plan.notes` on `ArrangementPlan`.

## Impact
None at runtime (dead write). Misleading to a maintainer. LOW.

## Suggested Fix
Remove the dead assignment, or (if per-track diagnostics are wanted) add a proper
`notes: str = ""` field to `TrackAnalysis` and have `print_analysis` surface it, using
`get_drum_mapping` per-note rather than a hardcoded list to decide the message.

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
