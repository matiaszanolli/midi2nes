# DPCM / Drum-Sampling Audit — 2026-07-19

Scope: `dpcm_sampler/` plus the DMC-facing edges of the channel pipeline
(`tracker/track_mapper.py`, `nes/emulator_core.py`, `nes/audio_engine.asm`,
`main.py` pack call sites). Hardware claims verified against
`docs/APU_DMC_REFERENCE.md` and `docs/NES_DMA_REFERENCE.md`.

## 1. Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 1 |
| LOW      | 1 |
| **Total**| **2** |

New: 2 · Existing (already tracked, skipped): 0 reported (4 confirmed still valid — see below).

Highest-risk item: **DP-DPCM-05 (MEDIUM)** — a song frame can reference a dense
DPCM id whose `.dmc` file was skipped at pack time (missing/corrupt file), leaving
the engine to index a `$00` placeholder (or read past the table), triggering a
garbage/click DPCM hit instead of the intended drum or a clean noise fallback. The
`skipped` count from the packer loader is discarded and only the all-missing
(`loaded_samples == 0`) case is guarded. On the shipped tree all 1941 catalog files
resolve, so this bites only a corrupted/custom install — hence MEDIUM, not HIGH.

### Fixes verified holding (no regression found)
- **#295/DP-01** ceiling length: `dpcm_length_val = max(0,(size+14)//16)` is exactly
  `ceil((size-1)/16)`, so `(L*16)+1 >= size` for every size; tail fully read.
  `size` bounded to 4081 ⇒ `L ≤ 255` (8-bit safe). Matches `APU_DMC_REFERENCE.md` §2/§4.
- **#75** floor-under-read regression: not present.
- **#73/D-10** full GM 35–81 coverage: mid-tom note 47 → `tom_mid` resolves to a real
  catalog key; the velocity→primary→role→alias cascade in
  `_resolve_dpcm_sample_name` reaches the index and only returns `None` (→ noise) for
  genuine asset gaps.
- **#69/D-06** monotonic `_next_id`, **#70/D-07** unified `metadata['size']` memory
  accounting + up-front `pending_size` check, **#71/D-08** dead similarity code
  removed: all confirmed in `dpcm_sample_manager.py`.
- **#74/D-11** noise-discard warning: the dropped count equals `len(noise_events)`
  exactly and the `else` branch is the only discard path.
- **#140** referenced-only packing + dense remap; **#200/D-14 / #254** dense-id byte
  encoding: confirmed in `emulator_core.py:202-241` and
  `generate_dpcm_index.get_dpcm_sample_ids_from_frames`.
- **#256/D-18** `run_map` missing-index guard: now present (`main.py:125-128`) — the
  skill's Dimension 8 note that it "still crashes" is stale.
- **#76/D-13** `from_file` stray-key `TypeError`: now caught and re-raised as
  `ValueError` (`enhanced_drum_mapper.py:192-193`) — the skill's "still open" note is
  stale; this is fixed on this tree.
- DMC trigger order (`nes/audio_engine.asm:@write_dpcm`): `$4015=$0F` (stop) →
  `$4010`/`$4012`/`$4013` → `$4015=$1F` (enable w/ DMC bit 4). Matches
  `APU_DMC_REFERENCE.md` §6. `$4011←$00` silence init present at `audio_init`
  (`audio_engine.asm:136`).

### Existing open issues confirmed still valid (deduped, not re-reported)
- **#340 / DP-DPCM-01** — GM roles splash(55), vibraslap(58), triangle_mute(80),
  triangle_open(81) have no catalog sample and no alias; they fall to noise. Verified
  by resolving all 47 roles against the shipped catalog: exactly those 4 fail.
- **#341 / DP-DPCM-02** — `DPCMSampleManager` runs on placeholder sizes (`length`
  absent from every index entry ⇒ constant 1024) and its eviction never affects the
  packed ROM (the packer keys off frame `sample_id`, not the manager). Still true.
- **#342 / DP-DPCM-03** — `dpcm_converter.py` is orphaned (grep: no non-test importer);
  its `prev=0x40` start level + constant-input `bit=0` (level ramps down on playback)
  and fixed 8 kHz resample decoupled from the `$4010` rate index would mis-pitch
  samples if it were wired in. Still orphaned.
- **#343 / DP-DPCM-04** — the `note = min(255, dense_id+1)` byte ceiling aliases
  `dense_id ≥ 255` onto the 255th sample; warned (`emulator_core.py:220-224`) but not
  prevented. Boundary confirmed: 255 distinct is exact, 256+ collides.

## 2. Findings

### DP-DPCM-05: Missing-file DPCM samples leave frames pointing at `$00` placeholder slots
- **Severity**: MEDIUM
- **Dimension**: 4 (size/address/table integrity) + 8 (channel-pipeline integration)
- **Location**: `dpcm_sampler/generate_dpcm_index.py:83-96` (silent skip),
  `main.py:650-657` and `main.py:1056-1063` (discard `skipped`),
  `dpcm_sampler/dpcm_packer.py:139-145` (`_table` `$00` placeholder)
