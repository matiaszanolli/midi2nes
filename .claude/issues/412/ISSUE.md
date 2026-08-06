# TD-30: Duplicate defaultdict import in nes/emulator_core.py

**Severity:** LOW · **Domain:** tech-debt · **Source:** docs/audits/AUDIT_TECH_DEBT_2026-08-06.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/412

## Description
`from collections import defaultdict` is imported twice (lines 1 and 3, with an unrelated
import sandwiched between). Caught via a `pyflakes` sweep. No functional effect.

## Location
- `nes/emulator_core.py:1-3`

## Impact
None functionally; readability nit only.

## Suggested Fix
Delete the redundant import on line 3.
