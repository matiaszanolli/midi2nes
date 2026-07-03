# TD-13: MEMORY.md is self-contradicting on the day it was authored

**Severity:** LOW · **Domain:** tech-debt / documentation · **Source:** AUDIT_TECH-DEBT_2026-07-03.md

## Description
`MEMORY.md` states "**586 tests** across 45 files" — the live count is **789 tests across 50 files** (`python -m pytest --collect-only -q` → "789 tests collected"; `ls tests/test_*.py | wc -l` → 50). Separately, `MEMORY.md`'s "Gotchas worth remembering" section says `__version__.py` "lags reality... still reads `0.4.0-dev`" — but `midi2nes/__version__.py` currently reads `"0.5.0-dev"`.

Both `MEMORY.md` and `midi2nes/__version__.py` were last touched in the **same commit** (`a359e03 feat: Bump version to 0.5.0-dev for upcoming release`, 2026-06-28), so this file misstated its own commit's content from the moment it was created — it was never accurate, not merely drifted since.

**Location:** `MEMORY.md:10-11` (test count), `MEMORY.md:28-29` (`__version__.py` gotcha) — line numbers have since drifted slightly (now 11, 34-35) but content unchanged.

## Evidence
- `git log -1 --format=%cd --date=short -- MEMORY.md midi2nes/__version__.py` → both `2026-06-28`; `git show --stat a359e03` includes both files.
- `python -m pytest --collect-only -q` → `789 tests collected`.
- `MEMORY.md:11` — `- **586 tests** across 45 files, all passing`
- `midi2nes/__version__.py:3` — `__version__ = "0.5.0-dev"`

## Impact
`MEMORY.md` is explicitly positioned (in its own header) as the durable, authoritative doc pairing with `CLAUDE.md` — a wrong "current status" section undermines exactly the trust it's meant to provide. No runtime/ROM impact.

## Suggested Fix
Update the test count (789 tests / 50 files) and delete/rewrite the `__version__.py` gotcha to reflect current state (it already reads `0.5.0-dev`). Consider a lightweight discipline/check that `MEMORY.md`'s "Current status" block is updated in the same commit as version bumps.

## Related
TD-17 (#226, same family: docs asserting stale test counts/status).

## Completeness Checks
- [ ] **DOC**: `MEMORY.md`'s test count and `__version__.py` gotcha updated to match current code
