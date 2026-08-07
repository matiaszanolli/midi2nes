# #381 — SAFE-2026-07-19-1: Full pipeline hard-requires dpcm_index.json in legacy mode; missing index aborts the whole run

**Severity:** LOW · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-07-19.md

## Description
In legacy mode the full pipeline calls `assign_tracks_to_nes_channels(midi_data["events"], 'dpcm_index.json')` with a hard-coded path and **no existence check**. When `dpcm_index.json` is absent, `EnhancedDrumMapper._load_sample_index` (`dpcm_sampler/enhanced_drum_mapper.py:231`) raises `FileNotFoundError`, which the pipeline's outer `except Exception` (`main.py:1167`) relays as `"[ERROR] Pipeline failed: DPCM index file not found: dpcm_index.json"` and `sys.exit(1)`.

This is an asymmetry: the DPCM-*packing* step (5.5) treats a missing index as **optional** (`"No dpcm_index.json found, skipping DPCM packing."`, `main.py:1078`), and the step-by-step `run_map` was given a dedicated clean-error guard in #256/D-18 (`main.py:125-128`). The full pipeline's mapping step never received that treatment, so a user who deletes the shipped `dpcm_index.json` gets the whole song aborted at step 2 rather than a drumless build or the same actionable guidance `run_map` prints.

## Location
`main.py:869-870` (`run_full_pipeline`, legacy mapping) vs `main.py:125-128` (`run_map` guard) and `main.py:1043-1078` (DPCM-packing step 5.5)

## Evidence
```python
# main.py:869-870  (run_full_pipeline, legacy mode — no guard)
dpcm_index_path = 'dpcm_index.json'
mapped = assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)
# vs main.py:125-128 (run_map — guarded)
if not Path(dpcm_index_path).exists():
    print(f"[ERROR] DPCM index not found: {dpcm_index_path} ...")
    sys.exit(1)
```

## Impact
Low. The repo ships `dpcm_index.json`, so this only bites if it is deleted/moved. The failure is a clean error line (not a raw traceback unless `-v`), but it is less actionable than `run_map`'s and inconsistent with the "DPCM is optional" posture the packing step takes.

## Related
#256/D-18 (run_map guard, closed); DP-DPCM-01 #340 (percussion role gaps — different).

## Suggested Fix
Add the same `Path('dpcm_index.json').exists()` guard before the legacy mapping call in `run_full_pipeline`, emitting `run_map`'s message; or, to match step 5.5's optional treatment, skip drum→DPCM mapping (map drums to noise) with a warning when the index is absent.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **FALLBACK**: Missing-index path degrades cleanly (drumless build or clean error), matching step 5.5's optional posture
- [ ] **SIBLING**: `run_map` guard and step 5.5 packing skip stay consistent with the new behavior
- [ ] **TESTS**: A regression test pins the missing-`dpcm_index.json` full-pipeline behavior
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# #382 — TEMPO-17: Frame-alignment verdict predicates disagree — asymmetric % FRAME_MS and single-segment time basis vs. is_frame_aligned

**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-19.md

## Description
#99 consolidated the frame-alignment *tolerance value* into one constant (`FRAME_ALIGNMENT_TOLERANCE_MS`) but left the three alignment predicates computing alignment three different ways, so they return contradictory verdicts for the same tick:

- `is_frame_aligned` (`tracker/tempo_map.py:263-268`) is **correct**: rounds to nearest frame (`np.round(time_ms / FRAME_MS)`) and checks the **symmetric** distance `abs(time_ms - frame_number*FRAME_MS) < TOL`. A time just *below* a frame boundary is aligned.
- `_validate_frame_boundaries` (`tracker/tempo_map.py:477-484`) checks `remainder = time % FRAME_MS; if remainder > TOL: raise`. This is **asymmetric**: `remainder` measures distance only *above* the lower boundary, range `[0, FRAME_MS)`. A time `< TOL` *below* the next boundary has `remainder ≈ FRAME_MS - ε` and is wrongly judged misaligned. Correct test: `remainder < TOL or remainder > FRAME_MS - TOL`.
- `_check_frame_alignment` (`tracker/tempo_map.py:863-876`) has the same asymmetric modulo test **and** a second defect: it derives time as `change.tick * (prev_tempo / ticks_per_beat)` — a **single-segment** basis that assumes the whole song from tick 0 ran at the tempo immediately preceding the change. For any song with an earlier tempo change this is not the true cumulative time (`calculate_time_ms(0, tick)`), so its verdict is doubly wrong under multi-tempo input.

## Evidence
With `EnhancedTempoMap(500000, ticks_per_beat=480)` and a tempo change to 300000 µs/qtr at tick 480, at **tick 506** the true cumulative time is 516.250 ms = 0.417 ms below frame boundary 31 (516.667 ms):

```
is_frame_aligned(506)            -> True   (correct: 0.417 ms from a boundary)
_validate_frame_boundaries(506)  -> RAISES (516.250 % 16.667 = 16.250 > 0.5)
_check_frame_alignment(506)      -> RAISES (single-seg basis = 316.250 ms, rem 16.250)
```

All three claim to answer "is tick 506 frame-aligned?"; one says yes, two say no.

