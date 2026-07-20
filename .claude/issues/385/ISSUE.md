# SAFE-2026-07-19-3: export subcommand writes music.asm directly to the user path (not atomic)

**Issue:** #385
**Severity:** LOW · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-07-19.md
**Labels:** low, safety, enhancement
**Dimension:** D8 (Partial-Output-on-Failure)
**Status as filed:** NEW

## Description
`export_tables_with_patterns` / `export_direct_frames` write the final ASM via `with open(output_path, 'w') as f: f.write('\n'.join(lines))`. Content is assembled into `lines` before the file is opened (single buffered write; only disk-full/IO error could truncate), but the write is not atomic (no temp-file + os.replace). On such a rare failure the step-by-step export subcommand would leave a truncated .asm at the user path. Full pipeline unaffected (writes into auto-cleaned TemporaryDirectory).

## Location
`exporter/exporter_ca65.py:1326-1327` and `:897`; reached from run_export (`main.py:616`)

## Suggested Fix
Write to a sibling temp file and os.replace() into place so a failed write never overwrites a prior good music.asm.

## Related
#123 (loud DPCM-append warnings — same subcommand's separate partial-output risk).
