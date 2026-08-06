# DPCM / Drum-Sampling Audit — 2026-08-05

Scope: `dpcm_sampler/` plus the DMC-facing edges of the channel pipeline
(`tracker/track_mapper.py`, `nes/emulator_core.py`, `nes/audio_engine.asm`,
`exporter/exporter_ca65.py`, `main.py` pack call sites). Hardware claims
verified against `docs/APU_DMC_REFERENCE.md` and `docs/NES_DMA_REFERENCE.md`.

## 1. Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 0 |
| LOW      | 0 |
| **Total**| **0** |

New: 0 · Existing (already tracked, confirmed still valid): 13.

**No new findings this cycle.** `git log --since=2026-07-19 -- dpcm_sampler/
tracker/track_mapper.py nes/emulator_core.py nes/audio_engine.asm
exporter/exporter_ca65.py main.py nes/project_builder.py` shows the DPCM
subsystem's core logic (`dpcm_sampler/**`, `track_mapper.py`,
`emulator_core.py`, `audio_engine.asm`) has **not changed** since the
2026-07-19 DPCM audit. The three commits landed in the interim
(`36348ce` mapper auto-select/direct-DPCM marker #361-363, `7a2054d` triangle
control constant #364, `bc5467a` arranger noise strike-decay #359-360,
`398891f` pattern-selection gate #365) touch `exporter_ca65.py`, `main.py`,
`nes/project_builder.py`, and the arranger — none re-open or regress a DPCM
finding; `36348ce`'s direct-DPCM marker is additive (a `.asm` comment +
`resolve_mapper` guard) and doesn't touch any code path this audit's
dimensions cover.

Every issue this audit re-verified was re-confirmed present in the code
exactly as previously described, and all 13 remain **OPEN** on GitHub — none
have been silently fixed or silently regressed further. No workaround or
new edge case was found for any of them, and no dimension surfaced a
previously-unfiled problem.

Highest-risk items among the still-open set (unchanged ranking from the prior
report):
- **#367/DP-DPCM-05 (MEDIUM)** — a missing/corrupt `.dmc` file at pack time
  leaves its dense id's slot as a `$00` placeholder (or drops it from
  `max_id` entirely), and the frame that referenced it still encodes
  `note = dense_id + 1`; `@write_dpcm` then plays a 1-byte garbage fragment
  instead of the intended drum or a clean fallback.
- **#348/NH-HW-2026-07-18-1 (open, cross-filed under nes-hardware)** —
  direct-export `init_music` (`exporter/exporter_ca65.py:879-891`) still never
  writes `$00` to `$4011`, unlike the bytecode engine's `audio_init`
  (`nes/audio_engine.asm:132-135`), so a `--no-patterns` build can start with
  a nonzero DMC output level muffling Triangle/Noise via the mixer
  (`docs/APU_DMC_REFERENCE.md` §6).

## 2. Findings

No new findings. This audit re-verified every dimension and skeptical-checklist
item in the `audit-dpcm` skill against the current tree and found the code
unchanged from the 2026-07-19 audit. Per the deduplication protocol, all
re-confirmed issues are listed below as "Existing", not re-reported.

## 3. Re-verification detail (existing issues confirmed still valid)

### Dimension 1 — Drum-note → sample mapping & coverage
- **#340/DP-DPCM-01 (Existing, OPEN)** — `DEFAULT_MIDI_DRUM_MAPPING`
  (`dpcm_sampler/drum_engine.py:8-56`) still maps `splash`(55),
  `vibraslap`(58), `triangle_mute`(80), `triangle_open`(81) to role names with
  no catalog sample and no `DPCM_ROLE_ALIASES` entry (`drum_engine.py:63-73`);
  those four still fall through to noise. Re-verified by reading the full
  35-81 table and the alias dict directly — exactly those four names are
  absent from both.
- Confirmed fixed, no regression: note 47 (mid tom) resolves to `"tom_mid"`
  (`drum_engine.py:19`) — a real, non-`None` role name — and the
  velocity→primary→role fallback cascade in `_resolve_dpcm_sample_name`
  (`dpcm_sampler/enhanced_drum_mapper.py:405-418`) still tries all three
  candidates before returning `None`.

### Dimension 2 — `dpcm_index.json` schema integrity
- No change. `generate_dpcm_index.py` (lines 82-102) is still the sole
  writer, still emitting only `id` + `filename`; `length`/`data`/`frequency`
  still always fall back to their defaults in
  `DPCMSampleManager.allocate_sample` (`dpcm_sample_manager.py:34,55,58`).
  This is the same "acceptable simplification, not a bug" conclusion as the
  prior audit — no finding filed for it, consistent with #341's framing.

