# Batch fix: #352, #343, #344, #345

Fetched via `gh issue view 352 343 344 345 --repo matiaszanolli/midi2nes --json title,body,labels,state`.
Immutable snapshot as filed — GitHub is authoritative for current state.

Note: #352 was fixed separately on branch `fix/issue-352` (see that branch's
own copy of this snapshot) after investigation revealed it was substantially
bigger/riskier than originally filed — a real, production-facing O(n^2)
pattern-detection slowdown, not test-only dead code. This branch covers only
#343/#344/#345.

## #352 — REG-21: PatternDetector (bare, test-only dead code) hangs at n≈1000 events — O(n²×length-range) per-start rescan
Labels: bug, medium, regression
Source: discovered while verifying fix-issue batch #332/#333/#338/#339 (2026-07-18)

`tracker/pattern_detector.py`'s bare `PatternDetector` class implements an
O(n² × pattern-length-range) per-start rescan; at n≈1000 (its own sampling
cap) with default max_pattern_length=32 this becomes computationally
infeasible. Confirmed pre-existing on master. `grep` shows it's imported
only by tests/test_patterns.py — never production code. Suggested fix
(option 1, recommended): delete the class, migrate its ~4 test call sites to
`EnhancedPatternDetector`.

**Correction discovered during implementation:** `EnhancedPatternDetector`
inherits from `PatternDetector` and calls its slow `detect_patterns` via
`super()` — this is NOT dead code, it's the real production sequential
detector. Fixed instead by recalibrating `DETECTOR_MAX_EVENTS` (1000 → 300,
empirically measured to bound worst-case latency to ~2.5s). See branch
`fix/issue-352`.

## #343 — DP-DPCM-04: Dense-remap note=min(255,dense_id+1) silently aliases the 256th+ distinct drum with no warning
Labels: bug, low, dpcm
Source: AUDIT_DPCM_2026-07-18.md

`nes/emulator_core.py:220` encodes `note = min(255, dense_id + 1)`. At N≥256
distinct DPCM samples, dense_id=255 collides with dense_id=254 (both encode
to note=255) — every dense_id≥255 becomes unreachable, silently playing
sample #254 instead. Suggested fix: emit a warning when
`len(referenced_ids) > 255`, mirroring the same-frame-collapse drop counters.

## #344 — TEMPO-15: _collapse_same_frame_events keeps the earlier note on a velocity tie, contradicting its docstring
Labels: bug, low, tempo
Source: AUDIT_TEMPO_2026-07-18.md

Docstring/comment say ties keep the *later* event; code's strict `>`
comparison keeps the earlier one. Suggested fix: change `if vel > prev_vel`
to `if vel >= prev_vel` so ties keep the later event as documented (or fix
the docs instead, if the earlier-note behavior is intentional).

## #345 — TEMPO-16: EnhancedLoopManager passes pattern event-indices to get_tempo_at_tick as ticks (unit mismatch)
Labels: bug, low, tempo
Source: AUDIT_TEMPO_2026-07-18.md

`LoopManager.detect_loops` builds loop start/end from pattern *event-index*
positions (not ticks/frames), then `EnhancedLoopManager.detect_loops` feeds
those directly into `get_tempo_at_tick`, which expects a tick. Harmless for
single-tempo songs; wrong tempo stamped on loop boundaries for multi-tempo
songs. Latent only — not on the default pipeline (only reached via the
opt-in `--with-analysis` path). Suggested fix: convert positions to
ticks/frames (via `events[idx]['frame']`) before the tempo lookup.
