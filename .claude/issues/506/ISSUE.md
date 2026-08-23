# PERF-B-04: Song-bank capacity overflow is detected only after all N songs are fully parsed, mapped, and held in memory

**Severity:** LOW · **Domain:** performance
**Source:** AUDIT_PERFORMANCE_2026-08-23.md (carried forward from AUDIT_PERFORMANCE_2026-08-07 / 2026-08-21, filed for the first time here)
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/506

## Description
A bank whose combined bytecode can never fit the MMC3 sequence-bank budget still pays
the entire N-song parse+map+frame-build cost — and holds all N frames dicts per
PERF-B-02 (#505) — before either the exporter's own overflow check or the post-build
`check_mapper_capacity` gate can fail. No cheap early estimate gates the loop. #467's
refactor changed how the failure path reports/cleans up but did not move the capacity
check earlier.

## Evidence
- The per-song parse loop (`main.py:1032-1059`) completes for every song before
  `export_song_bank_bytecode` (`main.py:1083`) or `check_mapper_capacity`
  (`main.py:1379`, inside `build_and_validate_rom`, called from `run_song_build` at
  `main.py:1093-1096`) run.
- Both checks execute inside the `tempfile.TemporaryDirectory` block opened at
  `main.py:1077`.

## Impact
Low — the failure is loud and correct, just late. An exact early estimate is
impossible pre-export (bytecode size depends on macro/instrument dedup).

## Related
PERF-B-02 (#505) — its interleaving fix resolves this for free. PERF-B-01 (#504).

## Suggested Fix
No dedicated fix; falls out of the PERF-B-02 interleaving refactor.
