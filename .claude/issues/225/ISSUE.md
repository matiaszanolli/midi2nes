# TD-14: docs/DEBUG_ROM_VISUAL_GUIDE.md still assumes MMC1 ROM size — sibling drift to fixed #35 (M-10)

**Severity:** LOW · **Domain:** tech-debt / documentation · **Source:** AUDIT_TECH-DEBT_2026-07-03.md

## Description
Under "Scenario 4: ROM Doesn't Boot", `docs/DEBUG_ROM_VISUAL_GUIDE.md` tells the reader to check "ROM file size (should be ~131KB for MMC1)". `python main.py --debug song.mid` (the exact command this guide's own opening line references) now builds against the **MMC3** default (512KB PRG in 8KB banks per `CLAUDE.md`), not MMC1/131KB.

Existing #35 (M-10) fixed this same MMC1-vs-MMC3 drift in `CLAUDE.md` and confirmed README was already consistent, but did not touch this file — it is a sibling instance the original fix's grep didn't cover, not a regression of #35.

**Location:** `docs/DEBUG_ROM_VISUAL_GUIDE.md:121`

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
