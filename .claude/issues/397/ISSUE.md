# TD-29: Stray zero-byte skip file checked into repo root

**Severity:** LOW · **Domain:** tech-debt · **Source:** docs/audits/AUDIT_TECH-DEBT_2026-08-05.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/397

## Description
A 0-byte file named `skip` is tracked at the repo root, added in commit `cadff6d`
("Add new skip file for pipeline audit tracking", 2026-07-06) — an accidental artifact
swept into an unrelated commit. No code, test, script, or doc references it.

## Location
`skip` (repo root, tracked, 0 bytes)

## Impact
None functionally; cosmetic/hygiene only.

## Suggested Fix
`git rm skip` in a small hygiene commit.
