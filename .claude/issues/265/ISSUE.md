# TD-21: README.md and HISTORY.md still claim "586 tests" — live count is 900  (#265)

**Severity:** LOW · **Domain:** tech-debt · **Dimension:** Stale Documentation & Comments · **Source:** AUDIT_TECH-DEBT_2026-07-05.md

## Description
The public-facing `README.md` asserts "586 tests" in three separate places — the Tests shields.io badge (`Tests-586%20passing`), the intro tagline ("586 tests passing"), and the testing-section comment ("Run all tests (586 tests across 45 files)"). Live count is **900 tests across 50 files**. `HISTORY.md`'s milestone row for `v0.5.0-dev` also reads "586 (45 files)".

TD-13/#224 already flagged this exact stale number, but its scope and fix were `MEMORY.md`-only — the more visible README was left untouched. All three README lines trace to commit `a359e03` (2026-06-28), stale since the 0.5.0-dev bump and drifting further (586 → 900).

## Evidence
```
grep -n 586 README.md   → 11 (badge), 14 (tagline), 298 (testing section)
grep -n 586 HISTORY.md  → 99 (v0.5.0-dev | 586 (45 files))
ls tests/test_*.py | wc -l  → 50
```
Re-verified 2026-07-05: README lines 11/14/298 and HISTORY.md:99 still read 586; 50 test files present.

## Impact
LOW — no runtime/ROM effect, but the README is the first doc a new contributor or user reads; a test-count badge that is ~35% low undermines the "stabilization" message it sits next to.

## Suggested Fix
Update the README badge/tagline/testing comment to the current count (or drop the hard number from the badge and link to CI), and update or de-hard-code the `HISTORY.md` v0.5.0-dev row. Consider folding the count into a doc-lint that flags when git-tracked test-count strings diverge from `pytest --collect-only`.

## Related
#224 (TD-13, `MEMORY.md` — same 586 number, different file, still open).

## Completeness Checks
- [ ] **DOC**: README badge/tagline/testing comment + HISTORY.md row corrected to live count
- [ ] **SIBLING**: Other docs with the same stale 586/45-files string checked
- [ ] **TESTS**: (optional) doc-lint pins test-count strings to `pytest --collect-only`
