# F-02: ROM-validation gate only blocks on ERROR, which is unreachable for a bad-vector ROM — unbootable ROMs ship as SUCCESS

**Severity:** CRITICAL · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md
**Issue:** #6

## Description
run_full_pipeline exits non-zero only when overall_health == "ERROR" (main.py:459). In rom_diagnostics.py, "ERROR" is set only by _create_error_result (line 204), which fires solely when ROM bytes cannot be read/parsed. A linked ROM with invalid reset vectors records "Invalid reset vectors" as one issue (135-136), landing GOOD/FAIR/POOR but never ERROR. "No APU initialization code found" (139-140) likewise only adds an issue.

## Evidence
Only ERROR call site is _create_error_result (rom_diagnostics.py:204). main.py only warns on FAIR/POOR then prints SUCCESS banner.

## Impact
The sole hardware-safety gate cannot catch the failure class it claims to. A ROM with bad $FFFA-$FFFF vectors or missing APU init ships as SUCCESS and crashes the CPU on real hardware. Blast radius: every generated ROM whose linker mislays vectors.

## Related
F-11

## Suggested Fix
Treat not reset_vectors_valid and apu_count == 0 as hard-fail (force overall_health = "ERROR" or sys.exit(1) after diagnosis). Reserve "ERROR" for unreadable files but add a separate fatal check for vector/APU validity.

**Location:** `main.py:453,459-468`; `debug/rom_diagnostics.py:135-162,184-207`
