# #97 — TEMPO-05: Dead optimization & loop-alignment code on the live path (optimize_tempo_changes, EnhancedLoopManager)

**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-06-29.md

## Description
Several timing-mutating routines are risky (e.g. `_smooth_tempo_transitions` adds intermediate tempos via **linear interpolation of µs/quarter**, which is not linear in elapsed time and would change segment duration; the FRAME_ALIGNED branch of `add_tempo_change` re-snaps `change.tick` via binary search and could in principle reorder events; `_minimize_tempo_changes` drops sub-5% changes). They are **not reachable on the default pipeline**: `optimize_tempo_changes` has **zero non-test call sites**, and the live front-end builds the tempo map with `optimization_strategy=None` (`tracker/parser_fast.py:29`), so the FRAME_ALIGNED re-snap and gradual-step paths in `add_tempo_change` are never taken. Likewise `EnhancedLoopManager.detect_loops`/`generate_jump_table` only run inside `parse_midi_to_frames_with_analysis` and `tracker/parser.py`, neither on the default MIDI->ROM path (`main.py:422` uses `parse_fast`, whose metadata is empty and whose jump tables are never consumed by the exporter/builder).

## Location
`tracker/tempo_map.py:507-611` (`_minimize_tempo_changes`, `_smooth_tempo_transitions`, `_align_to_frames`, `optimize_tempo_changes`); `add_tempo_change` FRAME_ALIGNED re-snap `:243-285`; `tracker/loop_manager.py:115-159` (`EnhancedLoopManager`).

## Evidence
`grep -rn "optimize_tempo_changes"` -> only the definition in `tempo_map.py` plus tests. `grep -rn "EnhancedLoopManager"` -> only `parser_fast.py` (inside the unused `_with_analysis`) and `parser.py` (legacy), plus tests. `main.py:422` calls `parse_fast`, which returns `"metadata": {}`.

## Impact
No active timing bug, but a maintenance/latent-trap hazard: if a future change wires `optimize_tempo_changes` or the analysis parser into the live path, the duration-changing `_smooth_tempo_transitions` and the reorder-capable FRAME_ALIGNED re-snap become real HIGH bugs. LOW today (dead code / hardening).

## Related
PERF-08 / PERF-01 in `docs/audits/AUDIT_PERFORMANCE_2026-06-29.md`; TEMPO-06.

## Suggested Fix
Either delete the unused optimization/loop-analysis paths or add tests pinning their timing-preservation invariants *before* any future wiring; document that `_smooth_tempo_transitions` linearly interpolates µs/quarter (not elapsed time) and must not be used to preserve note timing.

## Completeness Checks
- [ ] **TESTS**: If kept, tests pin timing-preservation invariants before any future wiring
- [ ] **DOC**: `_smooth_tempo_transitions` interpolation semantics documented
