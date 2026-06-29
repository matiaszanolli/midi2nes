# DPCM / Drum-Sampling Audit — 2026-06-29

Audit of the DPCM/drum subsystem: GM-percussion → DPCM sample mapping, WAV→1-bit-delta
conversion, sample packing/addressing, and the DMC-facing edges of the channel pipeline
and CA65 exporter. Scope per `.claude/commands/audit-dpcm/SKILL.md`.

Hardware claims cite `docs/APU_DMC_REFERENCE.md` and `docs/NES_DMA_REFERENCE.md`.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2 |
| HIGH     | 3 |
| MEDIUM   | 5 |
| LOW      | 3 |
| **Total**| **13** |

Highest-risk drop / round-trip issues:

- **D-01 (CRITICAL, NEW)** — every shipped `dpcm_index.json` `filename` is bare
  (relative to `dmc/`, e.g. `(Konami…) Hit 1.dmc`) but every consumer resolves it from
  the current working directory. **0 of 1923 samples resolve**; the packer emits dummy
  tables and **all DPCM percussion is silent** on the default pipeline.
- **D-02 (CRITICAL, NEW)** — the drum mapper's `sample_id` is an allocation counter
  (`len(active_samples)`), but the engine indexes the packer's `dpcm_*_table`, which is
  ordered by the index `id`. The two id-spaces are unrelated, so once samples *do* load,
  a drum event plays the **wrong sample**.
- **D-03 (HIGH, NEW)** — the standalone `play_dpcm` routine (direct/`--no-patterns`
  export) tests a stale Z flag after `STA last_dpcm_note`, so a note-0 (rest) sentinel
  re-triggers a bogus `sample_id = $FF` instead of being skipped.

