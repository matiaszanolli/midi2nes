# F-11: Backup restore does not fire on prepare-failure or top-level exception exits

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md
**Issue:** #26

## Description
When output_rom pre-exists, the pipeline copies it to .nes.backup (main.py:244-247). Restore-on-failure runs only after a compile failure (436-438) and validation ERROR (463-466). The prepare-failure exit (426-428) and top-level except → sys.exit(1) (488-494) do not restore. In those modes the final ROM is not yet overwritten (compile copies at the very end, compiler.py:146), so the original is intact today — a latent inconsistency, becomes data loss if a future change writes output_rom earlier.

## Evidence
Restore blocks exist only at 436 and 463; exits at 428 and 494 have none.

## Impact
Inconsistent backup/restore contract; fragile against reordering. Backup also never deleted on success (F-12).

## Related
F-02, F-12

## Suggested Fix
Move restore into a single finally/helper keyed on "overwrote the original and did not succeed", covering every exit path after backup creation.

**Location:** `main.py:426-428`, `main.py:488-494`; restore only at `main.py:436-438` and `463-466`
