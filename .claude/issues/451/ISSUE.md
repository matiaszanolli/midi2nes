# ARR-2026-08-21-4: Dropped tracks are never surfaced to the user — verbose output omits dropped_tracks/plan.notes, and print_analysis is dead code

**GitHub Issue:** #451
**Source Report:** docs/audits/AUDIT_ARRANGER_2026-08-21.md
**Severity:** MEDIUM · **Domain:** arranger
**Filed:** 2026-08-21

**Severity:** MEDIUM · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-08-21.md

## Description
`_assign_channels` faithfully records overflow in `plan.dropped_tracks` and `plan.notes` (including since #205's bookkeeping fix), but nothing on the live path ever shows them: `arrange_for_nes`'s `verbose` block prints only per-track role/polyphony lines, and `print_analysis` — the one function that prints `DROPPED:` and the notes — has no caller anywhere in the codebase (its only mention is the `arranger/__init__.py` module docstring). `allocate_frame` then skips unassigned tracks with a bare `continue`. So with >4 pitched voices, entire musical parts vanish from the ROM with zero indication even under `--verbose`, while the legacy front-end warns unconditionally about its (far smaller) same-frame note drops.

## Location
`arranger/pipeline_integration.py:272-283` (`arrange_for_nes` verbose block), `arranger/role_analyzer.py:464-499` (`print_analysis`), `arranger/__init__.py:21` (docstring-only reference)

## Evidence
`grep -rn print_analysis` → only the definition and the docstring. Simulated 4 melodic tracks: `dropped=[2, 3]`, `plan.notes` populated with "Dropped - no channels available" — and a full `arrange_for_nes(verbose=True)` run prints none of it.

## Impact
A musically-wrong voice drop (MEDIUM floor per `_audit-severity.md`) made worse by being undiscoverable: users comparing the ROM to the source MIDI have no clue which parts were cut or why. Blast radius: any `--arranger` run of a >4-voice MIDI (most piano/orchestral files).

## Related
#205/ARR-10 (made the bookkeeping correct; this is about surfacing it), #230/REG-12 (tests for the drop logic).

## Suggested Fix
Print `plan.notes` (or at minimum a one-line "N track(s) dropped: ..." summary) unconditionally from `arrange_for_nes` — mirroring the legacy path's warning style — and either call `print_analysis` under `verbose` or delete it.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
