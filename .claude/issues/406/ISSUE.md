# TD-11-FOLLOWUP: split run_full_pipeline into per-stage helpers

**Severity:** LOW · **Domain:** tech-debt · **Source:** split out of #136 (TD-11)
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/406

## Description
`main.py:run_full_pipeline` (~335 lines) threads parse -> map/arrange -> frames -> patterns
-> export -> DPCM-pack -> prepare -> compile -> validate inline. #136's `export_direct_frames`
half was extracted cleanly (byte-for-byte golden-diff verified); this half was deliberately
deferred because it's substantially more entangled:
- a single `try/except/finally` wraps nearly the whole function, gating backup/restore-on-
  failure (#26) via a `build_succeeded` flag -- a stage split must preserve this exact
  single-recovery-point semantics
- deliberate `del` calls trim peak memory between stages (#371/PERF-A-01) -- stage functions
  returning artifacts must not silently reintroduce that overhead
- control flow genuinely branches per stage (arranger vs legacy track mapping; patterns vs
  direct export; mapper resolution timing differs by path)
- `sys.exit(1)` is used inline for user-facing validation at several points

## Location
- `main.py:871-1206` (`run_full_pipeline`)

## Suggested Fix
Design stage helpers with an explicit, tested memory/error-handling contract before
extracting: a single mutable pipeline-context object stages prune as they go (replacing the
`del` calls with an equivalent, memory-profiling-verified effect); keep the outer
try/except/finally at the `run_full_pipeline` level; decide once whether stage helpers raise
on error rather than calling `sys.exit` inline.

## Completeness Checks
- [ ] TESTS: extracted stage helpers independently unit-testable
- [ ] CONTRACT: peak memory doesn't regress past #371/PERF-A-01's fix (profiling comparison)
- [ ] SIBLING: backup/restore-on-failure (#26) still triggers correctly per stage
- [ ] DOC: any docs describing the pipeline's stage sequence stays accurate
