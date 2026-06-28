# F-10: export appends DPCM block in 'a' mode — re-running clobbers/doubles on a reused output

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md
**Issue:** #23

## Description
run_export writes CA65 tables (overwrite) then appends packed DPCM assembly with open(args.output, 'a') (main.py:118-119). Default path appends to a fresh temp music.asm (safe). Step-by-step path: args.output is a user file; re-running export onto a path that already contains a DPCM block produces duplicate dpcm_* symbols → assembler error.

## Evidence
main.py:96-119: export_tables_with_patterns writes the file, then open(args.output, 'a') appends. No check for an existing DPCM block.

## Impact
Step-by-step export re-runs onto a path already containing a DPCM section → duplicate-symbol assembly failures. Recoverable → MEDIUM.

## Suggested Fix
Have export_tables_with_patterns include the DPCM block itself (single write), or guard the append against an existing DPCM marker.

**Location:** `main.py:118-119` (run_export); default path `main.py:403`
