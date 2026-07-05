**Severity:** MEDIUM · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-05.md

## Description
`NESEmulatorCore.process_all_tracks` injects a **non-channel** key `dpcm_sample_map` into the returned `frames` dict whenever a song references any DPCM drum samples (`nes/emulator_core.py:233`). Its value is `{str(dense_id): raw_id}` — a flat `str→int` map, not the `{frame_num: {note, volume, ...}}` shape every real channel has. The two production consumers explicitly skip it (`main.py:520`, `main.py:721`: `if channel_name == 'dpcm_sample_map': continue`).

`benchmark_pattern_detection` (`benchmarks/performance_suite.py:211`) — rewired by the #117 fix to finally use the real `ParallelPatternDetector` — has **no such guard**. On a `dpcm_sample_map` entry, `channel_frames` is `{str(dense_id): raw_id}`, so the inner loop binds `frame_data` to an `int` and calls `int.get('note', 0)` → `AttributeError: 'int' object has no attribute 'get'`.

## Evidence
- Emission is conditional on referenced drum ids: `nes/emulator_core.py:233` `processed['dpcm_sample_map'] = {str(dense_id): raw_id ...}`.
- Benchmark iteration at `benchmarks/performance_suite.py:222-227` lacks the `if channel_name == 'dpcm_sample_map': continue` line both production sites carry:
```python
for channel_name, channel_frames in frames_data.items():
    for frame_num, frame_data in channel_frames.items():
        ...
        'note': frame_data.get('note', 0),
        'volume': frame_data.get('volume', 0)
```
- The profile context manager re-raises; `run_full_pipeline` catches it and records a `stage="pipeline_error"` result — so **both the pattern-detection and export stages are lost** for that file; only parse/map/frames are timed.

## Impact
Dev-tooling only — no generated ROM or user output is affected. But the benchmark harness is the audit's regression backstop, and this makes its most important stage (pattern detection — the slowest, carrying the #114/#218 parallelism fixes) **un-measurable on the common percussion-containing MIDI**, silently degrading to a caught "Pipeline failed" line. A future regression in the parallel detector would go uncaught on exactly the inputs most likely to exercise it. MEDIUM (Dimension-6: a benchmark that measures the wrong code is worse than none), bounded to dev tooling.

## Suggested Fix
Add `if channel_name == 'dpcm_sample_map': continue` inside the channel loop in `benchmark_pattern_detection` (mirror `main.py:520`). Consider a shared `frames_to_events(frames)` helper so all three call sites cannot drift again.

## Related
Root cause shared with #200/D-14 (the `dpcm_sample_map` side table); production stages were guarded there, the benchmark was missed. Adjacent to PERF-11 (same method) and #117 (the fix that wired this stage to the real detector).

## Completeness Checks
- [ ] **CONTRACT**: The benchmark's `frames`→events extraction handles the `dpcm_sample_map` side table exactly as the production consumers do
- [ ] **SIBLING**: All three `frames`-iterating call sites (`main.py:520`, `main.py:721`, benchmark) share one guard / helper so they cannot drift again
- [ ] **FALLBACK**: The benchmark still exercises `ParallelPatternDetector` on drum MIDIs without raising
- [ ] **TESTS**: A regression test runs `benchmark_pattern_detection` on a drum-containing `frames` dict and asserts it completes
- [ ] **DOC**: No `docs/*.md` contradicted by the fix
