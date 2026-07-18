# TEMPO-16
**Filed as:** #345

**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-18.md

## Description
`LoopManager.detect_loops` builds each loop's `start`/`end` from pattern `positions` + `length`. Those `positions` are **indices into the note-on event list** (returned by `_find_pattern_matches` in `tracker/pattern_detector.py`, which enumerates the event sequence), not MIDI ticks and not frame numbers. `EnhancedLoopManager.detect_loops` then calls `self.tempo_map.get_tempo_at_tick(loop_info['start'])` and `...['end'])` (`tracker/loop_manager.py:127-128`) — feeding an event index into a function whose parameter is a MIDI tick. For a single-tempo song this is harmless (the lookup returns the one constant tempo regardless of the argument), but for a multi-tempo song the tempo stamped onto a loop boundary is read at the wrong position and can be wrong.

## Evidence
```python
# loop_manager.py:127-128 — loop_info['start']/['end'] are event indices…
start_tempo = self.tempo_map.get_tempo_at_tick(loop_info['start'])   # …used as a tick
end_tempo   = self.tempo_map.get_tempo_at_tick(loop_info['end'])
```
`pattern_detector._find_pattern_matches` returns sequence indices, not ticks/frames.

## Impact
Latent only. `EnhancedLoopManager` is **not on the default pipeline**; it is reached solely via `parse_midi_to_frames_with_analysis` (opt-in) and the older `tracker/parser.py`. The resulting `loop_points`/`jump_table` `tempo_state` is analysis metadata that no exporter consumes to build a ROM today, so no shipped ROM loops at the wrong tempo. It becomes a real bug the moment loop metadata is wired into ROM generation.

## Related
Sibling to the D3 default-PPQ "analysis-only tempo map" inertness (#98).

## Suggested Fix
Convert `positions` to ticks/frames before the tempo lookup (the note-on events carry a `frame` field; map index → `events[idx]['frame']` and query by the time domain the tempo map actually indexes), or document the boundary values as event indices and drop the tempo-at-tick lookup until loops feed real timing.

## Completeness Checks
- [ ] **CONTRACT**: the unit of loop boundary values (event index vs tick vs frame) is documented and consistent across producer and consumer
- [ ] **TESTS**: a multi-tempo test asserts the loop-boundary tempo is read at the correct position