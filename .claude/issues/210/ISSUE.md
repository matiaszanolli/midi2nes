# TEMPO-10: Duplicate tempo changes at the same tick resolve by numeric tempo value, not file/insertion order — violates MIDI "last event wins" semantics

Issue: #210

**Severity:** HIGH · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-03.md

## Description
`tempo_changes` is a list of `(tick, tempo)` tuples. `sort()` on tuples orders first by `tick`, then — for equal ticks — by `tempo` **ascending**, not by insertion order. `get_tempo_at_tick`/`_cumulative_ms` then pick the *last* entry at or before the query tick via `bisect_right`, which for a tied tick means "the numerically largest tempo value wins," not "the tempo change that was added last." Standard MIDI semantics require that when two `set_tempo` events land on the same tick, the one that appears **later in processing order** is authoritative. This code silently substitutes "larger tempo value" for "later in order," which are unrelated.

## Location
`tracker/tempo_map.py:118-119` (`TempoMap.add_tempo_change`: `self.tempo_changes.append((tick, tempo)); self.tempo_changes.sort()`) combined with `:162-168`/`:154-160` (`get_tempo_at_tick`/`_cumulative_ms`'s `bisect.bisect_right(ticks, tick) - 1`, which selects the **last** entry in the sorted list for ties).

## Evidence
Built and parsed a real `.mid` file with tempo events in file order `500000 -> 600000 -> 250000`, the second and third at the identical tick (480, delta-time 0 between them). Per standard MIDI order, 250000 (240 BPM) should be the active tempo from tick 480 onward, but 600000 (100 BPM) won instead. Confirmed directly against current code:
```python
tm.add_tempo_change(1000, 600000)   # added first
tm.add_tempo_change(1000, 400000)   # added second, should win
tm.tempo_changes -> [(0, 500000), (1000, 400000), (1000, 600000)]
tm.get_tempo_at_tick(1000) -> 600000   # wrong: the first-added value wins because it sorts last
```

## Impact
Wrong tempo for the remainder of the song (or section) from the tied tick onward, silently — same impact class as the already-fixed #94 (dropped tempo changes), just via a different root cause (tie-break order instead of validation rejection). Reachable on the live default pipeline (`parse_midi_to_frames` calls `EnhancedTempoMap.add_tempo_change` per `set_tempo` event in file order, with `optimization_strategy=None` so no re-snapping intervenes).

## Related
Distinct root cause from #94 (TEMPO-02, validation-rejection based) and from #208/#209 (TEMPO-08/09, zero/negative tempo value based) — this is a tie-break/ordering bug, not a validation gap.

## Suggested Fix
Track insertion order explicitly (e.g. append `(tick, tempo, seq)` with a monotonic `seq` counter, or use a stable structure keyed by tick that always overwrites on re-insertion) so that for duplicate ticks the most-recently-added tempo is authoritative, matching MIDI event order rather than numeric tempo value.

## Completeness Checks
- [ ] **CONTRACT**: `EnhancedTempoMap.enhanced_changes.sort(key=lambda x: x.tick)` (stable sort, keyed on tick only) still reflects the same fixed tie-break semantics after the change
- [ ] **SIBLING**: `_build_tempo_index` (`tracker/tempo_map.py:123-142`) consumes `self.tempo_changes` directly — verify it doesn't need its own tie-break fix once insertion order is tracked
- [ ] **TESTS**: A regression test pins duplicate-tick insertion order winning over numeric tempo value
