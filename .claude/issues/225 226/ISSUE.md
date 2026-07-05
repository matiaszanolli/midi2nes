# #225 — TD-14: docs/DEBUG_ROM_VISUAL_GUIDE.md still assumes MMC1 ROM size — sibling drift to fixed #35 (M-10)

**Severity:** LOW · **Domain:** tech-debt / documentation · **Source:** `docs/audits/AUDIT_TECH-DEBT_2026-07-03.md`

## Description
Under "Scenario 4: ROM Doesn't Boot", `docs/DEBUG_ROM_VISUAL_GUIDE.md` tells the reader to check "ROM file size (should be ~131KB for MMC1)". `python main.py --debug song.mid` (the exact command this guide's own opening line references) now builds against the **MMC3** default (512KB PRG in 8KB banks per `CLAUDE.md`), not MMC1/131KB.

Existing #35 (M-10) fixed this same MMC1-vs-MMC3 drift in `CLAUDE.md` and confirmed README was already consistent, but did not touch this file — it is a sibling instance the original fix's grep didn't cover, not a regression of #35.

## Evidence
- `docs/DEBUG_ROM_VISUAL_GUIDE.md:121` — `- 🔍 **Check:** ROM file size (should be ~131KB for MMC1)`
- `CLAUDE.md:197` — `PRG-ROM: MMC3 default is 512KB in 8KB banks (MMC1 is 128KB in 16KB banks; NROM is 32KB)`
- `grep -rn "MMC1" docs/*.md` — the rest of the hits are historical/comparative mentions in `MAPPER_MMC3_REFERENCE.md`, `2A03_CPU_REFERENCE.md`, `APU_DMC_REFERENCE.md`, which correctly discuss MMC1 as an alternative, not the default; this is the only live instance presented as current debugging guidance.

## Impact
A developer following this guide today to debug a non-booting debug ROM would look for the wrong file size and could misdiagnose a correctly-sized MMC3 ROM as broken (or vice versa). LOW — troubleshooting guidance only, no code/ROM impact.

## Suggested Fix
Update to "~512KB for the default MMC3 build (128KB/131KB if built with `--mapper mmc1`)" or point at the mapper-specific capacity instead of a bare number.

## Related
Existing #35 (M-10, closed/fixed but scoped to `CLAUDE.md`/README only).

## Completeness Checks
- [ ] **DOC**: `docs/DEBUG_ROM_VISUAL_GUIDE.md:121` updated to reflect MMC3-default ROM size (with MMC1 noted as the non-default alternative)

---

# #226 — TD-17: docs/WORK_PLAN_1.0.0.md 'Current Status Assessment' is 18+ months stale and unlabeled as historical

**Severity:** LOW · **Domain:** tech-debt / documentation · **Source:** `docs/audits/AUDIT_TECH-DEBT_2026-07-03.md`

## Description
`docs/WORK_PLAN_1.0.0.md` opens with "## Current Status Assessment (December 2024)" and asserts "**Current Version**: v0.3.5" and "**Test Coverage**: 177/177 tests passing (100%)". The project is now on v0.5.0-dev with 789 tests.

The date qualifier is present, so a careful reader isn't outright misled, but the doc is titled `WORK_PLAN_1.0.0.md` (no "archived"/"superseded" marker) and sits alongside `docs/ROADMAP.md`, which is the authoritative forward-looking doc — `docs/WORK_PLAN_1.0.0.md` isn't cross-referenced from `ROADMAP.md` or `HISTORY.md` as superseded, so it reads as still-live planning rather than a historical snapshot.

## Evidence
- `docs/WORK_PLAN_1.0.0.md:3-8` — "Current Status Assessment (December 2024)" / "Current Version: v0.3.5" / "Test Coverage: 177/177 tests passing (100%)"
- `python -m pytest --collect-only -q` → 789 tests (vs the doc's 177)
- `grep -n "WORK_PLAN" docs/ROADMAP.md HISTORY.md` → no hits (no cross-link marking it superseded)

## Impact
LOW — a contributor skimming `docs/` could treat 1.0.0 milestone items as still-open work without realizing most of "Phase 1" is long since done (patterns, arranger, DPCM, MMC3 all shipped per `HISTORY.md`/`MEMORY.md`).

## Suggested Fix
Add an "Archived — superseded by `docs/ROADMAP.md`" banner at the top, or fold any still-relevant open items into `ROADMAP.md` and delete the rest.

## Related
TD-13 (same family: docs asserting stale test counts/status).

## Completeness Checks
- [ ] **DOC**: `docs/WORK_PLAN_1.0.0.md` marked archived/superseded, or merged into `docs/ROADMAP.md`
