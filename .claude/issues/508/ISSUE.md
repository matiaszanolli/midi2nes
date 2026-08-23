# EXP-2026-08-23-1: AUDIO_BYTECODE_SPEC.md still documents $87 CMD_DMC_LEVEL as working after the engine handler was deleted

**Severity:** LOW · **Domain:** exporters
**Source:** AUDIT_EXPORTERS_2026-08-23.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/508

## Description
`#83/EXP-07` (2026-07-04) corrected the spec to document `$87 CMD_DMC_LEVEL` as real
and working, true at the time. `#309` (2026-07-17) then deleted that exact
`@cmd_dmc_level` handler as dead code, but the spec doc `#83` had just fixed was never
re-touched. The doc now claims a "real, working" opcode the shipped engine no longer
decodes — hitting `$87` today would silently halt that channel's sequence via
`@unknown_command`. Spotted once before as a cross-audit item (NH-HW-2026-08-21-7),
never filed until now.

## Evidence
- `docs/AUDIO_BYTECODE_SPEC.md:106,113` still describe `$87` as working.
- `nes/audio_engine.asm:376-434` dispatcher has no `$87` handler; falls to
  `@unknown_command`.
- `git log` confirms `f78c618` (#309, 2026-07-17) postdates `b7c99c8` (#83,
  2026-07-04).

## Impact
Doc-rot only — no exporter emits `$87` (confirmed #72's removal holds).

## Related
#83, #72, #309 (closed, none covers this gap); #509, #510, #511, #512 (same audit).

## Suggested Fix
Restore the handler, or mark the `$87` spec row removed/not-implemented like `$FE`'s
loop byte was in #163/NH-21.