The prior `AUDIT_NES_HARDWARE_2026-06-28.md` findings NH-01 (noise/DPCM never reach APU
registers) and NH-04 (`dmc_level` never written / unclamped) have been **addressed** by
commit `5e155ee` (#9): `nes/emulator_core.py` now emits dpcm `note`/`volume`, and
`exporter/exporter_ca65.py:946-947` now masks `dmc_level &= 0x7F`. Those are confirmed
fixed (see regression notes in D-09).

---

## Findings

### D-01: Shipped DPCM index filenames never resolve — all percussion silent
- **Severity**: CRITICAL
- **Dimension**: 2 (index schema) / 4 (packing) / 8 (pipeline integration)
- **Location**: `dpcm_sampler/generate_dpcm_index.py:13-18`; `main.py:263-265` and
  `main.py:547-554`
- **Status**: NEW
- **Description**: `generate_dpcm_index` writes `filename` as `rel_path` *relative to the
  scanned `dmc_folder`* (line 17 `rel_path = os.path.relpath(full_path, dmc_folder)`), so
  the shipped index stores bare names like `(Konami, Contra Force) Hit 1.dmc`. Both
  packer call sites build `Path(sample['filename'])` and test `sample_path.exists()`
  **relative to the current working directory** — never re-joining the `dmc/` root. The
  real files live under `dmc/`, so the bare names resolve to nothing.
- **Evidence**:
  ```
  # repo state, run from repo root:
  resolve from cwd:   0 / 1923
  resolve from dmc/:  1923 / 1923
  ```
  `main.py:264` `if sample_path.exists():` is False for all 1923 entries → `add_sample`
  is never called → `packer.banks` empty → `generate_assembly` emits the dummy tables
  (`dpcm_packer.py:96-101`: `dpcm_bank_table: .byte $00`, etc.).
- **Impact**: Every ROM built through the default pipeline or `export` packs **zero**
  DPCM samples. The engine's `play_dpcm`/`@write_dpcm` then index a 1-byte dummy table
  for every drum hit, so percussion is silent or garbage on every song with drums. Blast
  radius: all DPCM output, every pipeline run.
- **Related**: D-02 (id mismatch compounds), prior NH-01 (now fixed) assumed tables were
  populated.
- **Suggested Fix**: Store `filename` relative to a known DPCM root and have both packer
  sites resolve `Path(dpcm_root) / sample['filename']`, or write absolute paths in
  `generate_dpcm_index`. Add a non-fatal warning when `loaded_samples == 0` but the index
  was non-empty.

### D-02: `sample_id` is an allocation counter, not the packer table index — wrong sample plays
- **Severity**: CRITICAL
- **Dimension**: 7 (sample-manager lifecycle) / 8 (pipeline integration)
- **Location**: `dpcm_sampler/dpcm_sample_manager.py:53` (`'id': len(self.active_samples)`);
  `dpcm_sampler/enhanced_drum_mapper.py:294-298`; `dpcm_sampler/dpcm_packer.py:93-115`
- **Status**: NEW
- **Description**: `allocate_sample` assigns `'id': len(self.active_samples)` — a
  sequential 0,1,2… counter in *allocation order*. `EnhancedDrumMapper.map_drums`
  propagates this as `dpcm_events[...]["sample_id"]` (line 296), which `emulator_core`
  turns into `note = sample_id + 1` and the engine recovers as `y = note - 1` to index
  `dpcm_bank_table,y / dpcm_pitch_table,y / dpcm_addr_table,y / dpcm_len_table,y`. But the
  packer builds those tables ordered by `sorted(metadata.keys(), key=int)` — the
  `dpcm_index.json` `id` field (0..1922), an entirely different numbering. The allocation
  counter and the index id only coincide by accident.
- **Evidence**: `dpcm_sample_manager.py:53` `'id': len(self.active_samples)`;
  `dpcm_packer.py:94` `ordered_ids = sorted(self.sample_metadata.keys(), key=lambda x: int(x))`
  where keys are `str(sample['id'])` from `main.py:550`. The drum mapper never consults
  the index `id`; the packer never consults the allocation order.
- **Impact**: As soon as samples actually load (after D-01 is fixed), the first drum hit
  allocated (`id=0`) indexes packer table entry 0 — whatever sample has index id 0
  (`(Konami…) Hit 1`), not the kick the MIDI asked for. Every drum event points at the
  wrong sample. Hardware-correct registers, wrong audio.
- **Related**: D-01 (masks this today since tables are dummy), D-06 (id reuse on eviction).
- **Suggested Fix**: Make the drum mapper carry the *index* `id`
  (`self.sample_index[name]['id']`) into `dpcm_events`, not the manager's allocation
  counter, so `sample_id` indexes the packer tables consistently.

### D-03: Standalone `play_dpcm` tests stale Z flag — rest sentinel triggers bogus sample $FF
- **Severity**: HIGH
- **Dimension**: 5 (DMC trigger order) / 8 (integration)
- **Location**: `exporter/exporter_ca65.py:675-683`
- **Status**: NEW
- **Description**: The direct-export (`export_direct_frames`, `standalone=True`,
  reachable via `--no-patterns`) `play_dpcm` routine:
  ```asm
  lda (temp_ptr),y      ; A = note (sample_id+1, 0 = rest)
  cmp last_dpcm_note    ; Z set iff note == last
  beq @done             ; unchanged -> skip
  sta last_dpcm_note    ; STA does NOT affect Z
  beq @done             ; "note 0 -> nothing to trigger"  <-- tests stale cmp Z
  ; New sample: sample_id = note - 1
  sec / sbc #1 / tay ...
  ```
  The second `beq @done` (line 679) is meant to skip when the new note is 0, but `STA`
  leaves the flags from the preceding `CMP` untouched. Control only reaches line 678
  when the `CMP` was *not* equal (the first `beq` at line 677 didn't branch), so Z=0 and
  the second `beq` **never** fires. A rest (`note == 0`) that differs from `last_dpcm_note`
  falls through to `sbc #1` → `y = $FF`, triggering `dpcm_*_table[$FF]` — out-of-table
  garbage.
- **Evidence**: `exporter_ca65.py:676-679`. Contrast the project-builder engine
  `nes/audio_engine.asm:314-316`, which correctly guards with `lda current_note,x / bne :+ / jmp @silence` *before* dispatching to `@write_dpcm`.
- **Impact**: In the `--no-patterns` direct-export ROM, every transition from a sample
  back to silence re-fires a wrong/garbage sample id, producing spurious DPCM noise.
  Project-builder bytecode path is unaffected.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §3 (a `$4015` bit-4 trigger starts the
  reader from the programmed `$4012`/`$4013`; an out-of-range table index yields an
  arbitrary address/length).
- **Suggested Fix**: Reorder to test the note value, e.g. `lda (temp_ptr),y / cmp last_dpcm_note / beq @done / tax / sta last_dpcm_note / txa / beq @done`, or `pha`/`tax` to re-set Z from the note before the second branch.

### D-04: Emulator clamps `sample_id` to 94 — high-id drums collapse to one wrong sample
- **Severity**: HIGH
- **Dimension**: 8 (integration) / 1 (coverage)
- **Location**: `nes/emulator_core.py:124` (`"note": min(95, sample_id + 1)`);
  compounded by `exporter/exporter_ca65.py:952-953`
- **Status**: NEW
- **Description**: `process_all_tracks` stores the dpcm trigger as
  `note = min(95, sample_id + 1)`. The index ships 1923 samples (ids 0–1922), and the
  drum mapper can emit any allocated id. Any `sample_id >= 94` is silently clamped to note
  95 → `sample_id = 94` in the engine. The bytecode path repeats the clamp
  (`if note > 95: note = 95`, line 952). The clamp was presumably borrowed from the
  tone-channel MIDI-note range (0–95), but a DPCM `sample_id` is **not** a MIDI note and
  has no such ceiling.
- **Evidence**: `emulator_core.py:124`; `dpcm_index.json` has 1923 entries; the manager
  can allocate up to `max_samples` (default 16) distinct ids but those ids still index a
  table built from the full index — see D-02.
- **Impact**: Any song using more than ~94 distinct DPCM samples (or, post-D-02-fix, any
  index id ≥ 94) silently maps every high-id hit to a single wrong sample. Audible drum
  substitution with no warning.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2 — DPCM selection is by sample
  address/length tables, not a 7-bit note; there is no MIDI-note ceiling on a sample
  index.
- **Suggested Fix**: Don't reuse the 0–95 MIDI-note clamp for DPCM. Bound `sample_id` by
  the real packed-sample count (or use a 2-byte index), and route through the correct
  index id per D-02.

### D-05: One oversized `.dmc` aborts the entire DPCM pack via broad `except Exception`
- **Severity**: HIGH
- **Dimension**: 4 (size constraints) / 6 (robustness)
- **Location**: `dpcm_sampler/dpcm_packer.py:23-24`; `main.py:532-569` (and `253-269`)
- **Status**: NEW
- **Description**: `DpcmPacker.add_sample` raises `ValueError` when a file exceeds 4081
  bytes. Both packer call sites wrap the *entire* loop + `generate_assembly` in a single
  `try / except Exception` that just prints a warning and continues with **no DPCM
  assembly appended at all**. So a single oversized sample anywhere in the index discards
  every sample's tables for the whole song, not just the offending one.
- **Evidence**: 23 of the shipped `dmc/*.dmc` files exceed 4081 bytes (largest 69347).
  `main.py:568-569` `except Exception as e: print(... Failed to pack DPCM samples ...)`.
  The `ValueError` from `add_sample:24` escapes the per-sample loop and skips
  `generate_assembly`/the append.
- **Impact**: Once D-01's path bug is fixed (files resolve), the first index entry that
  points at a >4081-byte `.dmc` aborts packing → the `.import dpcm_*_table` in `music.asm`
  resolves only to the project-builder stub (`project_builder.py:449-456`) → all DPCM
  silent, reported as a warning, not an error.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2/§4 — max sample length is `(L*16)+1`
  with `L<=255`, i.e. 4081 bytes; longer samples cannot be addressed.
- **Suggested Fix**: Catch `ValueError` per-sample (skip + warn for that sample only), or
  pre-truncate/down-sample oversized `.dmc` files. Keep the rest of the catalog packing.

### D-06: Evicted sample id can be reused and mis-point earlier drum events
- **Severity**: MEDIUM
- **Dimension**: 7 (lifecycle)
- **Location**: `dpcm_sampler/dpcm_sample_manager.py:53` + `195-205` (`_remove_sample`)
- **Status**: NEW
- **Description**: `allocate_sample` sets `'id': len(self.active_samples)`. After
  `_optimize_sample_bank` / `_remove_sample` evicts an entry, `len(active_samples)` drops,
  so a subsequent allocation can produce an `id` already emitted into earlier
  `dpcm_events`. Two distinct samples then share one id; the emitted events that referenced
  the evicted sample now point at the survivor (or vice-versa).
- **Evidence**: `dpcm_sample_manager.py:53` id derivation; `:109-110` eviction; ids are
  never tracked as a monotonic allocator. `enhanced_drum_mapper.py:296` snapshots the id
  into an event at allocation time.
- **Impact**: On songs that exceed `max_samples` (default 16) and trigger eviction,
  earlier drum hits silently change to the wrong sample. Workaround: raise `max_samples`.
  Overlaps the deeper id-space confusion in D-02.
- **Suggested Fix**: Use a monotonic `next_id` counter (never reused), or key events by
  the stable index id (per D-02) rather than the dynamic allocation order.

### D-07: Memory limit is never enforced — two divergent accounting methods
- **Severity**: MEDIUM
- **Dimension**: 7 (lifecycle) / 6 (config)
- **Location**: `dpcm_sampler/dpcm_sample_manager.py:34,37-40,87-88,207-211`
- **Status**: NEW
- **Description**: `allocate_sample` measures memory as `sum(s['metadata']['size'])`,
  where `size` defaults to the `length` placeholder 1024 (the shipped index has no
  `length`, see D-08). `_optimize_sample_bank`'s eviction loop instead gates on
  `_get_total_memory()`, which returns `sum(len(s['data'])//8)` — and `data` is `[]` for
  every real index entry, so it is **always 0**. The two notions of "memory used" never
  agree, and the one driving eviction is permanently 0, so `memory_limit` is never reached
  by that path; only the `max_samples` count check evicts.
- **Evidence**: `:37` `current_memory = sum(s['metadata']['size'] ...)`; `:211`
  `return sum(len(s.get('data', [])) // 8 ...)`; index entries carry only `id`+`filename`.
- **Impact**: The configurable `memory_limit` (1KB–16KB) is dead on real input; only the
  `max_samples` count bounds the bank. Sizing/eviction decisions are made on placeholder
  data, not real sample sizes. Defense-in-depth gap, not a crash.
- **Suggested Fix**: Populate real sample sizes into the index/metadata, or compute size
  from the on-disk `.dmc`, and use one consistent accounting function for both the
  allocate-time check and the eviction loop.

### D-08: Index `length`/`data`/`frequency` always fall back to defaults — similarity/dedup inert
- **Severity**: MEDIUM
- **Dimension**: 2 (schema integrity) / 7 (dedup)
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:286-292`;
  `dpcm_sampler/dpcm_sample_manager.py:34,56,59,174-193`
- **Status**: NEW
- **Description**: `_load_sample_index` passes each raw index entry as `sample_data` to
  `allocate_sample`, which reads `sample_data.get('length', 1024)`,
  `sample_data.get('data', [])`, and `sample_data.get('frequency', 33144)`. The shipped
  `dpcm_index.json` and all `test_dpcm_index.json` fixtures contain only `id` and
  `filename`, so `length`/`data`/`frequency` are **always** the defaults.
  `_calculate_sample_similarity` and `_find_similar_sample` then compare empty `data`
  arrays — `max_len==0` ⇒ `length_similarity=1.0`, `min_length==0` ⇒
  `waveform_similarity=1.0`, so every pair is "100% similar" / the path is inert. The
  dedup/similarity subsystem does nothing on production data.
- **Evidence**: `python -c` over `dpcm_index.json` → keys union `{'filename','id'}`;
  `dpcm_sample_manager.py:174-193`.
- **Impact**: Memory accounting and dedup operate on placeholder data; the "smart sample
  allocation" is effectively a no-op. Cosmetic/over-engineered rather than wrong output.
- **Related**: D-07.
- **Suggested Fix**: Either enrich the index with real `length`/`frequency` (and load
  `data` lazily), or delete the similarity/dedup machinery as dead-on-real-input.

### D-09: `dmc_level` is read but never produced by any stage (dead command path)
- **Severity**: MEDIUM
- **Dimension**: 5 (DMC level handling)
- **Location**: `exporter/exporter_ca65.py:942-947,956-999,1083-1112`;
  `nes/emulator_core.py:112-130`
- **Status**: Regression-check of prior NH-04 (`AUDIT_NES_HARDWARE_2026-06-28.md`) — the
  **clamp** half is fixed; the **dead-path** half remains. Reported NEW (residual).
- **Description**: The bytecode exporter reads `frame_data.get('dmc_level')` and emits
  `CMD_DMC_LEVEL ($87, level)`. The unclamped-byte risk flagged by NH-04 is now fixed:
  `exporter_ca65.py:946-947` masks `dmc_level &= 0x7F`, and `emulator_core.py:128` clamps
  `max(0, min(127, e['dmc_level']))`. However, **no stage ever sets `dmc_level`** on a
  dpcm frame — the dpcm frame builder (`emulator_core.py:123-129`) only writes it when the
  incoming event already has `'dmc_level'`, and nothing upstream (drum mapper, arranger)
  produces it. So the entire `CMD_DMC_LEVEL` plumbing is unreachable on real input.
- **Evidence**: repo-wide, `dmc_level` is only ever read with `.get('dmc_level')` /
  guarded by `if 'dmc_level' in e`; the only writer is the pass-through at
  `emulator_core.py:127-128`.
- **Impact**: Dead code; no functional bug today. Worth tracking so the half-wired
  `$4011` direct-load feature is either completed or removed.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2 — `$4011` is a 7-bit direct-load
  register; the now-present `&0x7F` is correct.
- **Related**: prior NH-04 (clamp portion fixed by commit `5e155ee`).
- **Suggested Fix**: Either generate `dmc_level` for the `$4011` non-linear-mixer trick
  (`docs/APU_DMC_REFERENCE.md` §6) or remove the `CMD_DMC_LEVEL` path.

### D-10: `ADVANCED_MIDI_DRUM_MAPPING` (the default) only defines kick & snare — toms/cymbals dropped
- **Severity**: MEDIUM
- **Dimension**: 1 (mapping coverage)
- **Location**: `dpcm_sampler/drum_engine.py:15-33`;
  `dpcm_sampler/enhanced_drum_mapper.py:247-312`
- **Status**: NEW
- **Description**: `map_drums_to_dpcm`/`map_drums` default to `use_advanced=True`, which
  selects `ADVANCED_MIDI_DRUM_MAPPING`. That table fully defines only notes 36 (kick) and
  38 (snare) and ends with a `# Add more mappings...` stub. For every other GM percussion
  note (40 snare2, 42/44/46 hats, 49/51/57 cymbals, 41–48 toms…), `midi_note in mapping`
  is False, so the code takes the `else: sample_name = mapping.get(midi_note)` branch →
  `None` → the event falls to `noise_events`. Additionally, the velocity-split names the
  advanced map *does* return for 36/38 (`kick_soft`, `kick_hard`, `snare_soft`,
  `snare_hard`) are **absent** from the shipped index, so even kick/snare miss DPCM and
  fall to noise.
- **Evidence**: `drum_engine.py:32` `# Add more mappings...`;
  `enhanced_drum_mapper.py:279-284,376-381`; index lookup —
  `kick_soft/kick_hard/snare_soft/snare_hard in dpcm_index.json` → all False
  (only bare `kick`,`snare`,`ride` exist).
- **Impact**: With the default advanced mapping, essentially **all** drums fall through to
  the noise fallback rather than DPCM — toms/cymbals entirely, and even kick/snare at any
  velocity because the velocity-split sample names don't exist. Drums still make *a*
  sound (noise) so this is a degraded-output MEDIUM, not silent-drop, but it is far from
  the intended DPCM kit.
- **Related**: D-11 (the noise fallback is then itself at risk of being discarded).
- **Suggested Fix**: Flesh out `ADVANCED_MIDI_DRUM_MAPPING` across GM 35–81 and ensure the
  returned sample names exist in the index, or fall back to `DEFAULT_MIDI_DRUM_MAPPING`
  for unmapped notes before resorting to noise.

### D-11: Drum noise-fallback discarded when a real noise track already exists
- **Severity**: MEDIUM
- **Dimension**: 8 (integration)
- **Location**: `tracker/track_mapper.py:243-249`
- **Status**: NEW
- **Description**: `assign_tracks_to_nes_channels` calls `map_drums_to_dpcm` and routes
  the returned `noise_events` only `if noise_events and not nes_tracks['noise']`. When a
  song already has a tonal/effects track assigned to `noise` (the multi-track heuristic at
  lines 235-240 can fill it, or a track named "drum"), the drum noise-fallback hits — the
  very toms/cymbals D-10 pushed to noise — are silently dropped.
- **Evidence**: `track_mapper.py:248` `if noise_events and not nes_tracks['noise']:`.
- **Impact**: On songs with both a noise-channel part and unmapped drums, those drum hits
  vanish entirely (not even noise). Combined with D-10's mass fallthrough, this can drop
  most percussion. MEDIUM (workaround: the noise channel is single, a true hardware
  limit), but the silent discard is the concern.
- **Hardware ref**: NES has a single Noise channel (`docs/APU_NOISE_REFERENCE.md`), so
  some contention is unavoidable; the issue is the *silent* drop with no warning.
- **Suggested Fix**: When dropping drum noise-fallback because `noise` is occupied, emit a
  warning, or merge by frame priority instead of discarding wholesale.

### D-12: `length_reg = (size-1)//16` floors — non-`16k+1` samples under-read their tail
- **Severity**: LOW
- **Dimension**: 4 (size/length constraint)
- **Location**: `dpcm_sampler/dpcm_packer.py:66`
- **Status**: NEW
- **Description**: `_place_sample` computes `dpcm_length_val = (sample['size'] - 1) // 16`.
  The DMC plays back `(length_reg*16)+1` bytes. For a `size` not of the form `16k+1`, the
  floor discards up to 15 trailing bytes (e.g. a 1024-byte sample → `length_reg=63` →
  1009 bytes played, 15 lost). This is correct *clamping* (never over-reads), but it
  silently truncates the tail of most samples by a fraction of a frame.
- **Evidence**: `dpcm_packer.py:66`; computed: `size=1024 → length_reg=63 → 1009 bytes`
  (15 lost); `size=2049 → 2049` (exact).
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2/§4 — length formula `(L*16)+1`,
  16-byte alignment.
- **Impact**: Sub-millisecond tail loss per sample; rarely audible. The packer does *not*
  pad `.dmc` data up to a `16k+1` boundary, so the quantization is lossy by design.
- **Suggested Fix**: Pad/round sample data up to the next `16k+1` length (with silence)
  rather than flooring, so the full sample plays.

### D-13: `DrumMapperConfig.from_file` raises `TypeError` on a stray key; only some errors are caught
- **Severity**: LOW
- **Dimension**: 6 (config robustness)
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:162-191`
- **Status**: NEW
- **Description**: `from_file` does
  `DrumPatternConfig(**config_data.get('pattern_detection', {}))` and
  `SampleManagerConfig(**config_data.get('sample_management', {}))`. A hand-edited config
  with a renamed/extra key raises an uncaught `TypeError` (dataclass got an unexpected
  keyword); only `FileNotFoundError` and `json.JSONDecodeError` are handled. The returned
  config is also not `validate()`-d inside `from_file` (validation only happens if the
  result is passed to `EnhancedDrumMapper.__init__`, which the default
  `map_drums_to_dpcm` never does — it constructs the default config).
- **Evidence**: `enhanced_drum_mapper.py:169-174` (`**` splat), `:188-191` (only two
  excepts).
- **Impact**: A stray config key crashes with a raw `TypeError` traceback instead of a
  clear message. Low reach (no default-path caller uses `from_file`).
- **Suggested Fix**: Filter to known fields (or catch `TypeError`) and call
  `result.validate()` before returning.

---

## Items checked and NOT reported (disproven / already fixed)

- **NH-01 (prior, CRITICAL): noise/DPCM never reach APU registers** — FIXED.
  `nes/emulator_core.py:112-130` now emits dpcm `note`(=sample_id+1)/`volume`, and the
  exporter has a real `dpcm` channel path (`exporter_ca65.py:235-248`, `play_dpcm`,
  `@write_dpcm`). Not regressed.
- **`dmc_level` unclamped to $4011 (prior NH-04 clamp half)** — FIXED via
  `exporter_ca65.py:946-947` (`&= 0x7F`) and `emulator_core.py:128`. Residual dead-path
  reported as D-09.
- **`delta_encode` / `dpcm_compress` polarity** (`dpcm_converter.py:34-66`) — the two
  stages agree (both derive the bit from `encoded[i] > encoded[i-1]`), and a `1` bit
  "adds 2" per `docs/APU_DMC_REFERENCE.md` §3, matching an upward step. LSB-first packing
  (`byte |= bits[i+j] << j`) matches the DMC shifter consuming bit 0 first
  (`docs/APU_DMC_REFERENCE.md` §1 "Reader → Buffer → Shifter"). The `prev = 0x40` start
  vs the hardware default of 0 is a converter-side assumption, but the converter
  (`convert_wav_to_dmc`) is **not invoked by any pipeline path** (only the CLI
  `__main__`), so it is not a shipping-ROM bug — noted here, not filed.
- **`run_map --dpcm-index` ignored (prior pipeline F-05)** — `main.py:48-51` now honors
  `args.dpcm_index`. Not regressed.
- **`$4011` silence init** — `nes/mmc3_init.asm:68-69` writes `LDA #$00 / STA $4011`;
  `nes/audio_engine.asm:122-123` likewise. Matches `docs/APU_DMC_REFERENCE.md` §6.
- **DMA controller-read warning** — present in `nes/project_builder.py:480` (safe joypad
  read) and `docs/NES_DMA_REFERENCE.md` §6. Not a gap.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_DPCM_2026-06-29.md
```
