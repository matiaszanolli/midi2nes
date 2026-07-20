# Issue #371 — PERF-A-01: Inter-stage frame/event data held as three full in-memory copies with no streaming

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-19.md

## Description
Every pipeline stage reads its entire input JSON into memory (`load_json_stage` → `json.loads(Path(...).read_text())`) and writes its entire output at once. Across parse → map → frames the same musical data exists as three successive full structures (parsed events → per-channel mapped events → the `{channel: {frame_num: {...}}}` frames dict, the largest of the three). No stage `del`s the prior structure while building the next, and there is no streaming, so the frames stage's peak holds both its input and output simultaneously.

## Evidence
`main.py:137-140` — `mapped = load_json_stage(args.input, [], 'map')` then `frames = emulator.process_all_tracks(mapped)` then `Path(args.output).write_text(json.dumps(frames, ...))`; `mapped` is never released before `frames` is fully materialized. `run_full_pipeline` chains the same stages in-process in a temp dir. (Contrast `run_detect_patterns`, which does `del frames` after extraction — the parse/map/frames chain does not.)

## Impact
Constant-factor (~3x) memory overhead on the single largest structure, bounded by event count. Output is correct; no OOM on a common MIDI file. Blast radius: memory footprint only, all channels/stages.

## Dimension
4 — Inter-stage memory

## Related
Dimension 4 in the skill; cross-references PERF-A-06 (the events↔frames round-trip that creates a further transient copy).

## Suggested Fix
When the step-by-step CLI is not in use, have `run_full_pipeline` `del` each stage's input dict once its successor is built; longer term, consider a streaming/generator hand-off for the frames stage. Low priority — measure before investing.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (`run_full_pipeline` in-process chain vs step-by-step CLI)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
