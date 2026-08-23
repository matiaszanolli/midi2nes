# Pipeline Integrity Audit — 2026-08-23

Auditor: `/audit-pipeline` (all 8 dimensions). Tree audited: `HEAD` (`d1bafed`).
Baseline: `docs/audits/AUDIT_PIPELINE_2026-08-22.md`. Dedup: `gh issue list --state all`
(368 issues, saved to `/tmp/audit/issues_all.json`).

`main.py` changed substantially since the 2026-08-22 baseline (770 → 2006 lines across four
commits: `934b597` #485-488, `a63be2d` the new `--visualizer` feature, `a9a7a21` #465-467,
`d1bafed` #495/#497/#498 — the last of these is my own commit from earlier in this session).
This pass re-verifies against current `HEAD`, not the 08-22 baseline's line numbers.

## Summary

| Dimension | Findings |
|---|---|
| 1. Stage JSON contract integrity | 0 (tracked question from prior reports now resolved) |
| 2. Full-pipeline vs step-by-step parity | 0 |
| 3. Flag routing | 0 (new `--visualizer` flag independently verified correct) |
| 4. Error propagation & fail-fast | 0 |
| 5. Temp-file / intermediate handling | 0 |
| 6. Backup & overwrite safety | 0 |
| 7. Large-file threshold & detector fallback | 0 |
| 8. Song-bank path (new-code audit) | 0 |
| Meta (audit skill doc-rot) | 1 (PIPE-2026-08-23-1, LOW) |

**Totals: 1 finding — 0 CRITICAL, 0 HIGH, 0 MEDIUM, 1 LOW.**

**All four findings carried forward in `AUDIT_PIPELINE_2026-08-22.md` are confirmed fixed and
closed**, independently re-verified in code this session (not trusted from the GitHub label
alone):
- **PIPE-2026-08-22-1** (HIGH, wrong-stage JSON silently empty): fixed by **#485**. Re-verified:
  `load_json_stage`'s `channel_shape=True` guard (`main.py:88`) rejects a non-empty JSON object
  with none of the five NES channel keys, while still accepting a genuine empty `{}`.
- **PIPE-2026-08-22-2** (HIGH, `run_song_build` had no backup/restore contract): fixed by
  **#486**. Re-verified: `run_song_build` (`main.py:999-1118`) now calls `_backup_existing_rom`
  up front and `build_and_validate_rom` (the same helper `run_full_pipeline` uses), with a
  `finally` block that restores on failure and cleans up the backup on success — identical
  contract to the other two ROM-build entry points.
- **PIPE-2026-08-22-3** (LOW, misleading `--arranger` rejection message): fixed by **#487**.
  Re-verified: the pre-subcommand rejection now special-cases `song build --arranger`
  (`main.py:1761-1770`) instead of claiming no step-by-step equivalent exists.
- **PIPE-2026-08-22-4** (LOW, `order` collision after remove+add): fixed by **#488**.
  Re-verified: `SongBank._next_order()` (`nes/song_bank.py:57-70`) derives the next value from
  `max(existing orders) + 1` instead of `len(self.songs)`, which can no longer collide with a
  surviving song's order after a remove.

**Tracked question from Dimension 1 (prior reports) is now resolved, not still open**: whether
`run_detect_patterns`'s persisted JSON omitting `variations` matters. It's moot now — fixed by
**#498** (my own fix earlier this session): the subcommand's on-disk `output` dict
(`main.py:839-843`) includes `'variations': pattern_result['variations']`, matching the
in-memory 4-key envelope both detectors return.

**New code independently audited, not verify-the-fix**: the `--visualizer` flag
(`a63be2d`, added today) was traced end-to-end as brand-new pipeline-flag-routing surface —
exactly the class of bug this skill exists to catch (F-03/#8, #175/PL-02 precedents). Verified:
declared on the top-level argparse parser (`main.py:1579`) mirroring `--debug`'s existing
pattern (no subcommand-local declaration for either — both rely on the documented
flag-before-subcommand form, confirmed working via a direct `argparse` reproduction); present
in the manual `global_args` whitelist loop (`main.py:1795-1797`, would otherwise hit the F-03
unknown-flag hard-error); wired into `SimpleArgs` (`main.py:1859`); and
`_reject_debug_visualizer_combo` is called on both the subcommand-dispatch path
(`main.py:1775`) and the default-pipeline path (`main.py:1869`), both *after* the flag is
populated on `args`. `run_prepare`/`run_export`/`build_and_validate_rom` all read it via the
same `getattr(args, 'visualizer', False)` defensive-default idiom the codebase already uses for
`--debug`. No gap found.

**Does the step-by-step path produce the same ROM as the default path?** Yes — same
`parser_fast`, `assign_tracks_to_nes_channels`/arranger, `NESEmulatorCore`, pattern-detection
constants and caps, `CA65Exporter`, `pack_dpcm_into_asm`, and now (since #486) the same
`build_and_validate_rom`/backup contract across all three ROM-build entry points
(`run_full_pipeline`, `run_compile`, `run_song_build`).

## Contract Map

| # | Boundary | Producer → key(s) → Consumer | Verified |
|---|---|---|---|
| 1 | parse → map | `parse_midi_to_frames` → `{"events", "metadata"}` → `load_json_stage(..., ['events'])` / `run_map` | ✓ |
| 2 | map → frames | `assign_tracks_to_nes_channels` → `{pulse1,pulse2,triangle,noise,dpcm}` → `process_all_tracks` | ✓ |
| 3 | frames → detect-patterns | frames JSON → `frames_to_events` (skips `dpcm_sample_map`) → `channel_shape` guard | ✓ — #485 fix confirmed live |
| 4 | detect-patterns → export | `{'patterns','references','stats','variations'}` → `load_json_stage(..., ['patterns','references'])` | ✓ — `variations` now persisted (#498), the prior tracked question is resolved |
| 5 | export → prepare | `music.asm` + engine/bank/DPCM/visualizer markers → `resolve_mapper` / `NESProjectBuilder` | ✓ — new `--visualizer` wiring verified |
| 6 | prepare → compile | `nes.cfg` `NES_CFG_MAPPER_MARKER` → `_prepared_mapper_name_from_cfg` | ✓ |
| 7 | compile → validate | `compile_rom` bool + ROM file → `validate_rom` fatal-defect gate | ✓ |
| 8a | song build: bank load | `SongBank.import_bank` → `songs[name]['metadata']['order']` → sorted build order | ✓ — order collision fixed (#488) |
| 8b | song build: re-parse | `midi_path` (absolute) → `midi_to_frames_for_song` (never `segments`) | ✓ |
| 8c | song build: DPCM gate | frames → `_song_has_dpcm_events` | ✓ |
| 8d | song build: capacity/prepare/compile/validate | shared `build_and_validate_rom`, backup/restore contract | ✓ — #486 fix confirmed live |

## Findings

### PIPE-2026-08-23-1: `audit-pipeline/SKILL.md`'s `main.py` line citations are broadly stale — the file grew from 770 to 2006 lines and function order changed since the skill was last synced
- **Severity**: LOW
- **Dimension**: Meta (doc-rot in the audit skill itself)
- **Location**: `.claude/commands/audit-pipeline/SKILL.md` — nearly every `main.py:NNNN`
  citation from Dimension 1 onward
- **Status**: NEW
- **Description**: `main.py` has grown to 2006 lines (from ~770 at the time this skill's
  prose was last written) across today's commits alone (`934b597`, `a63be2d`, `a9a7a21`,
  `d1bafed`), and — more disruptively for line citations than raw growth — its function
  *order* changed: the song-bank subcommands (`run_song_add`/`run_song_list`/
  `run_song_remove`/`run_song_build`, ~290 lines) and the `#406` stage helpers
  (`detect_patterns_or_direct_export`/`export_frames_and_resolve_mapper`/
  `build_and_validate_rom`, ~250 lines) now sit **before** `run_full_pipeline` in the file,
  which itself moved from roughly line 770 to **line 1402**. Every citation this skill makes
  into `run_full_pipeline`'s body (its `try`/`except`/`finally` block, the
  `LARGE_FILE_THRESHOLD` check, the fallback detector construction, etc. — Dimensions 1, 4, 6,
  7 all cite specific lines in the 770-1230 range) is now off by 400-630 lines. Representative
  confirmed-stale examples from this session's spot checks:
  - `load_json_stage` cited at `main.py:64-93` → actually defined at `:88` (def line alone).
  - `run_full_pipeline`'s outer `try`/`except`/`finally` cited at `main.py:773`/`:1216`/
    `:1224-1229` → the function itself now starts at `:1402`; its `except`/`finally` are much
    later in the file (confirmed via `grep -n "except Exception as e:\|finally:"`, which lists
    over a dozen candidates in the 1400-2000 range with no easy 1:1 remap without reading the
    function body).
  - `LARGE_FILE_THRESHOLD` and the fallback block cited at `main.py:818`/`:827-853`/`:844` are
    inside `detect_patterns_or_direct_export` (now `main.py:1149-1273`), a function this same
    skill's own Dimension 1 already documents as having been extracted out of
    `run_full_pipeline` by #406 — but Dimensions 6/7's own citations weren't updated to match
    when that extraction happened, and have drifted further since.
  - This is the same doc-rot class already caught and fixed this week in the sibling
    `audit-arranger` (#493), `audit-patterns` (#497), and `audit-dpcm` (#500) skill files —
    `audit-pipeline` is the remaining sibling that hasn't had an equivalent sync pass, and
    (because `main.py` is the largest, most citation-dense file any of these skills reference)
    has the largest drift of the four.
- **Evidence**: `wc -l main.py` → 2006 (vs. the skill's implicit ~800-1200-line assumption
  throughout); `grep -n "^def run_\|^def detect_patterns_or_direct_export\|^def
  export_frames_and_resolve_mapper\|^def build_and_validate_rom"  main.py` shows
  `run_full_pipeline` at `:1402`, well after the stage helpers (`:1149`, `:1274`, `:1355`) and
  the song-bank subcommands (`:862`-`:1118`) it's documented to precede.
- **Impact**: None on ROM correctness — this is the audit skill's own prose, not shipped code.
  Every functional claim this session re-verified against the *current* code (not the stale
  citations) held true — see the Summary's verify-the-fix section — so the drift hasn't yet
  caused a false "still broken" or "still fine" conclusion. But at this volume of stale
  citations (the majority of Dimensions 1/4/6/7's line references), a future audit pass is at
  real risk of chasing wrong locations, and a full manual resync (as opposed to the ~5-10
  citations each sibling skill needed) is a nontrivial task worth scoping deliberately rather
  than doing piecemeal per future audit.
- **Related**: #493 (arranger skill doc-rot, same class, fixed), #497 (patterns skill doc-rot,
  same class, fixed), #500 (dpcm skill doc-rot, same class, fixed), #406 (the stage-helper
  extraction that started this dimension's drift), #486/#487/#488 (today's fixes that moved
  `run_song_build` substantially and added net new lines before `run_full_pipeline`).
- **Suggested Fix**: Run `/audit-sync` over `audit-pipeline/SKILL.md` for a full citation
  resync — given the scale, budget it as its own pass rather than folding it into an unrelated
  fix, and consider whether Dimensions 1/4/6/7's prose can reference function names alone
  (`grep -rn <function>`) for the highest-churn functions (`run_full_pipeline`, the stage
  helpers, `run_song_build`) rather than line numbers, to reduce how often this recurs as
  `main.py` keeps growing.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-08-23.md
```
