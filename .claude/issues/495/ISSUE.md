# PAT-2026-08-23-2: PatternDetector._optimize_patterns remains dead code with an unshared, diverging scoring formula

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-08-23.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/495

## Description
`_optimize_patterns` (`tracker/pattern_detector.py:382-419`) is never called by
`detect_patterns` (which does its own inline non-overlap selection at `:324-346`) or by any
other live code path. It re-implements the same overlap-selection idea with a private, unshared
score — `(exact_count + variation_count * 0.8) * pattern_length` (`:392-396`) — that ignores
both the module-level `score_pattern` (#103) and the #365/PAT-A exact-occurrence gate
(`len(candidate['positions']) >= MIN_PATTERN_OCCURRENCES`) that the live selection loop now
enforces.

`grep -rn "_optimize_patterns"` matches only its own definition and one direct unit test
(`tests/test_patterns.py:267`) that calls it in isolation — no integration path reaches it.

## Evidence
`tracker/pattern_detector.py:382` (definition) vs. `:187-346` (`detect_patterns`'s actual,
self-contained two-pass selection — the code path a fresh round-trip harness in this audit
exercised and confirmed lossless).

## Impact
None at runtime — confirmed no caller exists. Pure drift/maintainability risk: a future
contributor could reasonably assume this method participates in the real pipeline and patch it
instead of the inline loop in `detect_patterns`, silently missing both fixes it lacks (#103,
#365).

## Related
#103 (`score_pattern` unification), #365 (PAT-A, exact-occurrence gate), #131/TD-03 (prior
copy-paste drift noted in this same file). Carried forward unfixed from
`docs/audits/AUDIT_PATTERNS_2026-08-21.md` (PAT-2026-08-21-6) and
`docs/audits/AUDIT_PATTERNS_2026-08-07.md` (PAT-2026-08-07-B) — never previously filed.

## Suggested Fix
Delete `_optimize_patterns` and its isolated test, or — if it's meant as a documented alternate
strategy — rewrite it on top of `score_pattern` and the same `MIN_PATTERN_OCCURRENCES` gate, with
a docstring stating who is expected to call it.

## Completeness Checks
- [ ] **SIBLING**: Confirm no other dead/duplicate selection helper exists elsewhere in this
  file or `pattern_detector_parallel.py`
- [ ] **TESTS**: If deleted, `tests/test_patterns.py:267`'s isolated test is removed too
- [ ] **DOC**: No docstring/audit-skill prose is left implying this method participates in live
  selection

## Note
This issue was accidentally filed twice during `/audit-publish` (a shell-quoting error caused
the results to be misattributed) — the duplicate, #496, was closed as a duplicate of this one.
