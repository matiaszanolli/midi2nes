# TD-22: Superseded v0.4.0 planning/coverage docs are unlabeled as historical, assert stale current status  (#266)

**Severity:** LOW · **Domain:** tech-debt · **Dimension:** Stale Documentation & Comments · **Source:** AUDIT_TECH-DEBT_2026-07-05.md

## Description
Three docs present long-superseded figures as current status with no "archived"/"superseded" banner:
- `docs/IMMEDIATE_ACTIONS.md` — "Immediate Actions for v0.4.0", "All 186 tests passing", "177/177 tests passing", "Update all references … 0.3.5 → 0.4.0-dev", `__version__ = "0.4.0-dev"`
- `docs/COVERAGE_REPORT.md` — "Total Tests: 186 tests", "All 186 tests passing"
- `docs/TEST_COVERAGE_IMPROVEMENTS.md` — "bringing total test count from 568 to 582 tests"

The project is on `0.5.0-dev` with 900 tests. None of the three carry a superseded/archived/historical marker — exactly like TD-17's `WORK_PLAN_1.0.0.md`, they read as live guidance rather than a dated snapshot. TD-17 was documented in the 2026-07-03 report but was **not** filed as a GitHub issue, so this whole doc-family remains untracked.

## Evidence
```
grep -rniE "superseded|archived|historical" <the 3 docs>  → 0 hits
grep -niE "186 tests|0.4.0|177/177" docs/IMMEDIATE_ACTIONS.md
  → "Immediate Actions for v0.4.0", "All 186 tests passing", "177/177 tests passing",
    "0.3.5 → 0.4.0-dev", __version__ = "0.4.0-dev"
```
Re-verified 2026-07-05: all three files present, zero superseded/archived markers.

## Impact
LOW — documentation only. A contributor skimming `docs/` could treat v0.4.0 "immediate actions" (version bump, coverage targets) as still-open when they shipped long ago, or trust a 186-test coverage snapshot that is 4.8× under-count.

## Suggested Fix
Add an "Archived — superseded by `docs/ROADMAP.md`" banner to the top of each (and to `WORK_PLAN_1.0.0.md` per TD-17), or move them under a `docs/history/` subdirectory so they stop reading as current planning.

## Related
TD-17 (2026-07-03 report, `WORK_PLAN_1.0.0.md`, never filed as an issue); #224 (TD-13) and the TD-21 sibling (same 586/186/177 stale-count family).

## Completeness Checks
- [ ] **DOC**: Archived/superseded banner added to all three docs (and WORK_PLAN_1.0.0.md per TD-17)
- [ ] **SIBLING**: `docs/` swept for other v0.4.0-era snapshots presented as current
