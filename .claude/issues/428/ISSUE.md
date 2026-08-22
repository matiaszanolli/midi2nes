# Issue #428: PIPE-2026-08-21-8: Expected capacity/mapper ValueErrors on the default path are reported as "Unexpected pipeline failure"

- **Finding**: PIPE-2026-08-21-8
- **Labels**: low, pipeline, bug
- **Filed**: 2026-08-21 (audit-publish, AUDIT_PIPELINE_2026-08-21.md)
- **URL**: https://github.com/matiaszanolli/midi2nes/issues/428

---

**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-08-21.md

## Description

#384/SAFE-2026-07-19-2 narrowed the pipeline's blanket except into `except MIDI2NESError` ("expected, actionable") vs `except Exception` ("unexpected defect") in `run_full_pipeline` (`main.py:1446-1454`). But the stage helpers signal expected user-facing failures (song too big for the mapper, invalid mapper for this music.asm) with plain `ValueError`, which is not a `MIDI2NESError` — so an ordinary oversized song prints "**Unexpected** pipeline failure: Music data does not fit …", contradicting the label's stated purpose, while the same condition on the step-by-step path prints a clean `[ERROR]` (`run_prepare`/`run_compile`/`run_export` catch `ValueError` explicitly).

Raisers: `check_mapper_capacity` via `build_and_validate_rom` (`main.py:1275`), `resolve_mapper`/`enforce_direct_export_dpcm_mapper` via `export_frames_and_resolve_mapper` (`main.py:1204-1256`) — both helpers' docstrings (`main.py:1194`/`1266`) declare `ValueError` as an expected failure mode.

## Evidence

`core/exceptions.py` — `ValueError` is not in the `MIDI2NESError` hierarchy; helper docstrings at `main.py:1194`/`1266` declare ValueError as the failure contract; `run_prepare:617-619` catches it explicitly; no `except ValueError` exists in `run_full_pipeline`'s handler chain.

## Impact

Message-labeling only — exit code, backup restore, and the actionable text are all still correct. Cosmetic residue of #384's typed/untyped split.

## Related

#384/SAFE-2026-07-19-2, #363/MAP-2026-07-19-3.

## Suggested Fix

Either add `except ValueError` alongside `except MIDI2NESError` in `run_full_pipeline`, or raise a typed `MIDI2NESError` subclass from `check_mapper_capacity`/`resolve_mapper`.

## Completeness Checks
- [ ] **SIBLING**: Same expected-vs-unexpected labeling checked on the other entry points (`run_prepare`, `run_compile`, `run_export`, `run_song_build`) so all paths classify `ValueError` consistently
- [ ] **TESTS**: A regression test pins this specific fix (oversized-song / invalid-mapper failure on the default path prints `[ERROR]` without the "Unexpected" label)
- [ ] **DOC**: If helper docstrings' declared failure contract changes (typed exceptions), the docstrings were updated in lockstep
