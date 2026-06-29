# M-4: CC65 --version probes use bare command name not resolved path; get_version subprocess unguarded

**Severity:** HIGH · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

check_toolchain probes invoke bare "ca65"/"ld65" rather than the shutil.which-resolved
self._ca65_path/self._ld65_path (TOCTOU/PATH divergence); get_version runs its subprocess
unguarded. assemble/link already surface stderr + nonzero exit (not a finding).

## Suggested Fix
Use resolved paths for the --version probes; wrap get_version subprocess in try/except.
