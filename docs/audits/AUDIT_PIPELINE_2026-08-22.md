# Pipeline Integrity Audit — 2026-08-22

Auditor: Claude (audit-pipeline skill)
Tree audited: `master` @ `b532b89`
Baseline for this pass: `AUDIT_PIPELINE_2026-08-21.md` (audited at `949f0c6`). All four
findings from that report that were filed on GitHub (#425 CRITICAL, #426 CRITICAL, #427
MEDIUM, #428 LOW) are confirmed fixed and closed. The remaining four (PIPE-2026-08-21-2
HIGH, -4 HIGH, -6 LOW, -7 LOW) were never filed and are re-verified **still present** below
— this report carries them forward rather than re-deriving them from scratch, since a
targeted `git diff 949f0c6..HEAD -- main.py` confirms none of the touched lines changed.

Relevant commits since `949f0c6`: `fa179ae` (#425/#426 fixes — channel-9 drum filter,
51-song jukebox cap), `03446c5` (#429/#445/#449/#471), `8519a9f` (#453-456 — jukebox
prepare auto-detect, resolved ca65/ld65 paths, song-add exception handling, atomic bank
write), `1a23409` (#457/#428 — typed exceptions so capacity/mapper/compile/validate
failures no longer misreport as "unexpected"), `efecc87` (#435-438, patterns domain —
`main.py`'s `--no-patterns` stats stub now routes through `frames_to_events`), `bd5d431`
(#427/#442-444), `0a16a93`/`f19723e` (nes-hardware/regression fixes, no pipeline-contract
surface touched).

Dedup inputs: `gh issue list --state all` (355 issues checked), prior reports in
`docs/audits/` (especially `AUDIT_PIPELINE_2026-08-21.md`), `.claude/issues/`.

## Summary

| Dimension | Findings |
|---|---|
| 1. Stage JSON contract integrity | 1 (PIPE-2026-08-22-1 HIGH, carried) |
| 2. Full-pipeline vs step-by-step parity | 0 |
| 3. Flag routing | 1 (PIPE-2026-08-22-3 LOW, carried) |
| 4. Error propagation & fail-fast | 0 |
| 5. Temp-file / intermediate handling | 0 |
| 6. Backup & overwrite safety | 1 (PIPE-2026-08-22-2 HIGH, carried) |
| 7. Large-file threshold & detector fallback | 0 |
| 8. Song-bank path (new-code audit) | 1 (PIPE-2026-08-22-4 LOW, carried) |

**Totals: 4 findings — 0 CRITICAL, 2 HIGH, 0 MEDIUM, 2 LOW.** All four are carry-overs from
`AUDIT_PIPELINE_2026-08-21.md`, re-verified against today's tree; no new findings surfaced
this pass. This is a substantially quieter result than the prior report (which had 2
CRITICAL) — both CRITICALs were filed and fixed same-day.

**Single most dangerous contract break**: PIPE-2026-08-22-1. The step-by-step `frames`/
`export`/`detect-patterns` subcommands still accept a JSON file from the *wrong* pipeline
stage with no error — `load_json_stage(args.input, [], ...)` — and silently produce an
empty (but exit-0, "successful") result at every step downstream. This is a regression of
closed issue #377, whose fix commit (`c4894d2`) was never merged to master; re-confirmed
live today with the exact repro from the prior report.

**Does the step-by-step path produce the same ROM as the default path?** Yes. Both entry
points share `tracker/parser_fast.py`, `assign_tracks_to_nes_channels`/the arranger,
`NESEmulatorCore`, the `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH` constants, the shared
`get_pattern_detection_caps` resolver, `CA65Exporter`, the shared `pack_dpcm_into_asm`, and
the same `prepare`/`compile`/`validate_rom`/backup contract (`build_and_validate_rom`).
`run_song_build` (Dimension 8) is the one build path that does *not* share the
backup/restore/typed-exception contract the other two do — see PIPE-2026-08-22-2.

## Contract Map

| # | Boundary | Producer → key(s) → Consumer | Verified |
|---|---|---|---|
| 1 | parse → map | `parse_midi_to_frames` → `{"events", "metadata"}` → `load_json_stage(..., ['events'])` / `run_map` | ✓ |
| 2 | map → frames | `assign_tracks_to_nes_channels` → `{pulse1,pulse2,triangle,noise,dpcm}` → `process_all_tracks` | ✓ — #425's channel-9 filter fix confirmed in `dpcm_sampler/enhanced_drum_mapper.py`; melodic notes no longer pollute `dpcm` |
| 3 | frames → detect-patterns | frames JSON → `frames_to_events` (skips `dpcm_sample_map`) | ✓ shape / **✗ guard** — wrong-stage JSON still passes silently (PIPE-2026-08-22-1) |
| 4 | detect-patterns → export | `{'patterns','references','stats'}` → `load_json_stage(..., ['patterns','references'])` | ✓ (`variations` omission from the subcommand's JSON remains consumer-less — tracked question, not a finding) |
| 5 | export → prepare | `music.asm` + engine/bank/DPCM markers → `resolve_mapper` / `NESProjectBuilder` | ✓ |
| 6 | prepare → compile | `nes.cfg` `NES_CFG_MAPPER_MARKER` → `_prepared_mapper_name_from_cfg` | ✓ |
| 7 | compile → validate | `compile_rom` bool + ROM file → `validate_rom` fatal-defect gate | ✓ — now raises typed `CompilationError`/`ValidationError` (#457), both `MIDI2NESError` |
| 8a | song build: bank load | `SongBank.import_bank` → `songs[name]['metadata']['order']` → sorted build order | ✓ mechanism, ✓ per-song shape validated (#427 fix confirmed) / ✗ order can still collide (PIPE-2026-08-22-4) |
| 8b | song build: re-parse | `midi_path` (absolute) → `midi_to_frames_for_song` (never `segments`) | ✓ — missing path exits 1 cleanly before any build |
| 8c | song build: DPCM gate | frames → `_song_has_dpcm_events` | ✓ — no longer false-positives on melodic songs (#425 fix) |
| 8d | song build: export → engine | `export_song_bank_bytecode` `song_table_*` (stride 5) → `load_song_streams_indexed` (8-bit `current_song*5`) | ✓ — 51-song cap confirmed in place (#426 fix) |
| 8e | song build: capacity | combined `music.asm` → `check_mapper_capacity` (`main.py:1019`) | ✓ |
| 8f | song build: prepare | `song_count=len(songs)` → `JUKEBOX_BUILD` gate | ✓ mechanism / ✗ return value unchecked, no backup/restore (PIPE-2026-08-22-2) |

## Findings

### PIPE-2026-08-22-1: Wrong-stage JSON still silently yields empty output on the step-by-step path — regression of #377, unmerged fix, unchanged since last audit
- **Severity**: HIGH
- **Dimension**: 1 (Stage JSON contract integrity)
- **Both paths?**: Step-by-step only (`frames`, `export`, `detect-patterns` subcommands);
  the default pipeline passes in-memory structures and cannot hit this.
- **Location**: `main.py:251` (`run_frames`: `load_json_stage(args.input, [], 'map')`),
  `main.py:649` (`run_export`: `load_json_stage(args.input, [], 'frames')`), `main.py:735`
  (`run_detect_patterns`: same `[]` guard); `nes/emulator_core.py:161-...`
  (`process_all_tracks` — `if/elif` over the five channel names, no `else`, confirmed still
  the case at line 161 of the current tree).
- **Status**: Existing — carried verbatim from `AUDIT_PIPELINE_2026-08-21.md`
  (PIPE-2026-08-21-2), never filed on GitHub. Regression of #377 (closed 2026-08-05 as
  "Fixed in c4894d2", but that commit was never merged to master — re-confirmed this pass:
  `git merge-base --is-ancestor c4894d2 master` still fails, and `git log --all --grep
  c4894d2` finds no trace of it having landed via any other commit since).
- **Description**: `load_json_stage` with `required_keys=[]` accepts any JSON object, and
  `process_all_tracks` silently ignores unknown top-level keys (no `else` branch on its
  channel-name dispatch), so feeding a *parse*-stage file (`{"events": ..., "metadata":
  ...}`) to the `frames` subcommand produces an empty `{}` frames dict with exit 0. The
  empty output flows onward unchallenged: `export` happily writes a valid-looking `music.asm`
  with zero channels and exit 0.
- **Evidence**: Live repro on this tree (identical to the 2026-08-21 report's repro, re-run
  to confirm no drift):
  ```
  $ printf '{"events": [{"frame": 0, "note": 60, "velocity": 100, "channel": 0}], "metadata": {}}' > parsed.json
  $ python main.py frames parsed.json frames_out.json
   Generated frames -> frames_out.json      # exit 0
  $ cat frames_out.json
  {}
  $ python main.py export frames_out.json music_out.asm
  🔧 CA65 Exporter: Direct frame export mode (table-based)
    Channels: []
    Data size: 0 bytes (0.0 KB)
   Exported CA65 ASM -> music_out.asm        # exit 0, 2739-byte music.asm, no music data
  ```
  Zero diagnostics at any step.
- **Impact**: The documented step-by-step debugging path silently produces empty
  intermediates and ultimately a silent/empty ROM when a user passes the wrong stage's JSON
  — the exact defect class #120/SAFE-01's `load_json_stage` guard exists to catch, defeated
  here because these three call sites pass an empty `required_keys` list. Process note
  (repeated from the prior report, still true): a GitHub issue marked CLOSED cannot be
  trusted without an ancestry check on its stated fix commit — #378 and #379's fixes did
  land on master via other commits; #377's did not.
- **Related**: #377/PIPE-2026-07-19-1, #120/SAFE-01, orphaned branch
  `fix/issue-377-wrong-stage-json-guard` (commit `c4894d2`).
- **Suggested Fix**: Re-land `c4894d2`'s guard (or re-implement it fresh, since the branch
  may have drifted): have `run_frames`/`run_export`/`run_detect_patterns` reject a JSON
  object containing none of the five channel keys, with the parse-stage `events` key called
  out specifically in the error message so a user pointed at the wrong file gets an
  actionable diagnosis instead of a silent empty result.

### PIPE-2026-08-22-2: `run_song_build` still has no backup/restore contract, no exception safety net, and ignores `prepare_project`'s return value
- **Severity**: HIGH
- **Dimension**: 6 (Backup & Overwrite Safety) + 8 (Song-Bank Path)
- **Both paths?**: N/A — `song build` only. `run_full_pipeline` (`build_and_validate_rom`,
  `main.py:1279-1311`) and `run_compile` both re-verified correct this pass — both check
  `prepare_project`'s return value, both raise typed `MIDI2NESError` subclasses since
  `1a23409`/#457, and both go through the shared `_backup_existing_rom`/`_restore_backup`
  helpers.
- **Location**: `main.py:1004-1037` (`run_song_build`'s build tail): no
  `_backup_existing_rom`/`_restore_backup` call anywhere in the function; no
  `try`/`except`/`finally` around `builder.prepare_project(...)` (`:1026`),
  `compile_rom(...)` (`:1029`), or `validate_rom(...)` (`:1035`); `prepare_project`'s
  boolean return is not checked at `:1026` — contrast `build_and_validate_rom:1298`
  (`if not builder.prepare_project(...): raise ExportError(...)`), which does.
- **Status**: Existing — carried verbatim from `AUDIT_PIPELINE_2026-08-21.md`
  (PIPE-2026-08-21-4), itself carried from `AUDIT_PIPELINE_2026-08-07.md` (PL-2026-08-07-2).
  Never filed as its own issue, but its root cause **is** tracked and open as
  **#467/TD-32** ("`run_song_build` re-implements the capacity→prepare→compile→validate
  sequence instead of reusing `build_and_validate_rom`") — #467's own body explicitly
  anticipates this: *"the HIGH-severity consequence is PIPE-2026-08-21-4's finding; this
  entry tracks the duplication root cause"* and *"Related: PIPE-2026-08-21-4 ... if/when
  filed"*. Re-verified live on today's tree — none of the three `song_bank`/jukebox commits
  since `949f0c6` (`fa179ae`, `03446c5`, `8519a9f`) touched `run_song_build`'s build tail.
- **Description**: Unchanged from both prior reports. A re-run of `song build` over a
  previously-good ROM that compiles but fails `validate_rom` leaves the broken ROM at the
  output path (no backup taken, no `.nes.failed` rename on a first-time failure either,
  since `_restore_backup` is never called at all). Any exception out of `prepare_project`
  (which can raise `ExportError`, or `MapperError`/`ValueError` from its internal
  post-append `check_mapper_capacity` re-check at `nes/project_builder.py:239`) surfaces as
  a raw traceback instead of the `[ERROR]` + exit-1 convention every other build path now
  follows consistently (post-#457). `prepare_project`'s boolean return being ignored means a
  falsy-but-non-raising failure silently proceeds to `compile_rom`, which then fails with a
  misleading "Compilation failed" instead of "Failed to prepare NES project".
- **Evidence**: `grep -n "_backup_existing_rom\|_restore_backup" main.py` → 4 hits, all in
  `run_full_pipeline`/`run_compile`, zero in `run_song_build` (re-confirmed, unchanged
  count from the prior report); code read of `main.py:1004-1037` shows no
  `try`/`except`/`finally` wrapping the build tail at all.
- **Impact**: Unchanged — last-known-good jukebox ROM destroyed by a failed rebuild; raw
  tracebacks for expected, documented failure modes (oversized bank, bad mapper choice,
  missing `audio_engine.asm`). This is now the **only** one of the three ROM-build entry
  points (`run_full_pipeline`, `run_compile`, `run_song_build`) without this contract —
  the other two were fixed months ago (#26/F-11, #178/PL-05) and re-verified clean again
  this pass.
- **Related**: #467/TD-32 (open, tracks the duplication root cause that causes this),
  #26/F-11, #178/PL-05 (the same contract, already implemented on the other two paths).
- **Suggested Fix**: As #467 itself suggests — parameterize `build_and_validate_rom` to
  accept `song_count`/an already-exported `music_asm` path, and have `run_song_build` call
  it inside the same backup/restore/typed-exception wrapper `run_full_pipeline` and
  `run_compile` already use, rather than re-implementing the sequence a third time. Filing
  this as the HIGH pipeline-domain finding #467 anticipated, cross-referenced both ways.

### PIPE-2026-08-22-3: Pre-subcommand `--arranger` rejection message still denies that `song build --arranger` exists
- **Severity**: LOW
- **Dimension**: 3 (Flag Routing)
- **Both paths?**: N/A — CLI parsing/diagnostics only.
- **Location**: `main.py:1668-1669` (the blanket rejection: "--arranger only applies to the
  default MIDI-to-ROM pipeline; there is no step-by-step equivalent yet");
  `main.py:1613-1614` (`p_song_build`'s own `--arranger`, consumed at `main.py:968`).
- **Status**: Existing — carried verbatim from `AUDIT_PIPELINE_2026-08-21.md`
  (PIPE-2026-08-21-6), itself carried from `AUDIT_PIPELINE_2026-08-07.md` (PL-2026-08-07-3).
  Re-verified live this pass: `python main.py --arranger song build x.json y.nes` still
  prints the denial and exits 2, while `python main.py song build x.json y.nes --arranger`
  works (`p_song_build`'s `--arranger` flag is read at `main.py:968`,
  `use_arranger = getattr(args, 'arranger', False)`).
- **Description/Impact/Fix**: Unchanged from both prior reports — misleading diagnostic
  only, no functional break (the working `song build ... --arranger` order is unaffected).
  Point the user at `song build … --arranger` instead of denying it exists.
- **Related**: PL-2026-08-07-3, PIPE-2026-08-21-6, #174/PL-01.

### PIPE-2026-08-22-4: `metadata['order']` still collides after `song remove` + `song add`
- **Severity**: LOW
- **Dimension**: 8 (Song-Bank Path)
- **Both paths?**: N/A — `song build` only.
- **Location**: `nes/song_bank.py:92` and `:131` (`order=len(self.songs)` at both add
  sites), `main.py:868-883` (`run_song_remove` deletes without renumbering), `main.py:966`
  (the sort in `run_song_build` that consumes `order`).
- **Status**: Existing — carried verbatim from `AUDIT_PIPELINE_2026-08-21.md`
  (PIPE-2026-08-21-7), itself carried from `AUDIT_PIPELINE_2026-08-07.md` (PL-2026-08-07-4).
  Re-verified unchanged: none of `fa179ae`/`03446c5`/`8519a9f`/`bd5d431` touched
  `order=len(self.songs)` or `run_song_remove`'s body (`bd5d431`'s `nes/song_bank.py`
  changes were confined to `import_bank`'s per-entry validation, per PIPE-2026-08-22-1's
  contract-map entry 8a).
- **Description/Impact/Fix**: Unchanged — add songs A, B, C (`order` 0, 1, 2); remove B;
  add D → D gets `order=len(self.songs)=2`, colliding with C's `order=2`. Python's stable
  sort currently masks this in the simple case (ties keep insertion order, which happens to
  still be roughly chronological), but it is not a guaranteed-correct ordering — renumber
  remaining songs on `song remove`, or switch to a never-reused monotonic counter (e.g. a
  bank-level `next_order` field) instead of `len(self.songs)`.
- **Related**: PL-2026-08-07-4, PIPE-2026-08-21-7, #30/F-13.

## Verify-the-Fix Confirmations (re-checked this pass, no regressions found)

- **D1**: `load_json_stage` (#120/SAFE-01) still guards all subcommand reads; `run_map`
  still requires `['events']`; `run_export` still requires `['patterns','references']` for
  its `--patterns` file. `detect-patterns` still omits `variations` from its JSON — still
  consumer-less, remains a tracked question not a bug. #379: both export entry points still
  pass `pattern_result['references']`/`pattern_data['references']` straight through
  (confirmed unchanged in the `git diff`).
- **D2**: Single parser everywhere — `parser_fast` in `run_parse`, `run_full_pipeline`,
  `midi_to_frames_for_song`, `SongBank`; zero production imports of the old `tracker.parser`.
  Shared `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH` constants unchanged. The `--no-patterns`
  stub's stats schema changed *shape of computation* (now via `frames_to_events`, #435) but
  not *schema* — still `original_size`/`compressed_size`/`compression_ratio`/
  `unique_patterns`/`total_events`/`patterned_events`/`coverage_ratio`, still matching both
  real detectors' output shape. All banner reads remain schema-safe on both paths.
- **D3** (spot-checked): `--version` alone and `--version song.mid` both still print the
  version and exit 0; `--bogus` still exits 2 with "Unknown option"; `--arranger` before a
  subcommand still exits 2 (message staleness is PIPE-2026-08-22-3); `prepare` still passes
  `debug_mode`; `map` still honors `--dpcm-index`. No new `add_argument` call was added
  since `949f0c6` whose handler ignores it (only argument list changes since then were
  exception-type-only, no new flags).
- **D4**: `validate_rom` still fail-closed on diagnostics failure with an unconditional
  warning; fatal-defect gate still runs before health scoring. CC65 failures still return
  `False` → `sys.exit(1)` on all three build paths. **Improved this pass (#457)**:
  `check_mapper_capacity`/`resolve_mapper`/`enforce_direct_export_dpcm_mapper` now raise
  `MapperError` (a `MIDI2NESError` + `ValueError` subclass) instead of a bare `ValueError`,
  and `build_and_validate_rom` raises `ExportError`/`CompilationError`/`ValidationError`
  instead of bare `RuntimeError` — closing PIPE-2026-08-21-8/#428, confirmed fixed and
  closed on GitHub. `pack_dpcm_into_asm` remains the single shared DPCM-pack site with
  partial-miss labeling.
- **D5**: Default path still writes `music.asm`/`nes_project/` inside the
  `TemporaryDirectory`; final ROM still goes to the user's `output_rom`. No change to this
  code since `949f0c6`.
- **D6**: `run_full_pipeline` — backup, `finally`-restore, and success-path unlink all
  unchanged and re-confirmed present; `run_compile` still mirrors it. `run_song_build`
  remains the outlier (PIPE-2026-08-22-2, above) — unchanged since the prior report.
- **D7**: Fallback still samples uniformly via `sample_events_for_detection`; warning text
  still says analysis-only; `run_detect_patterns` still samples symmetrically with the
  default path. Both caps still resolve through `get_pattern_detection_caps` on both paths.
  No change to any of this code since `949f0c6` (`efecc87`'s changes were internal to the
  detector modules' tempo/worker-payload handling, not the threshold/fallback/sampling
  contract `main.py` exposes).
- **D8**: `#425`'s channel-9 filter is confirmed present in
  `dpcm_sampler/enhanced_drum_mapper.py` — `_song_has_dpcm_events` no longer false-positives
  on melodic content, closing the CRITICAL two-direction bug from the prior report. `#426`'s
  51-song cap is confirmed present in `export_song_bank_bytecode`. `#427`'s per-song-entry
  validation in `import_bank` is confirmed present and matches the description exactly
  (validates `entry` is a dict, `metadata` is a dict, before storing `self.songs`).
  `run_song_add`'s exception handling (#455) and `SongBank.export_bank`'s atomic write
  (#456) both confirmed present. The two still-open Dimension 8 gaps
  (PIPE-2026-08-22-2/-4) are unchanged carry-overs, not new.

## Next Step

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-08-22.md
```
