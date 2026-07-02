# PL-02: Global `--debug` is silently inert on `prepare` — step-by-step cannot produce a debug ROM

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-01.md

## Description
`--debug`/`-d` ("Enable debug overlay in ROM") is a global option, so
`python main.py --debug prepare music.asm proj/` parses cleanly — and `run_prepare` never
reads `args.debug`, so the prepared project has no debug overlay. The same class of
declared-but-ignored flag was cleaned up for `--config` on `map`/`detect-patterns`/
`song add` (#13/#109) but the `--debug`->`prepare` route was missed. (Global `--verbose` is
similarly inert on most subcommands, but is cosmetic-only.)

## Location
`main.py:693` (global declaration), `main.py:216-242` (`run_prepare` constructs
`NESProjectBuilder(args.output, mapper=mapper)` with no `debug_mode`), vs `main.py:620,634`
(default path passes `debug_mode=debug_mode`).

## Evidence
Live at HEAD: `python main.py --debug prepare missing.asm proj` reaches `run_prepare`
(clean `[ERROR] Failed to prepare NES project`) — the flag was accepted;
`grep args.debug main.py` shows the only consumer is `run_full_pipeline` (line 620).

## Impact
Misleading interface: a developer debugging playback via the step-by-step chain silently
gets a normal ROM without the APU/frame overlay they asked for. No song change (the overlay
is diagnostic), hence MEDIUM, not CRITICAL.

## Related
PL-01 (same mechanism); closed #13/#109 (same defect class).

## Suggested Fix
Pass `debug_mode=getattr(args, 'debug', False)` in `run_prepare`'s builder construction (one line), or reject `--debug` on subcommands like PL-01.

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