- **Status**: NEW
- **Description**: Dense DPCM ids are assigned at the **frames** stage
  (`emulator_core.process_all_tracks`) purely from the `sample_id`s a song
  references — it never checks whether the `.dmc` file exists. File resolution
  happens later, in `load_dpcm_index_into_packer`, which **silently skips** any entry
  whose file does not resolve (`skipped += 1; continue`, only warns when
  `verbose=True`, and both pack call sites pass the default `verbose=False`). The
  frame still encodes `note = dense_id + 1` for the skipped sample. In
  `generate_assembly`, `_table` emits `$00` for any id in `range(max_id+1)` not in
  `sample_metadata`, so the skipped dense_id's slot becomes `$00` across
  bank/pitch/addr/len — or, if it was the highest dense_id, it is dropped from
  `max_id` entirely and the frame indexes past the table into adjacent RODATA.
- **Evidence**: `main.py:651-657` handles only the all-missing case:
  ```python
  loaded_samples, _ = load_dpcm_index_into_packer(packer, dpcm_index, dpcm_index_path, sample_ids=sample_ids)
  if loaded_samples == 0 and sample_ids:
      dpcm_pack_warning = (... "the exported ASM has NO drums.")
  ```
  The `skipped` return (second element, `_`) is discarded, so a partial miss
  (`loaded > 0` and `skipped > 0`) produces no warning and no reconciliation. At
  runtime `@write_dpcm` (`nes/audio_engine.asm:531-539`) loads
  `dpcm_len_table,y = $00` ⇒ `$4013 = 0` ⇒ `(0*16)+1 = 1` byte read from bank 0 /
  `$C000`, i.e. a 1-byte fragment of the first packed sample (`APU_DMC_REFERENCE.md`
  §2/§4) — a click/garbage trigger, not the intended drum.
- **Impact**: A drum hit the MIDI clearly intended is replaced by a click or a
  wrong-sample fragment (or an out-of-range read) whenever any referenced `.dmc` is
  missing at pack time. Blast radius: any song on a corrupted/custom install where
  `dpcm_index.json` lists a file not on disk. All 1941 shipped catalog files
  currently resolve, so shipped-default builds are unaffected — hence MEDIUM.
- **Related**: #140 (referenced-only packing introduced the sparse tables), #341
  (manager decoupled from packing), Dimension 4 skeptical-checklist item ("placeholder
  slots provably unreachable?").
- **Suggested Fix**: Have `load_dpcm_index_into_packer` return the set of dense ids it
  actually packed (or reuse `skipped`), and at the pack call sites either (a) emit a
  non-verbose `[WARN]` naming the dropped drums, and/or (b) drop the corresponding
  frames back to a noise fallback so no frame indexes an unpacked slot. Minimally,
  stop discarding `skipped` and surface it like `loaded_samples == 0`.

### DP-DPCM-06: `drum_engine.py` ships production-dead helpers, one with a latent noise-contract bug
- **Severity**: LOW
- **Dimension**: 1 (drum mapping) / tech-debt
- **Location**: `dpcm_sampler/drum_engine.py:109-143` (`optimize_dpcm_samples`),
  `dpcm_sampler/drum_engine.py:146-166` (`DrumPatternAnalyzer`)
- **Status**: NEW
- **Description**: Both `optimize_dpcm_samples` and the `DrumPatternAnalyzer` class
  are imported only by tests (grep shows no production caller). `DrumPatternAnalyzer`'s
  `detect_patterns` / `detect_groove` / `optimize_mapping` are empty bodies (implicit
  `return None`), and `analyze_drum_track` feeds those `None`s forward — the class
  cannot do anything. Separately, `optimize_dpcm_samples` builds its noise fallback as
  `{"frame": ..., "velocity": ...}` with **no `note` key**, contradicting the noise-event
  contract the live `map_drums` path was fixed to honor (#195/NH-26:
  `process_all_tracks` derives a noise period via `midi_to_nes_pitch()` from `note`).
  It is inert today only because nothing wires it into the pipeline.
- **Evidence**: `drum_engine.py:138-141`:
  ```python
  noise_fallback.append({
      "frame": event['frame'],
      "velocity": event['velocity'],
  })   # no 'note' — would KeyError/mis-pitch in process_all_tracks
  ```
- **Impact**: Dead surface area and drift risk; if either helper is ever re-wired the
  missing `note` key becomes a real `KeyError`/silent mis-pitch on the noise channel.
- **Related**: #195/NH-26 (noise `note` contract), #331/#302 (other dead public API).
- **Suggested Fix**: Delete both (and their tests) if the roadmap has no consumer, or
  finish `DrumPatternAnalyzer` and add the `note` key to `optimize_dpcm_samples`'s
  fallback so it matches the live contract.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_DPCM_2026-07-19.md
```
