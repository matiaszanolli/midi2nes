# F-12: .nes.backup is never cleaned up on success

**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md
**Issue:** #29

## Description
On a successful re-run over an existing ROM, .nes.backup is left on disk indefinitely (main.py:244-247 creates it; no deletion on the success path main.py:479-486). Not harmful but clutters and can mask which file is current.

## Evidence
No backup_path.unlink() anywhere after the success banner.

## Impact
Disk clutter; minor confusion. LOW.

## Related
F-11

## Suggested Fix
backup_path.unlink(missing_ok=True) after the success banner, or document retention as intentional.

**Location:** `main.py:244-247` (created); no deletion on success path (`main.py:479-486`)
