# Pipeline Integrity Audit — MIDI2NES

**Date:** 2026-06-28
**Scope:** End-to-end conversion chain as a contract-bound system (parse → map/arrange → frames → detect-patterns → export → prepare → compile → validate), all 8 dimensions of `audit-pipeline/SKILL.md`.
**Dedup source:** `gh issue list` succeeded — only 2 open issues exist (#2 "how to use", #3 "Output seems silent"), neither related. `docs/audits/` was empty. **All findings are NEW.**

---

## 1. Summary

**Does the step-by-step path produce the same ROM as the default `run_full_pipeline` path?**
**NO.** Three independent divergences guarantee a different `music.asm` (and therefore a different ROM) between `python main.py song.mid out.nes` and the manual `parse → map → frames → detect-patterns → export → prepare → build.sh` chain:

1. The default path detects patterns with `ParallelPatternDetector(max_pattern_length=12)`; `run_detect_patterns` uses `EnhancedPatternDetector` with **no** `max_pattern_length` (F-08).
2. The default path silently falls back to **truncating events to 2000** on parallel failure; the step-by-step `detect-patterns` never truncates (F-04, F-09).
3. Pattern detection has **no effect on emitted bytes anyway** because `export_tables_with_patterns` ignores its `references` argument and uses `patterns` only as a yes/no switch between two unrelated exporters (F-01) — so the two paths differ chiefly by *which exporter runs* (`patterns` non-empty → macro-bytecode path; empty → `export_direct_frames`), and the step-by-step `export` with no `--patterns` always takes the direct path.

**Single most dangerous finding:** **F-02 (CRITICAL)** — the ROM-validation gate only blocks on `overall_health == "ERROR"`, which `rom_diagnostics.py` returns *exclusively* when the ROM file is unreadable. A ROM with **invalid reset vectors at $FFFA–$FFFF** is classified FAIR/POOR and shipped as `✅ SUCCESS`. The one check that exists to catch an unbootable ROM cannot catch the canonical unbootable ROM.

### Findings per dimension

| Dim | Area | Findings |
|-----|------|----------|
| 1 | Stage JSON contract integrity | F-01 (HIGH), F-07 (LOW) |
| 2 | full-pipeline vs step-by-step parity | F-08 (MEDIUM), F-06 (MEDIUM) |
| 3 | Flag routing | F-03 (CRITICAL), F-05 (MEDIUM) |
| 4 | Error propagation / fail-fast | F-02 (CRITICAL) |
| 5 | Temp-file / intermediate handling | F-10 (MEDIUM) |
| 6 | Backup & overwrite safety | F-11 (MEDIUM), F-12 (LOW) |
| 7 | Large-file threshold & fallback | F-04 (CRITICAL), F-09 (MEDIUM) |
| 8 | Song-bank path | F-13 (MEDIUM), F-14 (LOW) |

**Counts:** CRITICAL 3 · HIGH 1 · MEDIUM 6 · LOW 4 · **Total 14**

---

## 2. Contract Map

| # | Boundary | Producer → key(s) → Consumer | Verified matching |
|---|----------|------------------------------|:--:|
| 1 | parse → map | `parser_fast.parse_midi_to_frames` → `{"events","metadata"}` → `run_map` reads `midi_data["events"]` | ✓ key matches; ✗ no guard if `events` missing (bare `KeyError`) |
| 2 | map → frames | `assign_tracks_to_nes_channels(events, dpcm_index_path)` → mapped dict → `NESEmulatorCore.process_all_tracks` | ✓ |
| 3 | frames → detect-patterns | `process_all_tracks` → `{channel:{frame:{note,volume,...}}}` → flattened to events list | ✓ |
| 4 | detect-patterns → export | detector → `{patterns,references,stats,variations}`; `run_detect_patterns` drops `variations`; `run_export` reads `patterns`,`references` | ✗ **`references` consumed differently than produced — and then ignored entirely (F-01)** |
| 5 | export → prepare | `CA65Exporter.export_tables_with_patterns(frames,patterns,references,out)` → `music.asm` → `NESProjectBuilder.prepare_project` | ✓ (file-level), but `references` arg is dead (F-01) |
| 6 | prepare → compile | `prepare_project` → project dir → `compile_rom(project_dir, output_rom)` → bool | ✓ |
| 7 | compile → validate | `compile_rom` → `.nes` → `ROMDiagnostics.diagnose_rom` → `overall_health` | ✗ **gate ineffective for bad vectors (F-02)** |
| 8 | stats banner | detector `stats['compression_ratio']` (a percentage) → printed as `…x` | ✗ unit mismatch (F-07) |
| 9 | song add | `SongBank.add_song_from_midi` → `tracker.parser.parse_midi_to_frames` (**old** parser, not `parser_fast`) | ✗ third parser, drifts from pipeline (F-14) |

---

## 3. Findings

### F-01: `export_tables_with_patterns` ignores its `references` argument and uses `patterns` only as a boolean switch
- **Severity**: HIGH
- **Dimension**: 1 (Stage JSON contract integrity)
- **Location**: `exporter/exporter_ca65.py:646-895`; producers `main.py:352-370` and `main.py:88-102`
- **Status**: NEW
- **Description**: The SKILL flags a "references-format gap": `run_full_pipeline` converts references to `{frame_str:(pattern_id,offset)}` (`main.py:352-361`) while `run_export` passes the detector's raw `{pattern_id:[positions]}` straight through (`main.py:90`). Re-reading the consumer shows the gap is moot in a worse way: `export_tables_with_patterns` **never reads `references` at all**, and reads `patterns` only at line 652 (`if not patterns: return self.export_direct_frames(...)`). All emitted bytes are re-derived from `frames` (lines 746-895). The entire `ca65_references` block in `main.py:352-361` is dead computation, and the documented contract ("export reads `pattern_data['patterns']` and `['references']`") is a fiction — pattern *compression* has no effect on output bytes; `patterns` truthiness only selects between two completely different exporters (`export_direct_frames` vs the MMC3 macro-bytecode path).
- **Evidence**: `grep -n "\breferences\b\|\bpatterns\b" exporter/exporter_ca65.py` returns only the signature (646), the docstring (649), and the gate (652). No other use in the 250-line function body.
- **Impact**: (a) The "95.86x pattern compression" headline is not reflected in the exporter — `patterns` non-empty merely routes to a different, unrelated serializer. (b) The default and step-by-step paths emit *different ROMs* not because of compression but because step-by-step `export` (no `--patterns`) hits `export_direct_frames` while the default path hits the macro path. (c) Any future fix to the references format is wasted until the exporter actually consumes references.
- **Related**: F-06, F-07, F-08
- **Suggested Fix**: Either make `export_tables_with_patterns` actually consume `references`/`patterns` to emit compressed sequence data, or delete the `references` parameter and the dead `ca65_references` build, and document that "compression" is analysis-only. Until then, unify the default and step-by-step export so both reach the same exporter for the same input.
- **Both paths?**: Both (the divergence between them is part of the finding).

---

### F-02: ROM-validation gate only blocks on "ERROR", which is unreachable for a bad-vector ROM — unbootable ROMs ship as SUCCESS
- **Severity**: CRITICAL
- **Dimension**: 4 (Error propagation / fail-fast)
- **Location**: `main.py:453,459-468`; `debug/rom_diagnostics.py:135-162,184-207`
- **Status**: NEW
- **Description**: `run_full_pipeline` exits non-zero only when `rom_result.overall_health == "ERROR"` (`main.py:459`). In `rom_diagnostics.py`, `overall_health` is set to `"ERROR"` **only** by `_create_error_result` (line 204), which fires solely when the ROM bytes cannot be read/parsed (`except` at line 184). A successfully-linked ROM with **invalid reset vectors** records `"Invalid reset vectors"` as a single issue (line 135-136); with ≤2 such issues it lands "GOOD", ≤3 "FAIR", else "POOR" (lines 157-162) — none of which is "ERROR". Per `_audit-severity.md`, "Bad reset/NMI/IRQ vector … in generated ROM" is a CRITICAL floor, and "No APU initialization code found" (line 139-140) likewise only adds an issue, never ERROR.
- **Evidence**: Only ERROR-producing call site is `_create_error_result` (`grep -n 'ERROR' rom_diagnostics.py` → 162 is "POOR", 204 is the only `overall_health="ERROR"`). `main.py:453` even passes HEALTHY/GOOD silently and only *warns* on FAIR/POOR (`main.py:454-457`), then proceeds to the `✅ SUCCESS!` banner (`main.py:482`).
- **Impact**: The pipeline's sole hardware-safety gate cannot catch the exact failure class it claims to ("Verify a POOR ROM that crashes on hardware is not shipped as success"). A ROM with bad `$FFFA-$FFFF` vectors or missing APU init is reported `✅ SUCCESS! ROM created`, and on real hardware/accurate emulators it crashes the CPU. Blast radius: every generated ROM whose linker mislays vectors.
- **Related**: F-11
- **Suggested Fix**: Treat `not reset_vectors_valid` and `apu_count == 0` as hard-fail conditions (force `overall_health = "ERROR"`, or add an explicit `if not rom_result.reset_vectors_valid: sys.exit(1)` after diagnosis). Reserve "ERROR" for unreadable files but add a separate fatal check for vector/APU validity.
- **Both paths?**: Default path only (step-by-step has no validation stage at all — see F-06).

---

### F-03: Unknown/typo flags on the default path are silently swallowed → wrong ROM (silent song change)
- **Severity**: CRITICAL
- **Dimension**: 3 (Flag routing)
- **Location**: `main.py:664-666`
- **Status**: NEW
- **Description**: The hand-rolled default-path dispatcher whitelists six flags and then `elif arg.startswith('-'): i += 1  # Skip unknown options for now`. A user who types `--no-pattern` (missing `s`), `--arrange`, `--no-validation`, or `--skipvalidation` has the flag **silently discarded** and the pipeline runs in its default mode (patterns ON, legacy mapping, validation ON).
- **Evidence**: Live reproduction:
  ```
  $ python main.py --no-pattern bad.mid out.nes
  [ERROR] Input MIDI file not found: bad.mid   # flag swallowed; reached default path
  $ python main.py --arrange bad.mid out.nes
  [ERROR] Input MIDI file not found: bad.mid   # arranger NOT engaged
  ```
  Both reach the input-existence check, proving the unknown flag was dropped, not rejected.
- **Impact**: User intending `--no-patterns` (full-fidelity direct export) silently gets the pattern path (different exporter, F-01); user intending `--arranger` (polyphony via arpeggiation) silently gets legacy single-voice mapping — voices dropped, song plays differently. Per SKILL Dimension 3 / severity floor, a silently different song is CRITICAL. (Note: the same flags *on a subcommand* like `parse --no-patterns` correctly error via argparse — the bug is specific to the manual default-path loop.)
- **Related**: F-05, F-01
- **Suggested Fix**: In the manual loop, replace the silent `# Skip unknown options` branch with an error: print `Unknown option: {arg}` and `sys.exit(2)`. Better, route the default path through `argparse` with `parse_known_args` and reject leftovers.
- **Both paths?**: Default path only.

---

### F-04: Pattern-detector fallback truncates events to 2000 with no warning of incomplete output → silent song loss
- **Severity**: CRITICAL
- **Dimension**: 7 (Large-file threshold & fallback hand-off)
- **Location**: `main.py:319-327`
- **Status**: NEW
- **Description**: If `ParallelPatternDetector.detect_patterns(events)` raises, the `except Exception` fallback constructs `EnhancedPatternDetector` and, for `len(events) > 2000`, does `events = events[:2000]` (line 326) before detecting. The remaining frames are discarded. The exporter then renders only the surviving subset of `frames`... except it doesn't even read the truncated `events` (it reads `frames`, F-01) — so in the *default macro path* the truncation actually corrupts only `ca65_references` (which is itself dead). The real song-loss risk is that the truncation message ("Limiting to 2000 events for fallback performance") is a performance note, not a "your ROM is incomplete" warning, and a maintainer who later wires references→bytes (the intended design) ships only the first 2000 events.
- **Evidence**: `main.py:324-327`. The print at 325 frames it as a perf optimization; there is no "output will be incomplete" notice and the final `✅ SUCCESS` banner is unconditional.
- **Impact**: Data loss that changes the song the moment compression is made functional (F-01); today it silently corrupts the (dead) reference table. Reachability depends on `ParallelPatternDetector` raising — see F-09 for why the parallel path also silently *samples* large files. Either way, large MIDI files are at risk of producing a truncated ROM reported as success.
- **Related**: F-01, F-09
- **Suggested Fix**: Do not truncate silently. If the fallback cannot handle the event count, either keep all events (accept slowness) or abort with a clear "file too large for pattern detection; re-run with --no-patterns" error. If truncation is kept, print a prominent WARNING and reflect it in the success banner.
- **Both paths?**: Default path only (step-by-step `detect-patterns` has no truncation — see F-09).

---

### F-05: `map --config` / `--dpcm-index` are declared but ignored
- **Severity**: MEDIUM
- **Dimension**: 3 (Flag routing)
- **Location**: `main.py:40-44` (body) vs `main.py:519-520` (declared)
- **Status**: NEW
- **Description**: `p_map` declares `--config` and `--dpcm-index`, but `run_map` hardcodes `dpcm_index_path = 'dpcm_index.json'` and never reads `args.config` or `args.dpcm_index`. A user pointing `--dpcm-index custom.json` gets the default file silently.
- **Evidence**: `main.py:42` `dpcm_index_path = 'dpcm_index.json'`; no reference to `args.config`/`args.dpcm_index` in `run_map`.
- **Impact**: Misleading interface; a custom DPCM index is silently ignored, so drum mapping differs from what the user requested. Recoverable (user can edit the default file) → MEDIUM.
- **Related**: F-03
- **Suggested Fix**: Honor `args.dpcm_index or 'dpcm_index.json'` and pass `args.config` into the mapper, or drop the unused options.
- **Both paths?**: Step-by-step only (`run_full_pipeline` also hardcodes `'dpcm_index.json'` at `main.py:282`, so the default path has the same hardcode but no misleading flag).

---

### F-06: Step-by-step path has no prepare/compile/validate parity and `run_prepare` exits 0 on failure
- **Severity**: MEDIUM
- **Dimension**: 2 (parity) / 4 (fail-fast)
- **Location**: `main.py:55-63` (`run_prepare`); compile + validate exist only in `run_full_pipeline:432-477`
- **Status**: NEW
- **Description**: Two parity gaps. (a) `run_prepare` prints success **only inside** `if builder.prepare_project(...)`, with no `else`; `prepare_project` returns `True` on success (`nes/project_builder.py:500`) and raises on error (caught nowhere in `run_prepare`), so a path/permission failure raises an uncaught traceback rather than a clean exit — and a falsy-but-non-raising return would exit 0 silently. (b) There is no step-by-step `compile`/`validate` subcommand at all; the manual chain ends at `prepare` and the user runs `build.sh` by hand, so the validation gate (F-02) never runs on the step-by-step ROM.
- **Evidence**: `main.py:58` has no `else`; there is no `compile`/`validate` entry in the `subcommands` list (`main.py:608`).
- **Impact**: Step-by-step ROMs receive zero post-build validation; `prepare` failures are not surfaced as a clean non-zero exit with a message.
- **Related**: F-02, F-08
- **Suggested Fix**: Add an `else: sys.exit(1)` to `run_prepare`, wrap it in try/except, and add a `compile`/`validate` subcommand (or document that step-by-step intentionally stops at `prepare`).
- **Both paths?**: Step-by-step only.

---

### F-07: `compression_ratio` is a percentage but printed as `…x`
- **Severity**: LOW
- **Dimension**: 1 / 2 (stats contract)
- **Location**: `tracker/pattern_detector.py:746-754`; printed `main.py:157,484`
- **Status**: NEW
- **Description**: `calculate_compression_stats` computes `compression_ratio = ((original - compressed)/original) * 100` — a percentage reduction in [0,100]. The success banner prints `Compression ratio: {…:.2f}x` (`main.py:484`) and `run_detect_patterns` prints `{…:.2f}` (`main.py:157`). A 96% reduction is shown as "95.86x", which is the figure CLAUDE.md cites as a multiplier.
- **Evidence**: Formula at `pattern_detector.py:748`; `x` suffix at `main.py:484`.
- **Impact**: Cosmetic but misleading reporting; the documented "95.86x compression" is actually ~96% reduction (≈25x). Per severity table ("reported compression/stat inaccurate") this is MEDIUM-floor, but blast radius is display-only → LOW.
- **Related**: F-01
- **Suggested Fix**: Print `{ratio:.1f}%` reduction, or convert to a true multiplier `original/compressed` and label `x`.
- **Both paths?**: Both.

---

### F-08: Pattern-detector parameter divergence between default and step-by-step
- **Severity**: MEDIUM
- **Dimension**: 2 (parity)
- **Location**: `main.py:316,322` (default: `max_pattern_length=12`) vs `main.py:130` (`run_detect_patterns`: `min_pattern_length=3`, no `max_pattern_length`)
- **Status**: NEW
- **Description**: The default path runs `ParallelPatternDetector(..., max_pattern_length=12)` (and `EnhancedPatternDetector(..., max_pattern_length=12)` in fallback); `run_detect_patterns` runs `EnhancedPatternDetector(tempo_map, min_pattern_length=3)` with **no** `max_pattern_length`. Different detector classes and different length bounds produce different `patterns`/`references` for the same input.
- **Evidence**: `main.py:130` vs `316`/`322`.
- **Impact**: The step-by-step `detect-patterns` output differs from the default path's. Because the exporter ignores `references` and `patterns` truthiness rarely flips, the *byte* impact is small today, but the JSON artifacts genuinely diverge — anyone comparing or reusing them is misled, and if F-01 is fixed this becomes a playback divergence.
- **Related**: F-01, F-06
- **Suggested Fix**: Factor pattern-detection parameters into one shared constant/helper used by both entry points.
- **Both paths?**: Divergence between the two (the finding).

---

### F-09: Asymmetric large-file handling — default path samples/truncates, step-by-step processes the full set unbounded
- **Severity**: MEDIUM
- **Dimension**: 7
- **Location**: `tracker/pattern_detector_parallel.py:50-58` (samples to `MAX_EVENTS=15000`); `main.py:324-326` (fallback truncates to 2000); `run_detect_patterns` (`main.py:125-147`) has neither
- **Status**: NEW
- **Description**: The default path silently down-samples to 15000 events inside `ParallelPatternDetector` (`np.linspace` sampling, line 53-57) and truncates to 2000 in the fallback (F-04). `run_detect_patterns` uses `EnhancedPatternDetector` on the full event set with no threshold and no fallback. A large file that the default path "survives" via sampling may hang or OOM under the bare `detect-patterns` subcommand.
- **Evidence**: `pattern_detector_parallel.py:51` `MAX_EVENTS = 15000`; `main.py:130` constructs the detector with no size guard.
- **Impact**: Inconsistent robustness; the subcommand documented for "debugging" is the least robust on exactly the large inputs a user would debug. The silent sampling at 15000 is itself an undocumented lossy step (see F-04 rationale).
- **Related**: F-04
- **Suggested Fix**: Share one large-file policy across both entry points; make sampling/truncation explicit and warned, or honor `--no-patterns` semantics consistently.
- **Both paths?**: Divergence between the two.

---

### F-10: `export` appends DPCM block in `'a'` mode — re-running clobbers/doubles on a reused output
- **Severity**: MEDIUM
- **Dimension**: 5 (temp-file / intermediate handling)
- **Location**: `main.py:118-119` (`run_export`: `open(args.output, 'a')`); default path `main.py:403` (`open(music_asm, 'a')`)
- **Status**: NEW
- **Description**: `run_export` writes the CA65 tables (overwrite via `export_tables_with_patterns`) then **appends** the packed DPCM assembly with `open(args.output, 'a')`. The default path appends to the fresh temp `music.asm`, so it is safe (file is new each run). But in the step-by-step path `args.output` is a user file: the first `export` writes tables + appends DPCM; a *second* `export` to the same path overwrites the tables (good) but the DPCM append is fine only because the tables write truncates first — however if a user has hand-edited or concatenated content, the append lands after whatever `export_tables_with_patterns` left. The real risk is appending DPCM to a file that already has a DPCM block from a prior tool step, producing duplicate `dpcm_*` symbols → assembler error.
- **Evidence**: `main.py:96-119`: `export_tables_with_patterns` writes the file, then `open(args.output, 'a')` appends. No check for an existing DPCM block.
- **Impact**: Step-by-step `export` re-runs onto a path that already contains a DPCM section yield duplicate-symbol assembly failures. Recoverable (delete and re-run) → MEDIUM.
- **Related**: —
- **Suggested Fix**: Have `export_tables_with_patterns` include the DPCM block itself (single write), or guard the append against an existing DPCM marker.
- **Both paths?**: Step-by-step (`run_export`) primarily; default path safe due to temp dir.

---

### F-11: Backup restore does not fire on prepare-failure or top-level exception exits
- **Severity**: MEDIUM
- **Dimension**: 6 (backup & overwrite safety)
- **Location**: `main.py:426-428` (prepare fail), `main.py:488-494` (top-level except); restore only at `main.py:436-438` (compile) and `463-466` (validation ERROR)
- **Status**: NEW
- **Description**: When `output_rom` pre-exists, the pipeline copies it to `.nes.backup` (`main.py:244-247`). Restore-on-failure runs only after a compile failure and after a validation ERROR. The **prepare-failure** exit (`main.py:426-428 sys.exit(1)`) and the **top-level `except` → sys.exit(1)** (`main.py:488-494`) do **not** restore the backup. In those two failure modes, however, the final ROM has not yet been overwritten (compile copies the new ROM only at the very end, `compiler/compiler.py:146`), so the user's original ROM is intact — the missing restore is a latent inconsistency rather than active data loss today. It becomes data loss if any future change writes `output_rom` before prepare/compile completes.
- **Evidence**: restore blocks exist only at 436 and 463; the exits at 428 and 494 have none.
- **Impact**: Inconsistent backup/restore contract; fragile against reordering. The backup is also never deleted on success (F-12).
- **Related**: F-02, F-12
- **Suggested Fix**: Move restore into a single `finally`/helper keyed on "did we overwrite the original and not succeed", covering every exit path after backup creation.
- **Both paths?**: Default path only.

---

### F-12: `.nes.backup` is never cleaned up on success
- **Severity**: LOW
- **Dimension**: 6
- **Location**: `main.py:244-247` (created); no deletion on success path (`main.py:479-486`)
- **Status**: NEW
- **Description**: On a successful re-run over an existing ROM, `.nes.backup` is left on disk indefinitely. Not harmful, but clutters and can mask which file is current.
- **Evidence**: No `backup_path.unlink()` anywhere after the success banner.
- **Impact**: Disk clutter; minor confusion. LOW.
- **Related**: F-11
- **Suggested Fix**: `backup_path.unlink(missing_ok=True)` after the success banner, or document the retention as intentional.
- **Both paths?**: Default path only.

---

### F-13: Song-bank path is disjoint from the pipeline — no `song → ROM` route
- **Severity**: MEDIUM
- **Dimension**: 8 (song-bank path)
- **Location**: `nes/song_bank.py` (methods: `add_song_from_midi`, `add_song`, `export_bank`, `import_bank`, `get_bank_data`, `get_bank_size` — no compile/build); `main.py:159-221`
- **Status**: NEW
- **Description**: `SongBank` exposes only JSON bank read/write and size estimation; there is no method that turns a bank into a `.nes`, and no pipeline entry consumes a bank. The `song` subcommands are a dead-end relative to ROM generation. `docs/ROADMAP.md`/`WORK_PLAN_1.0.0.md` make no multi-song-ROM promise (grep returned nothing), so this is a feature gap, not doc-rot.
- **Evidence**: `grep "def " nes/song_bank.py` shows no build/compile method; the main `subcommands` list and `run_full_pipeline` never reference a bank.
- **Impact**: Multi-song banks can be assembled and listed but never compiled into a ROM — the feature is half-wired. No active corruption → MEDIUM (contract gap).
- **Related**: F-14
- **Suggested Fix**: Either add a `song build <bank> <out.nes>` route through the project builder/compiler, or document the song bank as an analysis/storage feature only.
- **Both paths?**: Song-bank path only (disjoint).

---

### F-14: `SongBank.add_song_from_midi` uses the old full parser, not `parser_fast` — third parser drift
- **Severity**: LOW
- **Dimension**: 8
- **Location**: `nes/song_bank.py:7,61` (`from tracker.parser import parse_midi_to_frames`); pipeline uses `tracker.parser_fast` (`main.py:35,264`)
- **Status**: NEW
- **Description**: The song-bank ingestion parses MIDI with `tracker.parser.parse_midi_to_frames` (the older full parser), while every pipeline path uses `parser_fast`. The two parsers populate `metadata` differently (old parser fills per-track metadata, `parser.py:92-104`; fast parser returns `"metadata": {}`, `parser_fast.py:84`) and may differ in note/event handling. A song stored in a bank is therefore parsed by a different code path than the one that would render it.
- **Evidence**: `song_bank.py:7` import; `parser.py:102-104` vs `parser_fast.py:83-85` differing return shapes.
- **Impact**: If the song-bank path is ever wired to ROM output (F-13), notes/timing could differ from the main pipeline for the same MIDI. Today it only affects bank metadata. LOW (latent).
- **Related**: F-13
- **Suggested Fix**: Point `song_bank.py` at `parser_fast` (or have both parsers share a single front-end) so bank ingestion matches pipeline note handling.
- **Both paths?**: Song-bank path only.

---

## Disproved / non-findings (re-checked, not reported)

- **Backup suffix math on `my.song.nes`** — `Path('my.song.nes').with_suffix('.nes.backup')` → `my.song.nes.backup` (verified live). No clobber. Not a bug.
- **`--no-patterns`/`--skip-validation` on a subcommand** — argparse rejects with `unrecognized arguments` and exits non-zero (verified live). Silent-ignore concern from SKILL Dimension 3 does **not** reproduce on subcommands (only on the default path, F-03).
- **`prepare_project` returning `None`** — it returns `True` at `nes/project_builder.py:500`; the `if not builder.prepare_project(...)` check is valid.
- **`compile_rom` swallowing CC65 nonzero exit** — `cc65_wrapper.assemble`/`link` raise `CompilationError` on `returncode != 0` (lines 139-144, 194-199); `compile_rom` returns `False` on those, and `run_full_pipeline` exits on `not compile_rom(...)`. Error propagation here is correct.
- **`ca65_references` truncation correctness** — moot because the exporter ignores `references` (F-01); not separately reported.

---

## Next step

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-06-28.md
```
