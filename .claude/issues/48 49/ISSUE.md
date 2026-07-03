# REG-08: Legacy multi-track channel-allocation heuristic untested (track_mapper.py 206-240)

**Severity:** LOW · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

## Description
`tests/test_track_mapper.py` covers the single-track pitch-split path (chord/arpeggio/grouping) but not the multi-track branch (the `average_pitch` ranking that assigns melody→pulse1, harmony→pulse2 with arpeggio fallback, bass→triangle, drums→noise/dpcm). This is the default (non-arranger) allocation for multi-track MIDI and is entirely unverified.

## Evidence
`tracker/track_mapper.py` ~206-240: the multi-track `else` branch ranks channels by `average_pitch`, pops highest→pulse1, next→pulse2 (`apply_arpeggio_fallback`), lowest→triangle, drum-named→noise. `tests/test_track_mapper.py` defines only chord/arpeggio/grouping tests — no multi-track allocation test.

## Impact
A regression in default multi-track voice assignment (e.g. bass routed to a pulse channel) ships green for the most common real-world MIDI shape.

## Suggested Fix
Add to `test_track_mapper.py`: feed `test_midi/multiple_tracks.mid` events; assert the highest-avg-pitch track lands on `pulse1`, the lowest on `triangle`, and a `drum`-named track on `noise`.

## Completeness Checks
- [ ] **CHANNEL**: Bass routed to triangle (not a pulse channel); drums to noise/dpcm
- [ ] **SIBLING**: Mirrors the arranger channel-allocation test (REG-04) for the legacy front-end
- [ ] **TESTS**: A test pins the multi-track allocation for `multiple_tracks.mid`
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# REG-09: cc65_wrapper.py (70%) — missing-tool detection and nonzero-exit/stderr handling untested

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

## Description
`_audit-common.md` flags the cc65 subprocess as a must-check path: return-code handling, missing-tool detection, and stderr surfacing. The uncovered lines are exactly the error branches (nonzero `ca65`/`ld65` exit, missing-binary handling). No test forces `ca65` to fail and asserts the wrapper raises/propagates rather than reporting success — the HIGH-rated "CC65 nonzero exit ignored" failure mode is unguarded by a unit test.

## Evidence
`compiler/cc65_wrapper.py` ~70% coverage; the uncovered lines (error-handling branches around 86-99, 229-241) cover nonzero `ca65`/`ld65` exit and missing-binary handling. No `tests/test_cc65_wrapper.py` exists; existing compiler tests use the happy path or a present toolchain.

## Impact
If a future change swallows a compile error, the suite stays green while emitting broken ROMs (HIGH per severity doc).

## Suggested Fix
Add `tests/test_cc65_wrapper.py`:
(a) monkeypatch `subprocess.run` to return rc=1 + stderr; assert the wrapper raises `CompilationError` with stderr surfaced.
(b) Point the wrapper at a nonexistent `ca65`; assert a clear missing-tool error, not a generic crash.

## Completeness Checks
- [ ] **CC65**: Nonzero `ca65`/`ld65` exit + stderr surface (asserted by a test)
- [ ] **SIBLING**: Both `ca65` and `ld65` invocations covered by the error-path test
- [ ] **TESTS**: `tests/test_cc65_wrapper.py` pins rc=1 propagation and missing-tool detection
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
