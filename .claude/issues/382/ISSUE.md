# TEMPO-17: Frame-alignment verdict predicates disagree — asymmetric % FRAME_MS and single-segment time basis vs. is_frame_aligned

Issue: #382 · https://github.com/matiaszanolli/midi2nes/issues/382
Labels: low, tempo, bug

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