### Dimension 3 — DPCM conversion correctness
- **#342/DP-DPCM-03 (Existing, OPEN)** — `dpcm_sampler/dpcm_converter.py` is
  still orphaned (`grep -rn "dpcm_converter" --include=*.py .` outside
  `tests/` returns nothing). Its `prev = 0x40` start-level assumption
  (line 36) and fixed 8 kHz resample decoupled from the `$4010` rate index
  are unchanged and would still mis-pitch/misdecode samples if wired in.

### Dimension 4 — Sample size / address / DMC range constraints
- Confirmed fixed, no regression: `_place_sample`
  (`dpcm_sampler/dpcm_packer.py:76-98`) still computes
  `dpcm_length_val = max(0, (sample['size'] + 14) // 16)` — ceiling division,
  matching `docs/APU_DMC_REFERENCE.md` §2/§4's `(L*16)+1` read formula, so
  #295/DP-01 continues to hold. `size` stays bounded to 4081 via the
  truncate-on-add path, so `length_reg ≤ 255` (8-bit safe).
- **#367/DP-DPCM-05 (Existing, OPEN)** — `load_dpcm_index_into_packer`'s
  `skipped` count is still discarded at both call sites
  (`main.py:608-609` in `run_export`, `main.py:1014` in `run_full_pipeline`
  — both `loaded_samples, _ = load_dpcm_index_into_packer(...)`), and
  `generate_assembly`'s `_table` helper (`dpcm_sampler/dpcm_packer.py:130-139`)
  still emits `$00` for any dense id in `range(max_id+1)` that wasn't
  packed. A frame can still reference a dense id whose file failed to
  resolve and get a 1-byte garbage read instead of a warning or fallback.

### Dimension 5 — DMC level handling & DMA-timing implications
- Confirmed fixed, no regression: no producer emits `dmc_level`
  (`grep -rn "dmc_level\|CMD_DMC_LEVEL"` only matches the regression test
  `tests/test_ca65_export.py:413-426`); the `$87` opcode path is still gone.
- `@write_dpcm` (`nes/audio_engine.asm:512+`) still writes `$4015=$0F` →
  `$4010`/`$4012`/`$4013` → `$4015=$1F`, matching
  `docs/APU_DMC_REFERENCE.md` §6's trigger order. Bytecode-path
  `audio_init` still zeroes `$4011` (`nes/audio_engine.asm:132-135`).
- **#348/NH-HW-2026-07-18-1 (Existing, OPEN)** — direct-export `init_music`
  (`exporter/exporter_ca65.py:879-891`) still has no `$4011` write; only
  `$4017`, `$4015`, and the two pulse sweep registers are initialized.

### Dimension 6 — Config robustness
- Confirmed fixed, no regression: `DrumMapperConfig.from_file`
  (`dpcm_sampler/enhanced_drum_mapper.py:161-193`) now catches `TypeError`
  from a stray config key and re-raises `ValueError`
  (lines 190-191: `except TypeError as e: raise ValueError(...)`) — #76/D-13
  is fixed on this tree (the skill's "still open" framing is stale, as the
  prior audit also noted).
- `EnhancedDrumMapper.__init__` (`enhanced_drum_mapper.py:200-201`) still
  calls `self.config.validate()` unconditionally before constructing
  `DPCMSampleManager`, so a `from_file`-loaded config is still validated
  before use through this constructor. No new direct-construction call site
  found outside tests.

### Dimension 7 — Sample-manager dedup & lifecycle
- Confirmed fixed, no regression: `_next_id` is still monotonic
  (`dpcm_sample_manager.py:13,51-52`), memory accounting is still unified
  around `metadata['size']` with the up-front `pending_size` check
  (lines 42, 57, 120-130), and `_find_similar_sample`/
  `_calculate_sample_similarity` remain deleted.
- **#341/DP-DPCM-02 (Existing, OPEN)** — the manager still runs on constant
  placeholder sizes (Dimension 2) and its eviction decisions still have no
  effect on what the packer actually ships (the packer keys off frame
  `sample_id`, independent of `DPCMSampleManager` state).

### Dimension 8 — Channel-pipeline integration
- Confirmed fixed, no regression: the noise-discard warning
  (`tracker/track_mapper.py:307-317`) still fires only in the
  already-occupied `else` branch and its count is still exactly
  `len(noise_events)` — the sole discard path, re-read in full this cycle.
- Confirmed fixed, no regression: `run_map` (`main.py:119-130`) still guards
  a missing `dpcm_index.json` with a clean `[ERROR]` + exit before calling
  `assign_tracks_to_nes_channels` — #256/D-18 remains fixed.
