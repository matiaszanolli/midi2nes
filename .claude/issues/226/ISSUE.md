# TD-17: docs/WORK_PLAN_1.0.0.md "Current Status Assessment" is 18+ months stale and unlabeled as historical

**Severity:** LOW · **Domain:** tech-debt / documentation · **Source:** AUDIT_TECH-DEBT_2026-07-03.md

## Description
`docs/WORK_PLAN_1.0.0.md` opens with "## Current Status Assessment (December 2024)" and asserts "**Current Version**: v0.3.5" and "**Test Coverage**: 177/177 tests passing (100%)". The project is now on v0.5.0-dev with 789 tests.

The date qualifier is present, so a careful reader isn't outright misled, but the doc is titled `WORK_PLAN_1.0.0.md` (no "archived"/"superseded" marker) and sits alongside `docs/ROADMAP.md`, which is the authoritative forward-looking doc — `docs/WORK_PLAN_1.0.0.md` isn't cross-referenced from `ROADMAP.md` or `HISTORY.md` as superseded, so it reads as still-live planning rather than a historical snapshot.

**Location:** `docs/WORK_PLAN_1.0.0.md:3-8`

## Evidence
- `docs/WORK_PLAN_1.0.0.md:3-8` — "Current Status Assessment (December 2024)" / "Current Version: v0.3.5" / "Test Coverage: 177/177 tests passing (100%)"
- `python -m pytest --collect-only -q` → 789 tests (vs the doc's 177)
- `grep -n "WORK_PLAN" docs/ROADMAP.md HISTORY.md` → no hits (no cross-link marking it superseded)

## Impact
LOW — a contributor skimming `docs/` could treat 1.0.0 milestone items as still-open work without realizing most of "Phase 1" is long since done (patterns, arranger, DPCM, MMC3 all shipped per `HISTORY.md`/`MEMORY.md`).

## Suggested Fix
Add an "Archived — superseded by `docs/ROADMAP.md`" banner at the top, or fold any still-relevant open items into `ROADMAP.md` and delete the rest.

## Related
TD-13 (#224, same family: docs asserting stale test counts/status).

## Completeness Checks
- [ ] **DOC**: `docs/WORK_PLAN_1.0.0.md` marked archived/superseded, or merged into `docs/ROADMAP.md`
