**Severity:** MEDIUM · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-06-29.md

## Description
Each step-by-step subcommand does `json.loads(Path(args.input).read_text())` (and `--patterns`) with no `Path.exists()` check and no `try/except` around the parse, then immediately indexes a hard-coded key. A missing file raises `FileNotFoundError`; a truncated/garbage file raises `json.JSONDecodeError`; a file from the wrong stage raises `KeyError` (e.g. feeding a parse JSON to `export`, which expects frames, or a frames JSON to `--patterns`, which expects `patterns`/`references`). All surface as raw tracebacks on the documented "Step-by-step pipeline for debugging" path.

**Scope note (dedup):** The `run_map` / `midi_data["events"]` facet is already tracked as #110. This finding covers the remaining, not-yet-filed surface: `run_frames` (`main.py:56`), `run_export` (`main.py:215`, `:220`, and key access `pattern_data['patterns']`/`['references']` at `main.py:237`–`238`), `run_detect_patterns` (`main.py:274`), plus the missing-file/`JSONDecodeError` guards on all of them.

## Location
- `main.py:56` (`run_frames`)
- `main.py:215`, `:220` (`run_export`)
- `main.py:274` (`run_detect_patterns`)
- key access `main.py:237`–`238` (`pattern_data['patterns']`/`['references']`)

## Evidence
`run_export`: `pattern_data = json.loads(Path(args.patterns).read_text())` then `patterns = pattern_data['patterns']; references = pattern_data['references']`. No existence check, no `JSONDecodeError` guard, no key guard on any path.

## Impact
Poor UX on the documented debugging path (CLAUDE.md "Step-by-step pipeline for debugging"); an inter-stage contract break crashes with `KeyError` rather than "this isn't a patterns file". No corrupted ROM (these stages do not write `args.output` before the parse), so this is robustness/UX, not correctness. Blast radius: the remaining subcommand entry points (`run_frames`, `run_export`, `run_detect_patterns`).

## Related
- #110 (P-02) covers the `run_map`/`events` facet — same theme, complementary scope.
- Prior pipeline audit F-05/F-08 touch these subcommands' flags/params but not input robustness.

## Suggested Fix
A small `load_json_stage(path, required_keys, stage_name)` helper that checks existence, catches `JSONDecodeError`, and validates the expected top-level keys, raising a typed error (`ParsingError`/`ValidationError`) with a clear message. Reuse across all four subcommands (and fold in #110's `run_map` guard).

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same guard applied across `run_map` (#110), `run_frames`, `run_export`, `run_detect_patterns`
- [ ] **TESTS**: A regression test pins this specific fix (missing / malformed / wrong-stage JSON → clean error)