- **#381/SAFE-2026-07-19-1 (Existing, OPEN)** — `run_full_pipeline`'s legacy
  branch (`main.py:824-827`) still calls `assign_tracks_to_nes_channels`
  against a hardcoded `'dpcm_index.json'` with no existence check before the
  call (unlike `run_map`); a missing index still aborts the whole pipeline
  via the outer `try/except`, rather than degrading to a drumless build the
  way the packer path does.
- **#380/TD-28 (Existing, OPEN)** — `run_export` (`main.py:591-620`) and
  `run_full_pipeline` (`main.py:995-1039`) still each carry their own
  independent `load_dpcm_index_into_packer` call block with duplicated
  open/parse/pack/report logic.
- **#369/EXP-2026-07-19-1 (Existing, OPEN)** — the macro-bytecode DPCM note
  clamp in `exporter/exporter_ca65.py` still clamps to the byte ceiling
  (255) rather than the engine's `$00-$5F` note range; unchanged since
  `7a2054d`/`36348ce` did not touch this clamp.
- **#137/TD-08 (Existing, OPEN)** — stale `.incbin` TODO comment in
  `exporter_ca65.py`, unchanged.
- Confirmed fixed, no regression: the dense-id remap
  (`nes/emulator_core.py:202-241`) and `note = min(255, dense_id + 1)`
  encoding are unchanged; the 255-distinct-sample ceiling is still openly
  tracked as **#343/DP-DPCM-04** (referenced in
  `docs/APU_DMC_REFERENCE.md` §6's "255-Distinct-Sample Ceiling" note,
  itself unchanged) rather than silently re-broken.

### Cross-cutting (adjacent audits' DPCM-relevant issues, confirmed still open)
- **#366/PAT-B** — `DrumPatternDetector` emergent-scan self-overlap (pattern
  audit's territory; re-confirmed still open, not re-litigated here).
- **#368/DP-DPCM-06** — `drum_engine.py`'s dead `optimize_dpcm_samples`
  (`drum_engine.py:109-143`) / `DrumPatternAnalyzer`
  (`drum_engine.py:146-166`) still present with the same missing-`note`-key
  noise-fallback contract bug (`optimize_dpcm_samples` at lines 138-141);
  still unreachable from production code, so still LOW/dead-code risk only.
- **#330/ARR-NEW-6**, **#329/ARR-NEW-5** — arranger-mode drum routing issues
  (arranger audit's primary territory); confirmed still open, out of this
  audit's direct dimension set but noted for completeness since they affect
  drum/noise/DPCM routing under `--arranger`.

## Skeptical checklist (re-run this cycle)

- [x] Unmapped/rare GM drum note 47 still resolves via `DEFAULT_MIDI_DRUM_MAPPING` → `tom_mid`. Confirmed working.
- [x] Velocity→primary→default fallback chain reaches the index correctly; only the 4 genuine gaps (#340) return `None`. Confirmed.
- [x] `length`/`data`/`frequency` still always defaults — not a regression, a known simplification (Dimension 2).
- [x] `length_reg` ceiling division still reads the full tail — #295 holds.
- [x] `DrumMapperConfig.from_file` no longer raises uncaught `TypeError` — #76 fixed, confirmed again.
- [x] `_next_id` monotonic — no reuse path found.
- [x] Memory limit enforced end-to-end via unified `metadata['size']` + up-front pending-size check — confirmed.
- [x] Noise fallback still discarded when noise is occupied, but now warned accurately (`len(noise_events)` exact) — confirmed.
- [x] Dense-id remap survives near-254-distinct-drum songs up to the documented 255 ceiling (#343 tracks the ceiling itself) — confirmed unchanged.
- [x] Packing only referenced samples (#140) can still leave a frame pointing at an unpacked `$00` placeholder on a missing/corrupt file — this is exactly #367/DP-DPCM-05, still open.

All hardware claims re-checked against `docs/APU_DMC_REFERENCE.md` §§1-6 and
`docs/NES_DMA_REFERENCE.md` §§1-6 as cited above; no doc/code drift found.

---

Suggested next step: no new issues to publish this cycle — the 13 issues
re-confirmed above (#329, #330, #340, #341, #342, #343, #348, #366, #367,
#368, #369, #380, #381) are already filed and OPEN. If any are prioritized
for a fix pass, re-run this audit afterward to verify the fix and check for
regressions, per the standard cadence:

```
/audit-publish docs/audits/AUDIT_DPCM_2026-08-05.md
```
(no-op: zero NEW findings to file)
