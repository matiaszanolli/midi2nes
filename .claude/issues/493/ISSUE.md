# ARR-2026-08-23-2: audit-arranger/SKILL.md has drifted from the code it audits

- **Issue**: #493

**Severity:** LOW · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-08-23.md

## Description
`.claude/commands/audit-arranger/SKILL.md` — the audit skill this very report was generated
from — has drifted from the code it audits. Three spots are stale relative to fixes that
landed on 2026-08-22, one day after the 2026-08-21 audit this skill file's prose was last
written against:

- `:200` — `**STILL OPEN — #88 (ARR-05)**: get_role_priority() ... is re-exported via
  arranger/__init__.py but has no call site`. Current code: the function has been **deleted
  entirely** (only a `# NOTE (#88/ARR-05)` comment remains at `arranger/gm_instruments.py:1326`),
  and it is no longer re-exported (`arranger/__init__.py`'s `__all__` has no such entry). #88
  is CLOSED on GitHub.
- `:223` — `**STILL OPEN — #91 (ARR-08)**: arp_speed is never validated ... Nothing ... guards
  against 0`. Current code: `VoiceAllocator.arp_speed` is a property with a clamping setter
  (`arranger/voice_allocator.py:104-115`, `max(1, int(value))`) covering every entry point.
  `tests/test_voice_allocator.py::TestArpSpeedValidation` exercises `arp_speed=0`/`-5` at the
  constructor, direct reassignment, and a full `arrange_for_nes(events, arp_speed=0)` run with
  no crash. #91 is CLOSED on GitHub.
- `:298` — `... arrange_for_nes writes triangle control = 0x81 with no duty bits`. Current
  code: commit `70ae14f` (#434, 2026-08-22) removed the triangle `control` key entirely —
  `arranger/pipeline_integration.py`'s triangle conversion now emits only
  `note`/`pitch`/`volume`, matching `nes/emulator_core.py`'s triangle contract (which never had
  a `control` key either). The `0x81` value described no longer exists anywhere in the live
  code.

## Evidence
```
$ grep -n "STILL OPEN\|0x81" .claude/commands/audit-arranger/SKILL.md
200:- **STILL OPEN — #88 (ARR-05)**: `get_role_priority()` (`arranger/gm_instruments.py:1303-1312`)
223:- **STILL OPEN — #91 (ARR-08)**: `arp_speed` is never validated. `arp_speed=0` makes
298:  (no real volume), and `arrange_for_nes` writes triangle `control = 0x81` with **no duty
```
`git show 70ae14f -- arranger/pipeline_integration.py` shows the `'control': 0x81,  # Triangle
linear counter` line deleted.

## Impact
None on ROM correctness. Misleads a future auditor (human or agent) into re-investigating
already-closed issues, or worse, "fixing" already-correct code, or reporting a real fix
(#434's triangle-key removal) as a regression because the checklist still expects the old key.

## Suggested Fix
Update Dimension 4/5's `#88`/`#91` framing from "STILL OPEN" to fixed, and Dimension 7's
triangle checklist item to say triangle frames carry no `control` key at all, citing #434.
`/audit-sync --issues 88,91,434` is built for exactly this.

## Completeness Checks
- [ ] **SIBLING**: Confirm no other "STILL OPEN"/stale-value claims remain elsewhere in the same skill file beyond these three spots (dimensions 1, 2, 3, 6, 8 were independently re-verified in AUDIT_ARRANGER_2026-08-23.md and found current)
- [ ] **DOC**: The skill file's prose is corrected to match current code (this issue's own subject)
