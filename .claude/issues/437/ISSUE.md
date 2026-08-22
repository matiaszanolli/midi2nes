# PAT-2026-08-21-3: `_analyze_pattern_tempo` still passes event indices to `get_tempo_at_tick` as ticks — the un-fixed sibling of #345

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-08-21.md
**GitHub Issue:** #437

## Location
`tracker/pattern_detector.py:479-507` (`_analyze_pattern_tempo`), `:509-528`
(`_analyze_variation_tempos`)

## Description
`_analyze_pattern_tempo` calls `self.tempo_map.get_tempo_at_tick(tick) for tick in range(pos, pos + length)`
where `pos` is a pattern position — an index into the detection event sequence, not a MIDI tick.
On every pipeline path this is harmless by construction (all live call sites pass
`analyze_tempo=False` or a constant single-tempo map). But on the one path where `analyze_tempo`
defaults to True **and** the tempo map is real — `parse_midi_to_frames_with_analysis`
(`tracker/parser_fast.py:208`) — a multi-tempo song gets `base_tempo`/`tempo_info` computed from
"tempo at tick ≈ small event index", i.e. effectively always the song's initial tempo, and those
wrong values are registered into the real map via `add_pattern_tempo`. The events already carry a
stamped `tempo` field (`parser_fast.py:155`) — the same data source the #345 fix switched the loop
manager to.

## Evidence
`pattern_detector.py:481-486` (`get_tempo_at_tick(tick)` over `range(pos, pos + length)`);
contrast with the fixed pattern at `loop_manager.py:127-139` whose comment explicitly names the
unit mismatch.

## Impact
Wrong per-pattern tempo metadata (`tempo_map.pattern_tempos`) on the analysis path only; nothing
live consumes `pattern_tempos` (`optimize_pattern_tempos` is CLI-unreachable), hence LOW rather
than MEDIUM. It is, however, the last remaining instance of the #345 defect class.

## Related
#345/TEMPO-16 (fixed sibling), #376/PERF-A-06 (won't-fix context for the constant analysis maps),
PAT-2026-08-21-2 (sibling finding, same report, same caller).

## Suggested Fix
Mirror the #345 fix: read `events[i]['tempo']` (falling back to `get_tempo_at_tick` only when the
key is absent), or drop the tempo-analysis pass entirely now that every live call site disables it.
