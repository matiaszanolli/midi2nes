# F-02: ROM-validation gate only blocks on ERROR, unreachable for bad-vector ROM

**Severity:** CRITICAL · **Domain:** pipeline

run_full_pipeline exits non-zero only when overall_health=="ERROR", which fires solely for
unreadable files. A linked ROM with invalid reset vectors / no APU init lands FAIR/POOR and
ships as ✅ SUCCESS, crashing the CPU on hardware.

## Suggested Fix
Treat not reset_vectors_valid and apu_count==0 as hard-fail (sys.exit(1)) regardless of tier.
