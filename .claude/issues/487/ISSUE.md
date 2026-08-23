# PIPE-2026-08-22-3: Pre-subcommand --arranger rejection message denies that 'song build --arranger' exists

**Filed:** https://github.com/matiaszanolli/midi2nes/issues/487
**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-08-22.md

## Description
The pre-subcommand `--arranger` rejection message still claims "no step-by-step equivalent yet" even though `song build --arranger` exists and works.

## Location
`main.py` (the blanket rejection message); `p_song_build`'s own `--arranger` argument.

## Related
#174/PL-01 (the original fix that added this rejection, before `song build --arranger` existed).

## Suggested Fix
Point the user at `song build … --arranger` instead of denying it exists.
