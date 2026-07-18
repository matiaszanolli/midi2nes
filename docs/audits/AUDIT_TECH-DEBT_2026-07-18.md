# Tech-Debt Audit — MIDI2NES — 2026-07-18

Audit: `/audit-tech-debt` (all 8 dimensions, whole repo).
Scope: maintainability debt — duplication, dead code, stale docs, stale markers, stubs,
magic numbers, error-handling debt, module/function size. Correctness is owned by the
subsystem audits and is only flagged here when debt actively hides a bug.

Dedup baseline: `/tmp/audit/issues.json` (27 open issues, re-fetched this cycle) plus every
prior report in `docs/audits/`, most directly `docs/audits/AUDIT_TECH-DEBT_2026-07-06.md`
(this is a delta/re-verify pass against it). Concurrent audits running in this same suite
today (`AUDIT_EXPORTERS_2026-07-18.md`, `AUDIT_DPCM_2026-07-18.md`) independently found the
same dead code in `nes/project_builder.py` — see Cross-Reference note below; not re-derived
here.

## Prompt-injection watch

Watched tool output (gh issue titles/bodies, doc contents, source comments) for any embedded
instruction attempting to steer this audit. **None encountered.**

## Summary

| Dimension | New Findings |
|-----------|--------------|
| 1. Logic Duplication | 1 re-surfaced (TD-23 — velocity→volume power-curve duplication; still unfixed, never filed as a GH issue) |
| 2. Dead Code & Cruft | 1 new (TD-24 — two genuinely-dead local variables in `dpcm_sampler/enhanced_drum_mapper.py`) + 1 new micro-finding (TD-25 — shadowed `tempfile` re-import in `benchmarks/performance_suite.py`) |
| 3. Stale Documentation & Comments | 0 new (TD-22/#266 still open, unchanged; TD-13/#224 still open, drift widened — see notes) |
| 4. Stale Markers (TODO/FIXME) | 0 (unchanged — still the single tracked TD-08/#137 marker) |
| 5. Stub & Placeholder | 0 new (no new live-path stub) |
| 6. Magic Numbers | 0 new standalone |
| 7. Error-Handling Debt | 0 new (`debug/rom_tester.py:71` bare `except:` re-confirmed as Existing #223; `utils/profiling.py:120` re-confirmed as Existing #135) |
| 8. Module / Function Size | 0 new; TD-11/#136 monoliths **grew again** — see Verification Notes |

**Severity totals (new findings):** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 3 (TD-23 resurfaced,
TD-24, TD-25).
**Existing (verified, not regressed):** TD-03/#131, TD-07/#134, TD-08/#137, TD-10/#135,
SAFE-12/#223, TD-11/#136, TD-13/#224, TD-22/#266, EXP-09/#302 (dead `CompressionEngine`).

### Three highest-leverage cleanups
1. **File TD-23 as a GitHub issue.** It was written up in `AUDIT_TECH-DEBT_2026-07-06.md` but
   never published — `grep -i "velocity_to_volume\|power curve" /tmp/audit/issues.json` finds
   nothing. The duplication (and the linear-vs-power inconsistency with the arranger) is
   unchanged twelve days later. Re-including it here so `/audit-publish` picks it up.
2. **Update #136 (TD-11) with the new monolith line counts** — `main.py` is now 1513 lines
   (was 1480) and `run_full_pipeline` is now `main.py:769-1109` (~340 lines, was ~332);
   `exporter/exporter_ca65.py` is now 1318 lines (was 1287) though `export_direct_frames`
   itself is unchanged at `187-925` (~738 lines) — the file's growth is elsewhere.
3. **Small dead-code sweep**: `dpcm_sampler/enhanced_drum_mapper.py`'s two dead locals
   (TD-24) and the harmless `tempfile` shadow-import in `benchmarks/performance_suite.py`
   (TD-25) are both mechanical one-line deletions — the kind of debt that costs nothing to
   fix once noticed.

---

## Findings

### TD-23: Velocity→4-bit-volume power curve is still copy-pasted across 4 production sites (never filed)
- **Severity**: LOW
- **Dimension**: 1 — Logic Duplication (with a Dimension 6 magic-number component)
- **Location**: `nes/emulator_core.py:113` (pulse branch), `nes/emulator_core.py:119`
  (non-pulse branch), `nes/emulator_core.py:168` (noise), `nes/envelope_processor.py:119`
  (`get_envelope_control_byte` base-velocity path). Divergent sibling formula:
  `arranger/voice_allocator.py:430,438` (`max(1, vel // 8)`) and `arranger/voice_allocator.py:453`
  (bare `vel // 8`, no floor at all — noise channel).
- **Status**: NEW (re-surfacing a finding first written up in
  `docs/audits/AUDIT_TECH-DEBT_2026-07-06.md` as TD-23 — that report's finding was never
  turned into a GitHub issue: `grep -i "velocity_to_volume\|power curve" /tmp/audit/issues.json`
  returns nothing, and no subsequent audit report (`docs/audits/*2026-07-1[7-8]*.md`) mentions
  it either. Re-verified line-for-line against current source; the code is unchanged since
  2026-07-06 except that the arranger has grown a *third* linear-formula call site.)
- **Description**: The MIDI-velocity → NES-4-bit-volume conversion
  `max(1, int(15 * math.pow(velocity / 127.0, 1.5)))` is hand-written verbatim at four
  production sites across `nes/emulator_core.py` and `nes/envelope_processor.py`, with the
  magic constants `15` (max APU volume), `127.0` (max MIDI velocity), and `1.5` (the
  perceptual-loudness exponent) inlined at every site. `grep -rnE "def .*volume|def .*velocity"
  nes/ arranger/ exporter/ core/` finds no `velocity_to_volume`-style helper — there is still
  no shared implementation. The `--arranger` front-end computes the same conversion with a
  *different*, linear formula (`arranger/voice_allocator.py:430,438,453`), so the two
  front-ends produce different volumes for identical velocity input. The three clamped power-
  curve copies (`emulator_core.py:117-121`, `:167-168`, `envelope_processor.py:117-121`) guard
  with `v_clamped = min(127, max(0, velocity))`, but the pulse copy at `emulator_core.py:113`
  still uses the raw, unclamped `velocity` with no `>0` guard — harmless for spec-valid MIDI
  (0-127 maps to 1-15) but a defense-in-depth gap the other three copies close.
- **Evidence**: `grep -rn "math.pow" --include='*.py' . | grep -v /tests/` →
  `nes/emulator_core.py:113,119,168`, `nes/envelope_processor.py:119` (four identical prod
  expressions, confirmed unchanged). `arranger/voice_allocator.py:430`: `"volume": max(1, vel
  // 8),  # Scale to 1-15` (comment added since 2026-07-06, referencing #268/NH-30). Line 453
  (noise channel, new site since 2026-07-06): `"volume": vel // 8,` — no `max(1, ...)` floor
  at all, unlike its two pulse siblings four lines above.
- **Impact**: LOW — no ROM/runtime break; power-curve outputs stay in the 1-15 APU range for
  valid input. It is a hardware-tuning knob (the exponent shapes perceived loudness) that must
  be replicated across 4 prod + 7 test sites without missing one if it ever changes, while the
  arranger silently keeps a *third*, different, and now partially unguarded (line 453) curve.
- **Related**: Same finding as `AUDIT_TECH-DEBT_2026-07-06.md` TD-23 (content unchanged, never
  published); `AUDIT_NES_HARDWARE_2026-06-28.md`/`-06-29.md` (noted the linear-vs-power curve
  inconsistency as harmless); Existing #89 (ARR-06, sibling `CPU_CLOCK`/pitch duplication
  between arranger and `nes/pitch_table.py` — same "arranger re-derives a core conversion
  instead of sharing it" theme). The new unguarded `vel // 8` at `voice_allocator.py:453` is a
  correctness nuance for a NES-hardware audit to weigh in on (whether noise volume 0 is ever
  reached with an active period write); not re-derived here since Dimension scope is
  duplication, not per-channel correctness.
- **Suggested Fix**: Add one `velocity_to_volume(velocity, *, clamp=True)` helper (e.g. in
  `nes/envelope_processor.py` or a small `nes/volume.py`) that owns the `15`/`127.0`/`1.5`
  constants and the clamp, have all four `nes/` sites call it, and have the tests import the
  same helper. Decide deliberately whether the arranger should adopt the power curve or keep
  the linear one, and document the choice at all three arranger call sites (including the
  now-unguarded noise one) if they must differ.

---

### TD-24: Two dead local variables in `dpcm_sampler/enhanced_drum_mapper.py`
- **Severity**: LOW
- **Dimension**: 2 — Dead Code & Cruft
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:247` (`pattern_instances =
  defaultdict(list)`) and `:359` (`velocity_ratio = velocity / template_vel`)
- **Status**: NEW
- **Description**: `python -m pyflakes` over all git-tracked non-test `*.py` reports two
  "local variable ... assigned to but never used" hits in this file that were not present at
  the 2026-07-06 audit (that pass confirmed 0 `imported but unused`, a narrower check that
  does not catch dead locals). `pattern_instances` (line 247, inside the pattern-aware
  DPCM/noise conversion method) is assigned a fresh `defaultdict(list)` intended to "track
  pattern instances for optimization" per its comment, but is never appended to, read, or
  returned anywhere in the method — confirmed via `grep -n "pattern_instances"
  dpcm_sampler/enhanced_drum_mapper.py`, which returns only the one assignment line.
  `velocity_ratio` (line 359, inside the pattern-based note-conversion helper) computes
  `velocity / template_vel` "as a reference" per its comment, but the very next lines resolve
  the sample purely from `template_note` and the raw `velocity` — `velocity_ratio` is never
  referenced again (`grep -n "velocity_ratio"` → one hit, the assignment itself).
- **Evidence**: `python -m pyflakes dpcm_sampler/enhanced_drum_mapper.py` →
  `247:9: local variable 'pattern_instances' is assigned to but never used`,
  `359:9: local variable 'velocity_ratio' is assigned to but never used`.
- **Impact**: LOW — no behavioral effect; both are inert locals in the DPCM drum-pattern
  conversion path (`convert_drum_track` / its pattern-based note helper), not consumed
  downstream. Reads as leftover scaffolding from an optimization that was never finished
  (the comments describe *intent* — "for optimization", "as a reference" — that the code
  doesn't act on), which is exactly the kind of half-finished logic that misleads a future
  reader into thinking pattern-instance tracking or velocity-ratio scaling is live.
- **Related**: Distinct from EXP-12/DP-06 (the `nes/project_builder.py` dead macro-instrument
  code both concurrent audits already found today) — different file, different subsystem
  (DPCM sample conversion vs. builder-side asm scaffolding).
- **Suggested Fix**: Delete both dead assignments. If pattern-instance tracking or
  velocity-ratio-scaled sample selection was intended functionality, either finish it (wire
  `pattern_instances` into the pattern-reuse decision the surrounding comment describes) or
  remove the now-stale comments along with the dead code.

---

### TD-25: Shadowed re-import of `tempfile` in `benchmarks/performance_suite.py`
- **Severity**: LOW
- **Dimension**: 2 — Dead Code & Cruft (module-level lint hygiene)
- **Location**: `benchmarks/performance_suite.py:11` (module-level `import tempfile`) and
  `:472` (`import tempfile` again, inside the `if __name__ == "__main__":` block)
- **Status**: NEW
- **Description**: `tempfile` is imported once at module scope (line 11) and used correctly
  at lines 184 and 236. A second, redundant `import tempfile` appears inside the
  `__main__` guard at line 472, which `pyflakes` flags as "redefinition of unused 'tempfile'
  from line 11". This is a regression of the class of issue TD-20/#231 swept in the
  2026-07-05/06 cycle (`python -m pyflakes` over tracked non-test `*.py` reported 0
  `imported but unused` as of 2026-07-06); this specific "redefinition" variant slipped back
  in since then in this file.
- **Evidence**: `python -m pyflakes benchmarks/performance_suite.py` →
  `472:5: redefinition of unused 'tempfile' from line 11`.
- **Impact**: LOW — purely cosmetic; Python re-binding the same module name is a no-op at
  runtime, and this code path only runs when the file is executed directly
  (`python benchmarks/performance_suite.py`), not via the pipeline or test suite.
- **Related**: TD-20/#231 (the original repo-wide unused-import sweep) — same lint class,
  new site, not worth a fresh issue on its own given the trivial fix; bundle with TD-24 if a
  cleanup PR is filed.
- **Suggested Fix**: Delete the redundant `import tempfile` at line 472; the module-level
  import at line 11 already covers the `__main__` block.

---

## Verification Notes (SKILL-named + prior-report items re-checked)

- **Dimension 1 (Logic Duplication)**: `_find_pattern_matches` copy-paste (TD-03/#131) still
  gone — `tracker/pattern_detector_parallel.py` uses `_collect_length_candidates`; both
  detectors still share `score_pattern` from `tracker/pattern_detector.py`. The note→name
  converter (TD-07/#134) is still single-sourced in
  `exporter/exporter_famistudio.py:midi_note_to_famistudio` (line 164);
  `exporter/exporter_ca65.py` still has only the unrelated `midi_note_to_timer_value`
  (line 42) — no second copy. TD-23 (velocity/volume power curve) is unchanged and
  re-included above since it was never filed.
- **Dimension 2 (Dead Code & Cruft)**: Repo root still holds only `main.py`, `constants.py`,
  `validate_rom.py` at the top level (git-tracked) — the various `*.nes`/`*.s`/`*.log` files
  observed on disk (`NBA.nes`, `poly*.nes`, `output*.nes`, `nba_music.s`, `rebuild.log`,
  `sultans.log`, etc.) are all confirmed **gitignored, untracked local build artifacts**
  (`git status --ignored` shows them as `!!`), matching `.gitignore`'s `/*.nes`/`/*.s`/`/*.log`
  rules — not repo cruft, no regression of TD-04/TD-05 (#132/#133, closed). `EXP-09`/#302
  (`exporter/compression.py`'s `CompressionEngine` and `exporter/base_exporter.py`'s
  `compress_channel_data`/`decompress_channel_data`) re-confirmed still dead:
  `grep -rn "CompressionEngine|compress_channel_data|decompress_channel_data"` outside
  `tests/` finds only the definitions and `base_exporter.py`'s own unused instantiation — no
  caller. Still Existing #302 (open), not re-reported. `python -m pyflakes` over all
  git-tracked non-test `*.py` still reports **0** `imported but unused` (TD-20/#231 sweep
  holds) — the two new findings above (TD-24, TD-25) are a different pyflakes class (unused
  local / redefinition), not a regression of TD-20.
- **Dimension 3 (Stale Documentation)**: `docs/WORK_PLAN_1.0.0.md` carries an explicit
  "Archived — historical snapshot" banner referencing #226/TD-17 — confirmed fixed, not
  re-reported. **TD-22/#266 still open and unchanged**: `docs/IMMEDIATE_ACTIONS.md`,
  `docs/COVERAGE_REPORT.md`, `docs/TEST_COVERAGE_IMPROVEMENTS.md` still carry zero
  superseded/archived/historical markers and still assert stale v0.4.0-era test counts (186,
  568→582) as current. **TD-13/#224 still open, drift wider than last cycle**:
  `MEMORY.md:11` still reads "586 tests across 45 files"; live count is now **1007 tests
  across 52 files** (`pytest --collect-only -q` → 1007 collected; `ls tests/test_*.py | wc -l`
  → 52) — up from 986/52 at the 2026-07-06 audit (tests keep growing while the MEMORY.md
  figure is frozen). `docs/ROADMAP.md` and `README.md` version badges (`v0.5.0-dev`) match
  `midi2nes/__version__.py` (`__version__ = "0.5.0-dev"`) — no new drift there. `main.py`'s
  subcommand set (`parse`, `map`, `frames`, `detect-patterns`, `export`, `prepare`, `compile`,
  `config`, `song`, `benchmark`) matches CLAUDE.md's documented command list exactly.
- **Dimension 4 (Stale Markers)**: `grep -rnE 'TODO|FIXME|HACK|XXX' --include='*.py' .` outside
  `tests/` returns exactly **one** hit — the DPCM `.incbin` TODO, still at
  `exporter/exporter_ca65.py:988` (unchanged line number since 2026-07-06). Still Existing
  #137 (TD-08); still the sole marker in production code.
- **Dimension 5 (Stub & Placeholder)**: `exporter/exporter_nsf.py:75-80`'s
  `NotImplementedError` still self-documents #81 (both `export()` overload sites). No new
  live-path stub found; `nes/song_bank.py`'s multi-song placeholders remain an honest,
  ROADMAP-documented gap (not doc-rot — `docs/ROADMAP.md`'s "Song banks → ROM" section
  accurately describes `prepare_multi_song_project`/`add_song_bank` as placeholders).
- **Dimension 6 (Magic Numbers)**: `MIN_ROM_SIZE = 32768` (`compiler/compiler.py`) and
  `LARGE_FILE_THRESHOLD` (`main.py`) remain named constants. `CPU_CLOCK = 1789773`
  duplication in `arranger/pipeline_integration.py` vs `nes/pitch_table.py` unchanged —
  Existing #89 (ARR-06). No new standalone magic-number finding beyond the 15/127.0/1.5
  triad folded into TD-23.
- **Dimension 7 (Error-Handling Debt)**: `utils/profiling.py:120`'s bare `except:` unchanged
  — Existing #135 (TD-10). `debug/rom_tester.py:71`'s bare `except:` (cosmetic ROM-header
  check, benign) is Existing #223 (SAFE-12), which already covers this exact site plus
  `benchmarks/performance_suite.py:103` — re-confirmed both sites unchanged, not re-reported.
- **Dimension 8 (Module/Function Size) — both tracked monoliths grew again**: `main.py` is
  now **1513** lines (was 1480 at 2026-07-06; +33). `run_full_pipeline` now spans
  `main.py:769-1109` (~340 lines, was ~332). `exporter/exporter_ca65.py` is now **1318**
  lines (was 1287; +31), though `export_direct_frames` itself is unchanged at
  `187-925` (~738 lines) — the file's growth this cycle is elsewhere (between
  `export_direct_frames` and `export_tables_with_patterns`, e.g. `_compress_macro` and
  supporting bytecode helpers). This is continued growth on **Existing #136 (TD-11)** —
  recommend updating #136 with the new figures rather than filing a duplicate. Recommended
  splits unchanged from the 2026-07-06 report.

---

## Cross-Reference: EXP-12 / DP-06 (not re-derived here)

Per task instruction, the dead `seq_cmd_instrument`/`seq_cmd_dpcm_play` macro-instrument and
DPCM-trigger code in `nes/project_builder.py` (unconditionally appended into every
bytecode-mode `music.asm`, never called by `nes/audio_engine.asm` — confirmed via
`grep -rn "seq_cmd_instrument\|seq_cmd_dpcm_play"` finding only the definitions/`.global`
declarations) was independently found today by both `AUDIT_EXPORTERS_2026-07-18.md` (EXP-12)
and `AUDIT_DPCM_2026-07-18.md` (DP-06). This audit's independent read of
`nes/project_builder.py:141-167,241-245` confirms the same conclusion — corroborating, not a
fresh finding here.

---

## Dedup notes

- `/tmp/audit/issues.json` re-fetched this cycle: **27 open issues** (down from 30 at
  2026-07-06 — several tech-debt/safety items appear to have closed between cycles;
  `gh issue list` defaults to open-only, consistent with prior audit runs).
- TD-23 was checked against all 27 open issue titles/bodies (`grep -i "velocity\|volume
  curve\|power curve"` → no hits) and every file under `docs/audits/` dated after
  2026-07-06 (`grep -l` → no hits) before being re-included as a still-unfiled finding.
- TD-24 and TD-25 are both genuinely new `pyflakes` output not present at the 2026-07-06
  baseline (which explicitly reported 0 `imported but unused` — a narrower check); checked
  against `/tmp/audit/issues.json` (`grep -i "pattern_instances\|velocity_ratio\|tempfile\|
  redefinition\|unused local"` → no hits) and `docs/audits/*.md` (no mentions) — both NEW.
- No finding here overlaps the open correctness issues (#301, #300, #269, #256, #204, #203,
  #202, #167, #115, #112, #107, #91, #88, #76); this report is maintainability-only,
  consistent with the tech-debt skill's scope boundary.

---

Suggest:
```
/audit-publish docs/audits/AUDIT_TECH-DEBT_2026-07-18.md
```
