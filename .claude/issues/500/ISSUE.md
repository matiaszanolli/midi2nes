# DPCM-2026-08-23-1: audit-dpcm/SKILL.md still describes closed issue #76/D-13 as open

**Severity:** LOW · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-08-23.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/500

## Description
`DrumMapperConfig.from_file` (`dpcm_sampler/enhanced_drum_mapper.py:164-196`) was fixed in
`3b905fc` (2026-07-18, predating even the 2026-08-21 DPCM audit): it now catches `TypeError`
from an unexpected/renamed config key and re-raises a clear `ValueError` (`:195-196`,
`raise ValueError(f"Invalid configuration key in {config_path}: {e}")`), and
`result.validate()` runs before returning (`:189`). `tests/test_drum_mapper_config.py`
exercises the stray-key path and passes.

But `.claude/commands/audit-dpcm/SKILL.md`'s Dimension 6 still opens with:

> **Still open (#76/D-13)**: `from_file` (lines 163-191) does
> `DrumPatternConfig(**config_data.get('pattern_detection', {}))` ... an unexpected/renamed key
> in the JSON raises `TypeError` (not caught; only `FileNotFoundError` and
> `json.JSONDecodeError` are handled...)

— describing exactly the pre-fix behavior. Its own line citation (`163-191`) is also short by
5 lines (the `except TypeError` block runs through `:196`). `gh issue view 76` confirms
**CLOSED**.

The 2026-08-21 DPCM audit report already flagged this exact staleness inline ("`/audit-sync`
should retire the 'Still open (#76/D-13)' paragraph") but it was never filed as an issue or
corrected on disk.

## Evidence
`grep -n "Still open (#76" .claude/commands/audit-dpcm/SKILL.md` → line 287;
`sed -n '191,196p' dpcm_sampler/enhanced_drum_mapper.py` shows the
`except TypeError as e: raise ValueError(...)` clause the skill text says doesn't exist.

## Impact
None on ROM correctness — this is the audit skill's own prose, not shipped code. Misleads a
future `/audit-dpcm` run (human or agent) into re-reporting #76 as a live bug, or spending
investigation time "confirming" a fix that already landed over a month ago. Same defect class
as `ARR-2026-08-23-2` (`audit-arranger/SKILL.md`, fixed by #493) and `PAT-2026-08-23-3`
(`audit-patterns/SKILL.md`, fixed by #497) — both filed and fixed this week; `audit-dpcm/SKILL.md`
is the one sibling skill file in this family that never got the equivalent sync pass.

## Related
#76/D-13 (closed, `3b905fc`), #493 (arranger skill doc-rot, same class, fixed), #497 (patterns
skill doc-rot, same class, fixed), #463 (tech-debt skill doc-rot, same class, fixed).

## Suggested Fix
Replace the "Still open (#76/D-13)" paragraph in Dimension 6 with a "Fixed (#76/D-13, verify)"
framing matching the sibling skills' style — state that `from_file` now catches `TypeError`
and re-raises `ValueError` (citing the correct `:164-196` range), and ask a future run to
confirm the catch clause hasn't been removed and that `result.validate()` still runs before
the constructed config is returned.

## Completeness Checks
- [ ] **DOC**: `audit-dpcm/SKILL.md`'s Dimension 6 paragraph reflects the fixed state with
  correct line citations, re-verified against the live tree after the edit
