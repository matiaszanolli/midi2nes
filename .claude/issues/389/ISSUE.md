# MAP-2026-08-05-2: Capacity pre-flight sizes only raw music.asm, never the debug overlay / DPCM-stub content appended afterward

**Severity:** MEDIUM · **Domain:** mappers · **Source:** docs/audits/AUDIT_MAPPERS_2026-08-05.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/389

## Description
Both `check_mapper_capacity` call sites (`main.py` and `NESProjectBuilder.prepare_project`)
size the exporter's raw `music.asm` before `prepare_project` appends the `--debug` overlay,
`fetch_sequence_byte`, or DPCM stub-table fallback content. Measured: `--debug` added 802
bytes to `CODE` on an NROM project — comfortably inside the static 2KB reserve in that case,
but the reserve is sized for the base playback engine, not this optional addition.

## Location
- `nes/project_builder.py:140` (check runs on source file)
- `nes/project_builder.py:142-148` (debug overlay appended after)
- `main.py:490-491`, `main.py:1069-1070` (CLI's earlier pre-flight, same ordering)

## Impact
Defense-in-depth gap for near-boundary songs; interacts with #388 (MAP-2026-08-05-1) in a
way that isn't guaranteed to fail cleanly at link time.

## Suggested Fix
Move `check_mapper_capacity` in `prepare_project` to run after debug/DPCM-stub content is
appended, sizing the actual final `music.asm`. Keep `main.py`'s early check for fast UX but
factor in `--debug` overhead when `args.debug` is set.
