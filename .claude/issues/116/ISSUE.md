# PERF-05: All intermediate pipeline JSON is written with indent=2

**Severity:** MEDIUM · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-06-29.md

## Description
`run_parse`, `run_map`, `run_frames`, and the `detect-patterns` writer all serialize with `json.dumps(..., indent=2)`. The frames artifact — `{channel: {frame_num: {note, volume, ...}}}` with tens of thousands of inner dicts — is pretty-printed with a newline and leading spaces per element. Versus compact `separators=(',',':')`, `indent=2` typically inflates output size 2–3x and proportionally increases write time and the downstream `read_text()`/`json.loads` parse time of the next stage. These are machine-only intermediates a human rarely opens. (The benchmark/report writers at `main.py:959`, `benchmarks/performance_suite.py:438` are human-facing reports — `indent=2` is fine there.)

## Location
`main.py:43` (parse), `:52` (map), `:59` (frames), `:312` (detect-patterns output)

## Evidence
Four `write_text(json.dumps(..., indent=2))` call sites at `main.py:43,52,59,312`.

## Impact
Larger temp files + slower write/read on every multi-step run; the full pipeline writes these to a `TemporaryDirectory` so the cost is per-run, not persisted. Correct output, just bloated/slow → MEDIUM.

## Related
PERF-04 (the frames structure is the memory high-water mark too).

## Suggested Fix
Use `json.dumps(data, separators=(',',':'))` for the parse/map/frames/detect-patterns intermediates; keep `indent=2` only on the human-read report writers.

## Completeness Checks
- [ ] **CONTRACT**: Compact output is still valid JSON the next stage parses unchanged
- [ ] **SIBLING**: All four intermediate writers switched; human-facing report writers left at `indent=2`
- [ ] **TESTS**: Round-trip test that compact intermediates load identically
