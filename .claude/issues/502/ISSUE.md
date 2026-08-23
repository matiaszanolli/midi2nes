# PIPE-2026-08-23-1: audit-pipeline/SKILL.md's main.py line citations are broadly stale

**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-08-23.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/502

## Description
`main.py` has grown to 2006 lines (from ~770 at the time `audit-pipeline/SKILL.md`'s prose
was last written) across recent commits (`934b597` #485-488, `a63be2d` the new
`--visualizer` feature, `a9a7a21` #465-467, `d1bafed` #495/#497/#498), and — more
disruptively for line citations than raw growth — its function *order* changed: the
song-bank subcommands (`run_song_add`/`run_song_list`/`run_song_remove`/`run_song_build`,
~290 lines) and the `#406` stage helpers (`detect_patterns_or_direct_export`/
`export_frames_and_resolve_mapper`/`build_and_validate_rom`, ~250 lines) now sit **before**
`run_full_pipeline` in the file, which itself moved from roughly line 770 to **line 1402**.

Every citation the skill makes into `run_full_pipeline`'s body (its `try`/`except`/`finally`
block, the `LARGE_FILE_THRESHOLD` check, the fallback detector construction, etc. —
Dimensions 1, 4, 6, 7 all cite specific lines in the 770-1230 range) is now off by 400-630
lines.

Representative confirmed-stale examples:
- `load_json_stage` cited at `main.py:64-93` → actually defined at `:88` (def line alone).
- `run_full_pipeline`'s outer `try`/`except`/`finally` cited at `main.py:773`/`:1216`/
  `:1224-1229` → the function itself now starts at `:1402`; its `except`/`finally` are much
  later in the file.
- `LARGE_FILE_THRESHOLD` and the fallback block cited at `main.py:818`/`:827-853`/`:844` are
  inside `detect_patterns_or_direct_export` (now `main.py:1149-1273`), a function this same
  skill's own Dimension 1 already documents as having been extracted out of
  `run_full_pipeline` by #406 — but Dimensions 6/7's own citations weren't updated to match
  when that extraction happened, and have drifted further since.

Same doc-rot class already caught and fixed this week in the sibling `audit-arranger` (#493),
`audit-patterns` (#497), and `audit-dpcm` (#500) skill files — `audit-pipeline` is the
remaining sibling that hasn't had an equivalent sync pass, and has the largest drift of the
four.

## Evidence
`wc -l main.py` → 2006; `grep -n "^def run_\|^def detect_patterns_or_direct_export\|^def
export_frames_and_resolve_mapper\|^def build_and_validate_rom" main.py` shows
`run_full_pipeline` at `:1402`, well after the stage helpers (`:1149`, `:1274`, `:1355`) and
the song-bank subcommands (`:862`-`:1118`) it's documented to precede.

## Impact
None on ROM correctness. Misleads a future `/audit-pipeline` run into chasing wrong
locations. Every functional claim this session re-verified against current code (not the
stale citations) held true, so no false conclusion resulted yet.

## Related
#493, #497, #500 (same doc-rot class, other sibling skills, fixed), #406 (stage-helper
extraction that started this drift), #486/#487/#488 (recent fixes that moved things further).

## Suggested Fix
Run `/audit-sync` over `audit-pipeline/SKILL.md` for a full citation resync; consider
function-name-based references (`grep -rn <function>`) for the highest-churn functions
instead of line numbers.

## Completeness Checks
- [ ] **DOC**: All `main.py:NNNN` citations in `audit-pipeline/SKILL.md` re-verified against
  the live tree after the resync
