# Tech-Debt Audit — MIDI2NES — 2026-07-06

Audit: `/audit-tech-debt` (all 8 dimensions, whole repo).
Scope: maintainability debt — duplication, dead code, stale docs, stale markers, stubs,
magic numbers, error-handling debt, module/function size. Correctness is owned by the
subsystem audits and is only flagged here when debt actively hides a bug.

Dedup baseline: `/tmp/audit/issues.json` (30 open issues, pre-fetched) plus every prior
report in `docs/audits/`, most directly `docs/audits/AUDIT_TECH-DEBT_2026-07-05.md`.
Per the task instruction, `gh issue list` was **not** re-run.

## Prompt-injection watch

Per protocol I watched for any embedded instruction in tool output attempting to steer
this audit. **None encountered.** The only markup anomaly on record is TD-19/#229 (leaked
tool-call tags in a *prior* report) — already tracked, inert, not re-litigated here.

## Summary

| Dimension | New Findings |
|-----------|--------------|
| 1. Logic Duplication | 1 (TD-23 — velocity→volume power-curve copy-pasted + inconsistent across 4 prod sites) |
| 2. Dead Code & Cruft | 0 (prior debt fixed/tracked — see Verification Notes) |
| 3. Stale Documentation & Comments | 0 new (MEMORY.md 586 still Existing #224; README/HISTORY now fixed) |
| 4. Stale Markers (TODO/FIXME) | 0 (unchanged — still the single tracked TD-08/#137 marker) |
| 5. Stub & Placeholder | 0 (no new live-path stub) |
| 6. Magic Numbers | 0 new standalone (the 15/127/1.5 constants folded into TD-23) |
| 7. Error-Handling Debt | 0 (unchanged — TD-10/#135 sites unmoved) |
| 8. Module / Function Size | 0 new; both TD-11/#136 monoliths **grew further** — see Verification Notes |

**Severity totals (new findings):** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 1.
**New:** 1. **Existing (verified, not regressed):** all SKILL-named items re-checked; two prior
LOW findings (TD-20 unused imports, TD-21 README 586 count) have since been **fixed**; the two
TD-11 monoliths grew again and should have #136 updated rather than a duplicate filed.

### Three highest-leverage cleanups
1. **TD-23 — Extract one `velocity_to_volume()` helper.** The 1.5-power velocity→4-bit-volume
   curve `max(1, int(15 * math.pow(v / 127.0, 1.5)))` is hand-inlined at four production sites
   in two files (plus seven test sites), and the arranger uses a *different* linear `max(1,
   vel // 8)` for the same conversion. One shared, documented helper removes the drift risk and
   the magic 15/127/1.5 constants in a single move.
2. **Update #136 (TD-11) with the new monolith line counts** — `run_full_pipeline`
   (`main.py:744-1076`, ~332 lines) and `export_direct_frames`
   (`exporter/exporter_ca65.py:187-925`, ~738 lines) both grew again; the tracked issue's
   figures are stale.
3. **Close the stale-open lint issues** — TD-20 (repo-wide unused imports) is now clean
   (`pyflakes` reports 0) and TD-21 (README/HISTORY "586 tests") is fixed; if their issues were
   filed they can be verified and closed.

---

## Findings

### TD-23: Velocity→4-bit-volume power curve is copy-pasted across 4 production sites (and inconsistent with the arranger's linear curve)
- **Severity**: LOW
- **Dimension**: 1 — Logic Duplication (with a Dimension 6 magic-number component)
- **Location**: `nes/emulator_core.py:113` (pulse branch), `nes/emulator_core.py:119`
  (non-pulse branch), `nes/emulator_core.py:168` (noise), `nes/envelope_processor.py:119`
  (`get_envelope_control_byte` base-velocity path). Divergent sibling formula:
  `arranger/voice_allocator.py:416` and `:424` (`max(1, vel // 8)`).
- **Status**: NEW
- **Description**: The MIDI-velocity → NES-4-bit-volume conversion
  `max(1, int(15 * math.pow(velocity / 127.0, 1.5)))` is hand-written verbatim at four
  production sites across `nes/emulator_core.py` and `nes/envelope_processor.py`, with the
  magic constants `15` (max APU volume), `127.0` (max MIDI velocity), and `1.5` (the
  perceptual-loudness exponent) inlined at every site. There is **no shared helper** —
  `grep -rnE "def .*volume|def .*velocity" nes/ arranger/ exporter/ core/` finds no
  `velocity_to_volume`-style function; each call re-derives the curve. Seven `tests/` sites
  (`test_core.py`, `test_envelope.py`, `test_audio_fixes.py`) re-implement the identical
  expression as their expected value, so changing the curve means editing **eleven** places.
  The copies have already drifted: the three sites at
  `emulator_core.py:117-121`/`:167-168`/`envelope_processor.py:117-121` guard with
  `v_clamped = min(127, max(0, velocity))` and a `velocity > 0` branch, but the pulse copy at
  `emulator_core.py:113` uses the raw, unclamped `velocity` with no `>0` guard — harmless for
  spec-valid MIDI (0–127 maps to 1–15) but a defense-in-depth gap the other copies close.
  Separately, the `--arranger` front-end computes the same conversion with a *different*
  formula — linear `max(1, vel // 8)` (`voice_allocator.py:416,424`) — so the two front-ends
  produce different volumes for the same velocity. Prior NES-hardware audits
  (`AUDIT_NES_HARDWARE_2026-06-28.md:235`) already noted this linear-vs-power inconsistency as
  "harmless," but it has never been filed as a duplication/consolidation item.
- **Evidence**: `grep -rn "math.pow" --include='*.py' . | grep -v /tests/` →
  `nes/emulator_core.py:113,119,168`, `nes/envelope_processor.py:119` (four identical prod
  expressions); the same string appears at 7 `tests/` sites. `voice_allocator.py:416,424`
  show the divergent `max(1, vel // 8)`.
- **Impact**: LOW — no ROM/runtime break; all outputs stay in the 1–15 APU range for valid
  input. But the curve is a hardware-tuning knob (the exponent shapes perceived loudness), and
  a future change to it must be replicated across 4 prod + 7 test sites without missing one,
  while the arranger silently keeps a second, different curve. This is exactly the "improve
  existing code, never duplicate" pattern the tech-debt skill targets.
- **Related**: `AUDIT_NES_HARDWARE_2026-06-28.md`/`-06-29.md` (noted the linear-vs-power curve
  inconsistency as harmless, not filed); Existing #89 (ARR-06, the sibling `CPU_CLOCK`/pitch
  duplication between arranger and `nes/pitch_table.py`) — same "arranger re-derives a core
  conversion instead of sharing it" theme.
- **Suggested Fix**: Add one `velocity_to_volume(velocity, *, clamp=True)` helper (e.g. in
  `nes/envelope_processor.py` or a small `nes/volume.py`) that owns the `15`/`127.0`/`1.5`
  constants and the clamp, have all four `nes/` sites call it, and have the tests import the
  same helper rather than re-hardcoding the expression. Decide deliberately whether the
  arranger should adopt the power curve or keep the linear one, and document the choice at the
  call site if they must differ.

---

## Verification Notes (SKILL-named + prior-report items re-checked)

Per the mandatory dedup process, every item the SKILL flagged as "already fixed/tracked,
verify before re-reporting," plus the three LOW findings from the 2026-07-05 report, was
re-checked against current source.

- **Dimension 1 (Logic Duplication)**: `_find_pattern_matches` copy-paste (TD-03/#131) still
  gone — `tracker/pattern_detector_parallel.py` uses `_collect_length_candidates`; both
  detectors share `score_pattern`. The note→name converter (TD-07/#134) is still single-sourced
  in `exporter/exporter_famistudio.py:midi_note_to_famistudio`; `exporter/exporter_ca65.py` has
  only the unrelated `midi_note_to_timer_value` (line 42). New duplication found is TD-23 above.
- **Dimension 2 (Dead Code & Cruft)**: Repo root still holds only `main.py`, `constants.py`,
  `validate_rom.py` — no new stray script or duplicate `check_rom.py`/`validate_rom.py`. The two
  dead items the 2026-07-05 report noted under Existing #165 (NH-23) are now **removed**:
  `NOISE_PERIODS` has zero non-test references (`grep -rn "NOISE_PERIODS" --include='*.py' .` →
  no hits) and the dead `is_midi_velocity` local is gone from `exporter/exporter_ca65.py`
  (`grep -n is_midi_velocity` → no hits). **TD-20 (repo-wide unused imports) is FIXED**:
  `python -m pyflakes` over all git-tracked non-test `*.py` reports **0** `imported but unused`
  (was 56 at the 2026-07-05 audit); the sweep landed. The only remaining pyflakes output is the
  cosmetic `f-string is missing placeholders` class (e.g. `main.py:360,821,856,1352,1404`) —
  literal strings with a stray `f` prefix, no dropped interpolation, harmless (as noted 07-05).
- **Dimension 3 (Stale Documentation)**: **TD-21 is FIXED** — `grep -n 586 README.md HISTORY.md`
  → no hits; the README badge/tagline/testing count no longer claims 586. `MEMORY.md:11` still
  reads "586 tests across 45 files" — that is **Existing #224 (TD-13)**, still open, live count
  now **986 tests across 52 files** (`pytest --collect-only -q` → 986; `ls tests/test_*.py` →
  52). Not re-reported. TD-22 (superseded v0.4.0 planning docs) is now filed as **#266**.
- **Dimension 4 (Stale Markers)**: `grep -rnE 'TODO|FIXME|HACK|XXX' --include='*.py'`
  (excluding tests) returns exactly **one** hit — the DPCM `.incbin` TODO, now at
  `exporter/exporter_ca65.py:988` (drifted from 928 as the file grew). Still Existing #137
  (TD-08); still the sole marker.
- **Dimension 5 (Stub & Placeholder)**: `exporter/exporter_nsf.py`'s `NotImplementedError`
  self-documents #81; `nes/project_builder.py`'s multi-song placeholders remain honest no-ops
  off the default path. No new live-path stub.
- **Dimension 6 (Magic Numbers)**: `MIN_ROM_SIZE = 32768` (`compiler/compiler.py`) and
  `LARGE_FILE_THRESHOLD` (`main.py`) remain named. `CPU_CLOCK = 1789773` duplication in
  `arranger/pipeline_integration.py` unchanged — Existing #89 (ARR-06). The bare 15/127/1.5
  velocity constants are folded into TD-23 rather than filed separately.
- **Dimension 7 (Error-Handling Debt)**: `utils/profiling.py` bare `except:` clauses remain at
  the tracked locations (Existing #135/TD-10, also #223/SAFE-12). Not re-reported.
- **Dimension 8 (Module/Function Size) — BOTH MONOLITHS GREW AGAIN**: `main.py` is now **1480**
  lines (was 1359 at the 2026-07-05 audit; +121). `run_full_pipeline` now spans
  `main.py:744-1076` (~332 lines, was ~313). `export_direct_frames` now spans
  `exporter/exporter_ca65.py:187-925` (~738 lines; next method `_compress_macro` at line 926);
  the file overall is **1287** lines (was 1232). This is growth on the exact monoliths tracked
  by **Existing #136 (TD-11)** — recommend updating #136 with the new figures rather than filing
  a duplicate. Recommended splits unchanged: `run_full_pipeline` → per-stage helpers
  (parse/map/frames/patterns/export/pack/prepare/compile); `export_direct_frames` → separate
  emitters for pitch tables vs. the four per-channel playback routines vs. data tables.

---

## Dedup notes

- The one new finding (TD-23) was checked against `/tmp/audit/issues.json` (30 open) and every
  file under `docs/audits/`. No open issue mentions velocity/volume-curve duplication
  (`grep -oiE "velocity|power curve|volume curve" /tmp/audit/issues.json` → no hits); prior
  NES-hardware audits discussed the curve's *correctness* and even named its inconsistency, but
  none filed it as a consolidation/duplication item.
- Two prior 2026-07-05 LOW findings are recorded here as **fixed** (TD-20 imports, TD-21 README
  586), not re-reported.
- No finding here overlaps the open correctness issues; this report is maintainability-only,
  consistent with the tech-debt skill's scope boundary.

---

Suggest:
```
/audit-publish docs/audits/AUDIT_TECH-DEBT_2026-07-06.md
```
