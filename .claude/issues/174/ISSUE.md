# PL-01: Global `--arranger` before a subcommand parses cleanly and is silently ignored — step-by-step users get the legacy arrangement

**Severity:** CRITICAL · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-01.md

## Description
`--arranger`/`-a` is declared on the top-level parser, so argparse accepts it in front of
any subcommand. No subcommand consumes it: `run_map` unconditionally runs
`assign_tracks_to_nes_channels` (legacy mode), and there is no `arrange` subcommand at all —
the arranger front-end is reachable only through `run_full_pipeline`. The flag is swallowed
without any warning or error.

## Location
`main.py:694` (global declaration), `main.py:839-843` (subcommand dispatch parses the full
argv), `main.py:44-58` (`run_map` never reads `args.arranger`).

## Evidence
Live at HEAD: `python main.py --arranger map missing.json out.json` proceeds into
`run_map` (fails on the missing input file, not on the flag) — argparse accepted and
discarded `--arranger`. Contrast: `python main.py --no-pattern x.mid` correctly errors
`Unknown option` (the #8 fix), and `main.py map --arranger ...` (flag after subcommand)
correctly errors via argparse.

## Impact
A user running the documented step-by-step chain with `--arranger` gets legacy
single-voice mapping: polyphonic content is pitch-split/dropped instead of arpeggiated, so
the final ROM plays a different song than requested, with zero diagnostics. An ignored flag
that silently changes the song is CRITICAL (same rationale that classified F-03/#8).
Trigger requires putting the global flag on a subcommand invocation; impact when it fires
is a silently different song.

## Related
Closed #8 (F-03); PL-02 (same mechanism, `--debug`); the absence of an `arrange` subcommand is the underlying parity gap.

## Suggested Fix
Either reject song-affecting global flags when a subcommand is chosen (error: "--arranger
only applies to the default pipeline; there is no step-by-step equivalent"), or honor them
(add an `arrange` subcommand / an `--arranger` switch on `map`). At minimum, scope the help
text.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
