# SAFE-09: SongBank.import_bank() and song subcommands have no JSON existence/parse/key guard

- **GitHub Issue**: https://github.com/matiaszanolli/midi2nes/issues/220
- **Severity**: MEDIUM
- **Domain**: safety
- **Source**: docs/audits/AUDIT_SAFETY_2026-07-03.md
- **Dimension**: 5 — JSON-Intermediate Guards (cross-refs Dimension 1: no surrounding try/except at the call sites either)
- **Location**: `nes/song_bank.py:177`-182 (`import_bank`); call sites `main.py:404` (`run_song_add`), `main.py:429` (`run_song_list`), `main.py:452` (`run_song_remove`); dispatch at `main.py:918` (`args.func(args)`, no wrapping try/except)
- **Status**: NEW (filed)

## Description
`import_bank(input_path)` does `data = json.loads(Path(input_path).read_text())` then immediately indexes `data['bank_info']['total_banks']`, `data['bank_info']['bank_size']`, and `data['songs']` with no existence check, no `JSONDecodeError` guard, and no key guard. All three `song` subcommands call it directly with no try/except, and `main()`'s subcommand dispatch (`args.func(args)` at `main.py:918`) has no outer handler either — unlike the rest of the CLI (`parse`/`map`/`frames`/`export`/`prepare`/`compile`/`config`/`benchmark` all end in a clean `[ERROR] ...` + `sys.exit(1)`). This is the identical bug class SAFE-01 (#120, closed) fixed via the `load_json_stage(path, required_keys, stage_name)` helper (`main.py:36`-65) for `run_map`/`run_frames`/`run_export`/`run_detect_patterns` — but `load_json_stage` was never applied here, and the `song` command family predates/was outside that fix's scope. `run_song_add` also calls `bank.add_song_from_midi(args.input, ...)` (`main.py:415`) unguarded, so even the now-typed `InvalidMIDIError` (from SAFE-02/#121) surfaces as a raw traceback on this path rather than the clean message the rest of the CLI gives it.

## Evidence
`nes/song_bank.py:179`: `data = json.loads(Path(input_path).read_text())`; `:180`-182: `self.total_banks = data['bank_info']['total_banks']`; `self.max_bank_size = data['bank_info']['bank_size']`; `self.songs = data['songs']`. `main.py:398`-420 (`run_song_add`), `:422`-443 (`run_song_list`), `:445`-459 (`run_song_remove`): none wrap the `import_bank`/`add_song_from_midi` calls in try/except.

## Impact
A user re-running `song add`/`song list`/`song remove` against a hand-edited, truncated, or wrong-format `--bank` JSON file gets a raw `FileNotFoundError`/`JSONDecodeError`/`KeyError` traceback instead of an actionable message. Scope is the JSON song-bank storage feature only (`CLAUDE.md`: "JSON song-bank storage/analysis only — not compiled to ROM"), so there is no ROM-corruption blast radius, matching SAFE-01's original MEDIUM classification for the same defect class.

## Related
Same root cause and fix pattern as SAFE-01/#120 (closed) — that fix's helper (`load_json_stage`) was scoped to the pipeline subcommands only and never extended to `song`. Not a duplicate of any open issue (checked #30/F-13, #33/F-14, #111/P-03 — all cover different song-bank gaps: routing, parser drift, and a dropped `--config` flag respectively).

## Suggested Fix
Reuse `load_json_stage(args.bank, ['bank_info', 'songs'], 'song-bank')` inside `import_bank`'s three call sites (or move the guard into `import_bank` itself), and wrap `run_song_add`/`run_song_list`/`run_song_remove` bodies in the same `try/except Exception as e: print(f"[ERROR] ..."); sys.exit(1)` pattern used by every other subcommand.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
