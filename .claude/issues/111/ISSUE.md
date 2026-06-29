# P-03: song add --config is declared but silently ignored

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-29.md

## Description
`p_song_add.add_argument('--config', help='Path to drum mapper configuration')` (`main.py:739`) is declared, but `run_song_add` (`main.py:316-338`) builds `metadata` from the other CLI args and calls `bank.add_song_from_midi(args.input, args.name, metadata)` without ever reading `args.config`. The drum-mapper config the help text promises is never loaded (`load_config` at `main.py:380` exists but is unused). Same misleading-interface class as #13 / P-01 (#109).

## Evidence
`run_song_add` body (`main.py:317-338`) has no `args.config` / `load_config(...)` reference; `load_config` is defined at `main.py:380` but never called anywhere (`grep "load_config(" main.py` shows only the definition).

## Impact
Misleading CLI on the song-bank path; the user's drum-mapper config is silently dropped. Song-bank is JSON-only and not compiled to ROM, so no ROM impact.

## Related
P-01 (#109), closed #13. Also touches the disjoint song-bank path (#30 closed).

## Suggested Fix
Drop `--config` from `song add`, or wire `load_config(args.config)` into `add_song_from_midi`.

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files (`detect-patterns --config` #109, `map --config`)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
