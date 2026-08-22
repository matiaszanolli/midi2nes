# Pipeline Integrity Audit — 2026-08-21

Auditor: Claude (audit-pipeline skill)
Tree audited: `master` @ `949f0c6` ("Enhance jukebox engine paths and audit processes")
Relevant recent commits: `8ea7ac3` (song-build JUKEBOX_BUILD gate + per-song CODE_8000 reset),
`ffccf51` (drum mapping reads 'volume' key — **introduces this pass's CRITICAL regression**),
`949f0c6` (docs/skills only, no code).

Dedup inputs: `gh issue list` (2 open issues, both unrelated user questions; closed set
checked through #414), `/tmp/audit/issues.json`, prior reports in `docs/audits/`
(especially `AUDIT_PIPELINE_2026-08-07.md` and `AUDIT_DPCM_2026-08-07.md`).

## Summary

| Dimension | Findings |
|---|---|
| 1. Stage JSON contract integrity | 2 (PIPE-2026-08-21-1 CRITICAL, PIPE-2026-08-21-2 HIGH) |
| 2. Full-pipeline vs step-by-step parity | 0 (all verify-the-fix checks pass) |
| 3. Flag routing | 1 (PIPE-2026-08-21-6 LOW, carried) |
| 4. Error propagation & fail-fast | 1 (PIPE-2026-08-21-8 LOW) |
| 5. Temp-file / intermediate handling | 0 |
| 6. Backup & overwrite safety | 1 (PIPE-2026-08-21-4 HIGH, carried) |
| 7. Large-file threshold & detector fallback | 0 |
| 8. Song-bank path (new-code audit) | 3 (PIPE-2026-08-21-3 CRITICAL, -5 MEDIUM, -7 LOW) |

**Totals: 8 findings — 2 CRITICAL, 2 HIGH, 1 MEDIUM, 3 LOW.**

**Single most dangerous contract break**: PIPE-2026-08-21-1. Commit `ffccf51` (the
DP-DPCM-12 fix) un-gated `EnhancedDrumMapper.map_drums`'s whole-input event scan, which has
**no channel-9 filter**. Every melodic note-on in every legacy-mode (non-`--arranger`) run
is now interpreted as a GM percussion note and emitted as a DPCM drum trigger. Reproduced
end-to-end on this tree: the default pipeline builds `test_midi/simple_loop.mid` (a
completely drumless file) into a "SUCCESS" ROM that packs **3 phantom DPCM samples** and
triggers them over the melody; `song build` now falsely rejects the same drumless song with
"contains DPCM drum samples". This silently changes the song on essentially every
legacy-mode build and functionally breaks `song build` for melodic banks.

**Does the step-by-step path produce the same ROM as the default path?** Yes — with the
same caveats as prior passes. Both entry points use `tracker/parser_fast.py`, the same
mapper (`assign_tracks_to_nes_channels`) / arranger, the same `NESEmulatorCore`, the shared
`PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH` constants, the shared
`get_pattern_detection_caps` resolver, the same `CA65Exporter`, the same shared
`pack_dpcm_into_asm`, and the same `prepare`/`compile`/`validate_rom`/backup contract. All
emitted music bytes derive from `frames`, so the documented detector differences (parallel
cap 15000 vs sequential cap 1000) affect only the patterns/stats metadata, except in the
theoretical edge where one detector returns zero patterns and the other doesn't (mode
switch direct-vs-bytecode). PIPE-2026-08-21-1 corrupts both paths *identically* (same
mapper stage), so it does not break parity — it breaks both.

## Contract Map

| # | Boundary | Producer → key(s) → Consumer | Verified |
|---|---|---|---|
| 1 | parse → map | `parse_midi_to_frames` → `{"events", "metadata"}` → `load_json_stage(..., ['events'])` / `run_map` | ✓ |
| 2 | map → frames | `assign_tracks_to_nes_channels` → `{pulse1,pulse2,triangle,noise,dpcm}` → `process_all_tracks` | ✓ shape / **✗ semantics** — the `dpcm` list is now polluted with melodic-note pseudo-drum events (PIPE-2026-08-21-1) |
| 3 | frames → detect-patterns | frames JSON → `frames_to_events` (skips `dpcm_sample_map`, #261) | ✓, but wrong-stage JSON still passes silently (PIPE-2026-08-21-2) |
| 4 | detect-patterns → export | `{'patterns','references','stats'}` → `load_json_stage(..., ['patterns','references'])` | ✓ (`variations` omission from the subcommand's JSON remains consumer-less — tracked question, not a finding) |
| 5 | export → prepare | `music.asm` + engine/bank/DPCM markers → `resolve_mapper` / `NESProjectBuilder` | ✓ |
| 6 | prepare → compile | `nes.cfg` `NES_CFG_MAPPER_MARKER` → `_prepared_mapper_name_from_cfg` | ✓ |
| 7 | compile → validate | `compile_rom` bool + ROM file → `validate_rom` fatal-defect gate | ✓ (fail-closed on diagnostics failure, #177) |
| 8a | song build: bank load | `SongBank.import_bank` → `songs[name]['metadata']['order']` → sorted build order | ✓ mechanism / ✗ per-song shape unvalidated (PIPE-2026-08-21-5) and order can collide (PIPE-2026-08-21-7) |
| 8b | song build: re-parse | `midi_path` (absolute) → `midi_to_frames_for_song` (never `segments`) | ✓ — missing path exits 1 cleanly before any build |
| 8c | song build: DPCM gate | frames → `_song_has_dpcm_events` | ✓ inspects real exported frames (both front-ends emit `{note, volume}`), but false-positives on every melodic song via PIPE-2026-08-21-1 |
| 8d | song build: export → engine | `export_song_bank_bytecode` `song_table_*` (stride 5, N songs) → `load_song_streams_indexed` (8-bit `current_song*5`) | **✗** — index overflows at song index ≥ 51 (PIPE-2026-08-21-3) |
| 8e | song build: capacity | combined `music.asm` → `check_mapper_capacity` (main.py:1007) + `prepare_project`'s internal re-check | ✓ — `MMC3Mapper.validate_segment_sizes` enforces both the per-region byte budgets *and* `max_bank >= SWAP_BANK_COUNT`, so an N-song 60-bank-pool overrun (including a song *starting* past bank 59) fails with a clean ValueError, not an ld65 error |
| 8f | song build: prepare | `song_count=len(songs)` → `JUKEBOX_BUILD` gate `song_count is not None` | ✓ — 8ea7ac3 fix confirmed by code read AND a live 1-song `--arranger` build (compiled, linked, validated) |

## Findings

### PIPE-2026-08-21-1: DP-DPCM-12's fix un-gates a channel-blind drum scan — every melodic note becomes a phantom DPCM drum trigger, and `song build` falsely rejects drumless songs
- **Severity**: CRITICAL
- **Dimension**: 1 (map-stage contract) + 8 (song-bank path)
- **Both paths?**: Both — the default pipeline and the step-by-step `map` subcommand share
  `assign_tracks_to_nes_channels`; `song build` (legacy mode) is broken in the opposite
  direction (false rejection). `--arranger` mode is unaffected on all three.
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:308-330` (`map_drums`'s per-track,
  per-event loop — no `channel == 9` filter anywhere in the method); trigger commit
  `ffccf51` (changed line 324 to `velocity = e.get('velocity', e.get('volume', 0))`);
  call site `tracker/track_mapper.py:348` (`map_drums_to_dpcm(midi_events, ...)` —
  deliberately passes the **full** parsed input so channel-9 drums in any track are found).
- **Status**: NEW (regression introduced by `ffccf51`, the fix for the 2026-08-07 DPCM
  audit's DP-DPCM-12; neither is filed on GitHub — issues checked through #414)
- **Description**: `EnhancedDrumMapper.map_drums` iterates *every* track's *every* event
  and resolves each note through the GM-percussion mapping
  (`_resolve_dpcm_sample_name(midi_note, ...)`). It has never had a channel-9 (or any
  drum-track) filter — but that latent flaw was invisible because the loop guarded on
  `e.get('velocity', 0) == 0`, and real parsed events (`tracker/parser_fast.py`) carry
  `'volume'`, never `'velocity'`, so the function was dead on real input (that deadness was
  DP-DPCM-12). `ffccf51` applied DP-DPCM-12's suggested fix verbatim — read `'volume'` as a
  fallback — which un-deadened the scan *without adding the missing channel filter*. Now
  every melodic note-on with volume > 0 is treated as a GM percussion note (MIDI note 60 =
  High Bongo, etc.), resolved against `dpcm_index.json`, and emitted as a real
  `{'frame', 'sample_id', 'velocity'}` DPCM event alongside the same note's legitimate
  pulse/triangle mapping. Notes that resolve to no sample fall to the noise-percussion
  branch instead. Downstream, `NESEmulatorCore.process_all_tracks` dutifully converts these
  into `{note: dense_id+1, volume: 15}` DPCM frames, the DPCM packer packs the referenced
  samples, and the engine triggers them at every melodic note-on. The DPCM audit's DP-DPCM-11
  explicitly warned "once DP-DPCM-12 is fixed, this finding should be re-verified" — the
  false-positive direction it predicted is exactly what shipped. The tests added in
  `ffccf51` (`tests/test_enhanced_drum_mapper.py`) feed only drum-shaped input, so the
  melodic-pollution direction is untested.
- **Evidence**: All reproduced live on this tree, `test_midi/simple_loop.mid` (single
  melodic track, channel 0, zero percussion):
  1. `python main.py map` output: `pulse1: 24 events` … and `dpcm: 12 events`
     (`[{'frame': 30, 'sample_id': 1932, 'velocity': 64}, …]`) — one phantom drum per
     melodic note-on (notes 60/64/67, `channel: 0` on every source event).
  2. Default pipeline `python main.py test_midi/simple_loop.mid out.nes` →
     `✓ Packed 3 DPCM samples across 1 banks` → `✅ SUCCESS!` — a drumless MIDI ships a ROM
     with three drum samples packed and triggered over the melody. No warning of any kind.
  3. `python main.py song add test_midi/simple_loop.mid --bank b.json --name solo` then
     `song build b.json out.nes` → `[ERROR] Song 'solo' contains DPCM drum samples…` —
     the identical command sequence the 2026-08-07 audit ran successfully at `f4c2283`
     now hard-fails on the same drumless input.
- **Impact**: Silent song change on effectively **every** legacy-mode build of melodic
  MIDI (most melody notes sit in the GM-percussion note range 35-81): phantom percussion
  is layered over the music, and DPCM's DMC channel activity also perturbs the mix. In the
  other direction, `song build` is functionally unusable for any melodic song in legacy
  mode (false DPCM rejection). Blast radius: `map` subcommand, default `run_full_pipeline`
  (legacy mode), `run_song_build` (legacy mode). Meets the CRITICAL floor twice over:
  "silent contract corruption" and "silently changes the song".
- **Related**: DP-DPCM-12 / DP-DPCM-11 / DP-DPCM-13 (`docs/audits/AUDIT_DPCM_2026-08-07.md`);
  `ffccf51`; #367/DP-DPCM-05 (the partial-miss warning machinery this pollution now
  routinely exercises with bogus ids).
- **Suggested Fix**: In `map_drums`'s event loop, skip events whose `e.get('channel')` is
  not 9 (parsed events always carry `channel`; hand-built test dicts can default to 9).
  Add the regression test DP-DPCM-11 asked for — a real melodic fixture through
  `parse → map` asserting `dpcm`/`noise` stay empty — alongside a channel-9 fixture
  asserting they don't.

### PIPE-2026-08-21-2: Wrong-stage JSON still silently yields empty output — #377 was closed but its fix was never merged to master
- **Severity**: HIGH
- **Dimension**: 1 (Stage JSON contract integrity)
- **Both paths?**: Step-by-step only (`frames`, `export`, `detect-patterns` subcommands);
  the default pipeline passes in-memory structures and cannot hit it.
- **Location**: `main.py:245-252` (`run_frames` calls `load_json_stage(args.input, [], 'map')`),
  `main.py:646`, `main.py:732` (same `[]` guard in `run_export`/`run_detect_patterns`);
  `nes/emulator_core.py:128-139` (`process_all_tracks` — if/elif over the five channel
  names, no else). Fix exists only on unmerged branch `fix/issue-377-wrong-stage-json-guard`
  (commit `c4894d2`).
- **Status**: Regression of #377 (closed 2026-08-05 as "Fixed in c4894d2", but
  `git merge-base --is-ancestor c4894d2 master` fails — the branch was never merged, and no
  equivalent guard landed via any other commit)
- **Description**: `load_json_stage` with `required_keys=[]` accepts any JSON object, and
  `process_all_tracks` ignores unknown keys, so feeding a *parse*-stage file to `frames`
  produces an empty frames dict with exit 0. The empty output then flows onward: `export`
  happily writes a music.asm with zero channels. The issue-tracker state says this is
  fixed; the tree says otherwise.
- **Evidence**: Live repro on this tree:
  `printf '{"events": [...], "metadata": {}}' > parsed.json`;
  `python main.py frames parsed.json frames_out.json` → `Generated frames -> …`, exit 0,
  file contains `{}`; `python main.py export frames_out.json music_out.asm` →
  `Channels exported: ` (empty), `Exported CA65 ASM`, exit 0, 1707-byte music.asm with no
  music data. Zero diagnostics at any step.
- **Impact**: The documented step-by-step debugging path silently produces empty
  intermediates and ultimately a silent ROM when a user passes the wrong stage's JSON —
  the exact defect class SAFE-01/#120's guard was built to catch, and the exact scenario
  #377 was filed for. Also a process finding: a closed issue whose fix commit is stranded
  on an unmerged branch means "CLOSED" state cannot be trusted without an ancestry check
  (the other `fix/issue-37x` branches were spot-checked: #378's and #379's fixes did land
  on master via other commits; #377's did not).
- **Related**: #377/PIPE-2026-07-19-1, #120/SAFE-01, branch `fix/issue-377-wrong-stage-json-guard`.
- **Suggested Fix**: Merge (or re-land) `c4894d2`'s guard: have `run_frames`/`run_export`/
  `run_detect_patterns` reject a JSON object containing none of the five channel keys
  (with the parse-stage `events` key called out specifically in the error message).

### PIPE-2026-08-21-3: Jukebox `song_table` is indexed with 8-bit `current_song*5` math — banks of 52+ songs build, validate, and then silently play the wrong streams
- **Severity**: CRITICAL
- **Dimension**: 8 (Song-Bank Path)
- **Both paths?**: N/A — `song build` only.
- **Location**: `nes/audio_engine.asm:259-286` (`load_song_streams_indexed`:
  `lda current_song / asl / asl / clc / adc current_song / tay` then five
  `lda song_table_*, y` reads with `iny`); producer `exporter/exporter_ca65.py:1623-1643`
  (`export_song_bank_bytecode` emits `song_table_ptr_lo/hi/bank` with `5 * len(songs)`
  entries, unbounded).
- **Status**: NEW (not in any prior report — `docs/audits/*2026-08*` grepped for the
  index math; not on GitHub)
- **Description**: The exporter emits the song table with stride 5 for N songs and no cap
  on N. The engine computes the base index `current_song * 5` in the 8-bit accumulator and
  walks it with an 8-bit Y register. At `current_song = 51` the base index is 255; the
  `iny` walk for channels 1-4 wraps to 0-3, so song 51 loads channels 1-4 from **song 0's**
  pulse1/pulse2/triangle/noise entries (shifted one channel). For `current_song >= 52` the
  multiply itself wraps (52*5 = 260 → 4), so every stream pointer/bank is read from the
  wrong song's (and wrong channel's) table slot. This is reachable: each song claims at
  least one fresh bank (`_build_song_bytecode` returns `current_bank + 1`), so up to 60
  small songs pass the exporter's `MAX_SEQUENCE_BANK` check, `check_mapper_capacity`
  (60 tiny per-song instrument/macro tables fit the 6144-byte CODE_8000 budget), CC65, and
  `validate_rom` (reset vectors and APU init are unaffected). Nothing warns at any stage.
  `song_instrument_ptr_*` (stride 1, max index 59) is safe; only the stride-5 table breaks.
- **Evidence**: Code read of both sides of the contract (exporter emission loop at
  `exporter_ca65.py:1629-1643`; engine math at `audio_engine.asm:267-276` — the comment
  even documents the `(x4)+x` trick with no range caveat). Arithmetic: 51*5 = 255 (channel
  walk wraps), 52*5 = 260 & 0xFF = 4. Reachability: 60-bank pool / ≥1 bank per song →
  52-60-song banks pass every gate (bank-count and CODE_8000 budgets verified against
  `mappers/mmc3.py:193-266`).
- **Impact**: A 52-60-song jukebox ROM ships as "validated" but songs at index ≥ 51 play
  other songs' streams on the wrong channels (and desync from their instrument table) —
  silent playback corruption with no build-time detection. Meets the CRITICAL floor
  "pipeline stage emits data a downstream stage parses as valid but means something else".
  Bounded blast radius (banks of 52+ songs), but severity is impact, not likelihood.
- **Related**: #30/F-13 (feature), 8ea7ac3, #127/MAP-2 (the analogous bank-count cap this
  slipped past because the table, not the banks, is the limit).
- **Suggested Fix**: Cheapest: have `export_song_bank_bytecode` raise a clear ValueError
  when `len(songs) > 51` (table index 5N-1 must stay ≤ 255), mirroring the
  `MAX_SEQUENCE_BANK` error. Alternatively widen the engine's lookup to 16-bit pointer
  arithmetic. Either way, add the limit to `docs/ROADMAP.md`'s v1 scope notes.

### PIPE-2026-08-21-4: `run_song_build` still has no backup/restore contract and no exception safety net (carried from 2026-08-07, unfixed)
- **Severity**: HIGH
- **Dimension**: 6 (Backup & Overwrite Safety) + 8
- **Both paths?**: N/A — `song build` only; `run_full_pipeline` and `run_compile` both
  re-verified correct this pass (`main.py:1309/1456-1460`, `:586-605`).
- **Location**: `main.py:989-1027` (`run_song_build`'s build tail: no
  `_backup_existing_rom`/`_restore_backup` (helpers at `main.py:475/491`), no
  `try/except/finally` around `builder.prepare_project(...)` (`:1014`),
  `compile_rom(...)` (`:1017`), `validate_rom(...)` (`:1022-1025`); additionally
  `prepare_project`'s return value is not checked at `:1014` — contrast `run_prepare`
  (`main.py:626-633`) and `build_and_validate_rom` (`main.py:1280-1281`), which both
  check it).
- **Status**: Existing — PL-2026-08-07-2 in `docs/audits/AUDIT_PIPELINE_2026-08-07.md`,
  never filed on GitHub and untouched by `8ea7ac3` (which changed only
  exporter/project-builder/song-bank files) — re-verified live on this tree.
- **Description**: Unchanged from the prior report: a re-run of `song build` over a
  previously good ROM that compiles but fails `validate_rom` leaves the broken ROM at the
  output path (no backup, no `.nes.failed` rename); any exception out of
  `prepare_project` (which can raise `ExportError`, or `ValueError` from its internal
  post-append `check_mapper_capacity` re-check at `nes/project_builder.py:239`) surfaces
  as a raw traceback instead of the `[ERROR]` + exit-1 convention. New detail this pass:
  `prepare_project`'s boolean return is also ignored — a falsy non-raising return would
  proceed to `compile_rom` and fail with a misleading "Compilation failed".
- **Evidence**: `grep -n "_backup_existing_rom\|_restore_backup" main.py` → 4 hits, all in
  `run_full_pipeline`/`run_compile`, zero in `run_song_build`; code read of `:989-1027`.
- **Impact**: Same as prior report — last-known-good jukebox ROM destroyed by a failed
  rebuild; raw tracebacks for expected failure modes.
- **Related**: PL-2026-08-07-2; #26/F-11, #178/PL-05 (the same contract, implemented on
  the other two build paths).
- **Suggested Fix**: Reuse `run_compile`'s exact structure: `backup_path =
  _backup_existing_rom(output_rom)` / `try: … build_succeeded = True finally:
  _restore_backup(...) or unlink backup`, plus `if not builder.prepare_project(...):`
  and a `try/except Exception` printing `[ERROR]`.

### PIPE-2026-08-21-5: `import_bank` validates bank-level shape but not per-song entries — a malformed bank crashes `song build`/`song list` with a raw KeyError
- **Severity**: MEDIUM
- **Dimension**: 8 (Song-Bank Path)
- **Both paths?**: N/A — `song` subcommands only.
- **Location**: `nes/song_bank.py:200-227` (`import_bank` checks `bank_info` and the
  presence of `'songs'`, but nothing about each song entry's shape); consumers
  `main.py:953-954` (`bank.songs[name]['metadata'].get('order', 0)`), `main.py:844-853`
  (`run_song_list` reads `song_data['metadata']`/`['bank']`), `main.py:962-963`
  (`song_data.get('midi_path')` — this one is defensive).
- **Status**: NEW
- **Description**: #220/SAFE-09 added the bank-level guard specifically so a corrupt or
  hand-edited bank fails with a clean message instead of a raw traceback, but the guard
  stops one level up: `data['songs']` values are stored as-is. A song entry missing
  `'metadata'` (or with a non-dict value, or missing `'bank'` for `song list`) raises an
  uncaught `KeyError`/`TypeError` inside `run_song_build`'s sort key or `run_song_list`'s
  print loop — a raw traceback, the exact presentation #220 was closing off. Banks written
  by `export_bank` always carry the keys, so this needs a hand-edited/truncated/
  version-drifted bank file — defense-in-depth, not a mainline break.
- **Evidence**: Code read: `import_bank` assigns `self.songs = data['songs']` with no
  per-entry validation; `run_song_build:954` indexes `['metadata']` unguarded inside the
  `sorted()` key lambda (outside the surrounding `try` that wraps only `import_bank`).
- **Impact**: Raw traceback instead of a clean `[ERROR]` on a malformed user file; exit is
  still nonzero and no ROM is produced, so no corruption — a robustness/UX gap.
- **Related**: #220/SAFE-09, #120/SAFE-01 (same defect class).
- **Suggested Fix**: In `import_bank`, validate each song entry is a dict with a dict
  `'metadata'` (raising the same `ValueError` style it already uses), or make the three
  consumer sites use `.get()` with defaults.

### PIPE-2026-08-21-6: Pre-subcommand `--arranger` rejection message still denies that `song build --arranger` exists (carried from 2026-08-07, unfixed)
- **Severity**: LOW
- **Dimension**: 3 (Flag Routing)
- **Both paths?**: N/A — CLI parsing/diagnostics only.
- **Location**: `main.py:1640-1651` (the blanket rejection: "--arranger only applies to
  the default MIDI-to-ROM pipeline; there is no step-by-step equivalent yet");
  `main.py:1592-1593` (`p_song_build`'s own `--arranger`, consumed at `main.py:956`).
- **Status**: Existing — PL-2026-08-07-3 in the prior report; re-verified live this pass:
  `python main.py --arranger song build x.json y.nes` still prints the denial and exits 2,
  while `python main.py song build x.json y.nes --arranger` works (used successfully in
  this audit's live jukebox build).
- **Description/Impact/Fix**: Unchanged from the prior report — misleading diagnostic
  only; point the user at `song build … --arranger` instead of denying it exists.
- **Related**: PL-2026-08-07-3, #174/PL-01.

### PIPE-2026-08-21-7: `metadata['order']` collides after `song remove` + `song add`, and `order` now drives jukebox playback order (carried from 2026-08-07, unfixed)
- **Severity**: LOW
- **Dimension**: 8 (Song-Bank Path)
- **Both paths?**: N/A — `song build` only.
- **Location**: `nes/song_bank.py:91` and `:131` (`order=len(self.songs)` at add time),
  `main.py:869-874` (`run_song_remove` deletes without renumbering), `main.py:953-954`
  (the sort that consumes `order`).
- **Status**: Existing — PL-2026-08-07-4 in the prior report; re-verified unchanged
  (`8ea7ac3` touched `nes/song_bank.py` but only the docstring and `midi_path` resolution,
  not `order`).
- **Description/Impact/Fix**: Unchanged — add A,B,C; remove B; add D → D ties C's
  `order=2`; stable sort currently masks it in simple cases. Renumber on remove or use a
  never-reused monotonic counter.
- **Related**: PL-2026-08-07-4, #30/F-13.

### PIPE-2026-08-21-8: Expected capacity/mapper `ValueError`s on the default path are reported as "Unexpected pipeline failure"
- **Severity**: LOW
- **Dimension**: 4 (Error Propagation & Fail-Fast)
- **Both paths?**: Default path only — `run_prepare`/`run_compile`/`run_export` catch
  `ValueError` explicitly and print a clean `[ERROR] <message>`.
- **Location**: `main.py:1446-1454` (the generic `except Exception` prints
  "Unexpected pipeline failure"); raisers: `check_mapper_capacity` via
  `build_and_validate_rom` (`main.py:1275`), `resolve_mapper`/
  `enforce_direct_export_dpcm_mapper` via `export_frames_and_resolve_mapper`
  (`main.py:1204-1256`) — both helpers' docstrings declare `ValueError` as an expected
  failure mode.
- **Status**: NEW (cosmetic residue of #384/SAFE-2026-07-19-2's typed/untyped split)
- **Description**: #384 narrowed the pipeline's blanket except into
  `except MIDI2NESError` ("expected, actionable") vs `except Exception` ("unexpected
  defect"). But the stage helpers signal expected user-facing failures (song too big for
  the mapper, invalid mapper for this music.asm) with plain `ValueError`, which is not a
  `MIDI2NESError` — so an ordinary oversized song prints "**Unexpected** pipeline
  failure: Music data does not fit …", contradicting the label's stated purpose while the
  same condition on the step-by-step path prints a clean `[ERROR]`.
- **Evidence**: `core/exceptions.py` — `ValueError` is not in the `MIDI2NESError`
  hierarchy; helper docstrings at `main.py:1194`/`1266` declare ValueError as the failure
  contract; `run_prepare:617-619` catches it explicitly.
- **Impact**: Message-labeling only — exit code, backup restore, and the actionable text
  are all still correct.
- **Related**: #384/SAFE-2026-07-19-2, #363/MAP-2026-07-19-3.
- **Suggested Fix**: Either add `except ValueError` alongside `except MIDI2NESError` in
  `run_full_pipeline`, or raise a typed `MIDI2NESError` subclass from
  `check_mapper_capacity`/`resolve_mapper`.

## Verify-the-Fix Confirmations (re-checked this pass, no regressions found)

- **D1**: `load_json_stage` (#120/SAFE-01) guards all subcommand reads; `run_map` requires
  `['events']`; `run_export` requires `['patterns','references']`. `detect-patterns` still
  omits `variations` from its JSON — still consumer-less (only `run_export` reads that
  file, and only for `patterns`/`references`); remains a tracked question, not a bug.
  #379: both export entry points pass `pattern_result['references']` (main.py:1224/700).
- **D2**: Single parser everywhere — `parser_fast` in `run_parse` (:219),
  `run_full_pipeline` (:1327), `midi_to_frames_for_song` (:894), `SongBank` (:11); zero
  production imports of `tracker.parser`. #19: both detector call sites use
  `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH` from `constants.py`; no other production call
  site hardcodes bounds. `--no-patterns` stub (:1085-1101) matches the detectors' full
  stats schema including `variations`, `coverage_ratio`, `total_events`; all banner reads
  are schema-safe on both paths.
- **D3** (live-tested): `--version` alone and `--version song.mid` both print
  `MIDI2NES 0.5.0-dev` and exit 0 (#179); `--bogus` exits 2 with "Unknown option" (#8);
  `--arranger` before a subcommand exits 2 (#174 — message staleness is
  PIPE-2026-08-21-6); `prepare` passes `debug_mode` (#175, main.py:622); `map` honors
  `--dpcm-index` (#13, :230) and pre-checks its existence (#256); `--config`/`--mapper`
  are consumed by both the manual whitelist (:1689-1700) and `SimpleArgs` (:1735-1738);
  no subcommand declares a flag its handler ignores (all `add_argument`s traced to reads).
- **D4**: `validate_rom` fail-closed on diagnostics failure (#177, :519-524) with
  unconditional warning; fatal-defect gate before health (#6, :526-535); CC65 failures
  return False → `sys.exit(1)` on all three build paths; `pack_dpcm_into_asm` is the
  single shared DPCM-pack site (#380) with partial-miss labeling (#367).
- **D5**: Default path writes `music.asm`/`nes_project/` inside the
  `TemporaryDirectory`; final ROM goes to the user's `output_rom`; nothing reads temp
  content after the `with`. Exporter writes via `atomic_write_text` (truncate-replace,
  #385), so re-run DPCM appends cannot accumulate (F-10).
- **D6**: `run_full_pipeline` — backup at :1309, `finally` restore at :1456-1460, backup
  unlink on success at :1427-1428 (F-11/F-12); `run_compile` mirrors it (:586-605, #178).
  `run_song_build` remains the outlier (PIPE-2026-08-21-4).
- **D7**: Fallback samples uniformly via `sample_events_for_detection` (F-04); warning
  text says analysis-only (#176) and the lossy coverage suffix covers the
  fallback-sampled case (#378); `run_detect_patterns` samples symmetrically (F-09/#21);
  both caps + the advisory threshold resolve through `get_pattern_detection_caps`
  (#219/#334) on both paths; the parallel→sequential fallback is a broad
  `except Exception` (:1139) around construction+detection.
- **D8**: JUKEBOX gate is `song_count is not None` in both `prepare_project` (:311) and
  `_generate_main_asm` (:354) (8ea7ac3); `_build_song_bytecode` re-declares
  `.segment "CODE_8000"` before each song's tables (:1330); a **live 1-song
  `song build --arranger` run compiled, linked, and validated** on this tree (the legacy-
  mode equivalent is blocked by PIPE-2026-08-21-1's false rejection, not by the jukebox
  machinery). Bank-pool chaining (`start_bank=next_bank`) is intact, and the combined
  capacity pre-flight (`main.py:1007` + `nes/project_builder.py:239`) catches both
  per-region overflows and any `BANK_60+` segment via
  `MMC3Mapper.validate_segment_sizes`'s `max_bank` check — an N-song overrun cannot reach
  ld65 raw. `_song_has_dpcm_events` inspects the real exported frames and both front-ends
  emit `{note, volume}` dpcm frames, so the gate mechanism is sound (its false positives
  are PIPE-2026-08-21-1). `midi_path` is stored absolute; missing/moved paths exit 1
  before any build artifact exists.

## Next Step

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-08-21.md
```