## Impact
None on shipped ROMs today — all three predicates are dead on the live path (`_validate_frame_boundaries`/`_check_frame_alignment` are called only from `tests/test_tempo_map.py`; `is_frame_aligned` likewise). Blast radius is latent: these are the validity gate for the FRAME_ALIGNED optimization strategy (D7, currently unreachable). If that path is ever wired in, valid tempo changes landing just below a frame boundary would be spuriously rejected/mis-reported, and multi-tempo songs would be judged against a wrong time basis. It also makes the test suite assert self-contradictory behavior, masking the gap.

## Related
- #99 (TEMPO-07, tolerance consolidation — this is the unfinished half)
- D7/#97 (the dead FRAME_ALIGNED path these gate)

## Suggested Fix
Rewrite both `_validate_frame_boundaries` and `_check_frame_alignment` to reuse `is_frame_aligned`'s logic — symmetric nearest-boundary distance on `calculate_time_ms(0, tick)` (the true cumulative time) — rather than an asymmetric `% FRAME_MS` test, and drop the single-segment `tick * us_per_tick` computation in `_check_frame_alignment`. Update the pinning tests accordingly.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same asymmetric-modulo pattern checked in any other alignment predicate
- [ ] **TESTS**: A regression test pins that all three predicates agree for a tick just below a frame boundary under multi-tempo input
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# #383 — TEMPO-18: Base TempoMap.__init__ lacks the non-positive initial_tempo guard that EnhancedTempoMap has

**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-19.md

## Description
`EnhancedTempoMap.__init__` rejects `initial_tempo <= 0` with a `TempoValidationError` before its BPM division (#317/TEMPO-14). The base `TempoMap.__init__` (`tracker/tempo_map.py:88-114`) guards only `ticks_per_beat` (`:101`), not `initial_tempo`. A base `TempoMap(initial_tempo=0)` constructs silently; `get_tempo_bpm_at_tick` would then `ZeroDivisionError`, and `_build_tempo_index` computes `us_per_tick = 0`, collapsing **every** tick to time 0.0 → frame 0 with no error.

## Evidence
`TempoMap(initial_tempo=0, ticks_per_beat=480).get_frame_for_tick(1000)` returns `0` (all events pile onto frame 0) instead of raising. A grep for `TempoMap(` excluding `Enhanced` and tests returns **no** live construction site, so this is currently unreachable in production.

Confirmed in code: `EnhancedTempoMap.__init__` guard at `tracker/tempo_map.py:238-241`; base `TempoMap.__init__` guards only `ticks_per_beat < 1` at `:101` with no `initial_tempo` check.

## Impact
None today (no live caller constructs the base class with untrusted tempo — the live front-end `tracker/parser_fast.py` uses `EnhancedTempoMap`). It is a defense-in-depth gap: `TempoMap` is a public exported symbol (`__all__`, `tracker/tempo_map.py:880`) whose hardened subclass validates a case the base silently mis-handles.

## Related
- #317/TEMPO-14 (the sibling guard in `EnhancedTempoMap`)
- TD-26/#346 (`tracker/parser.py`, a base-`TempoMap`-adjacent dead path)

## Suggested Fix
Add the same `if initial_tempo <= 0: raise TempoValidationError` (or `ValueError` for the base class, which does not import the tempo exception) at the top of `TempoMap.__init__`, mirroring the existing `ticks_per_beat` guard.

## Completeness Checks
- [ ] **SIBLING**: Same guard present in `EnhancedTempoMap` and any other `TempoMap` subclass/constructor
- [ ] **TESTS**: A regression test pins that `TempoMap(initial_tempo=0)` raises
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# #384 — SAFE-2026-07-19-2: Whole 8-step pipeline wrapped in one broad except Exception

**Severity:** LOW · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-07-19.md

## Description
`run_full_pipeline` wraps all eight steps in a single `try: ... except Exception as e: print(f"[ERROR] Pipeline failed: {e}"); sys.exit(1)`. It cannot discriminate failure classes programmatically.

This is **not** a live "swallows a real bug" bug: every failure surface underneath raises a specific typed exception (`InvalidMIDIError`, `ConfigurationError`, `ToolchainError`, `CompilationError`, `ValidationError`) whose message this clause relays, so user-facing output stays meaningful, and `-v` prints the full traceback. The residual concern is defense-in-depth/testability: a caller/test cannot branch on exception type, and a genuinely unexpected defect is flattened to the same generic line as an expected user error.

## Location
`main.py:848-1173` (`try` at `:848`, `except Exception as e` at `:1167`)

## Evidence
```python
except Exception as e:                       # main.py:1167
    print(f"\n[ERROR] Pipeline failed: {str(e)}")
    if args.verbose: traceback.print_exc()
    sys.exit(1)
```

## Impact
None on generated ROMs. Testability/maintainability only.

## Related
SAFE-2026-07-19-1 (its `FileNotFoundError` is one of the errors flattened here); #125/SAFE-08 (the analogous narrowing already done in `config_manager`).

## Suggested Fix
Optionally catch `MIDI2NESError` (the typed base) distinctly from a final `except Exception` for truly unexpected defects, so the two are logged/tested differently. Low priority given the informative typed messages already flow through.

## Completeness Checks
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface
- [ ] **SIBLING**: Same narrowing pattern checked against the `config_manager` precedent (#125/SAFE-08)
- [ ] **TESTS**: A regression test pins that a typed error and an unexpected defect are handled/logged distinctly
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
