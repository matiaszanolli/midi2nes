# DPCM / Drum-Sampling Audit — 2026-08-21

Auditor: `/audit-dpcm` (all dimensions). Baseline: `949f0c6` (master, clean tree).
Dedup sources: `gh issue list` (open + `--state all` searches, saved to
`/tmp/audit/issues.json`), `docs/audits/AUDIT_DPCM_2026-08-0[567].md`,
`docs/audits/AUDIT_ARRANGER_2026-0*.md`, and the sibling
`docs/audits/AUDIT_PIPELINE_2026-08-21.md` from this suite run.

## Summary

**5 findings — 1 CRITICAL (dedup cross-ref, already filed as PIPE-2026-08-21-1),
1 HIGH (new), 3 LOW (new).**

| Severity | Count | IDs |
|---|---|---|
| CRITICAL | 1 (cross-ref, not re-filed) | DPCM-2026-08-21-1 (= PIPE-2026-08-21-1) |
| HIGH | 1 | DPCM-2026-08-21-2 |
| MEDIUM | 0 | — |
| LOW | 3 | DPCM-2026-08-21-3, -4, -5 |

**Highest-risk drop/round-trip issues this cycle:**

1. **(cross-ref) Phantom drums on every legacy-mode build** — commit `ffccf51`
   (the DP-DPCM-12 fix) un-gated `EnhancedDrumMapper.map_drums`'s channel-blind
   scan; every melodic note-on in the GM-percussion note range 35–81 is now
   drum-mapped into `nes_tracks['dpcm']`. Independently confirmed on this tree;
   already fully filed (with end-to-end reproduction) as **PIPE-2026-08-21-1** —
   deduped, not re-reported (DPCM-2026-08-21-1 below is the cross-reference).
2. **Arranger-mode drums play the wrong catalog samples** (DPCM-2026-08-21-2,
   HIGH): `--arranger` emits DPCM "sample" values from `DPCM_SAMPLE_SLOTS`
   (kick→0, snare→1), but the pack stage interprets those as `dpcm_index.json`
   catalog ids — catalog id 0 is "(Konami, Contra Force) Hit 1" and id 1 is
   "(Konami, Contra Force) Kick". Every arranged kick fires "Hit 1"; every
   arranged snare fires a kick. This is the unfixed half (b) of closed issue
   #87/ARR-04, live now that arranger drum detection works.

**Verify-the-fix sweep (all clean — no regressions found):**

- **#DP-DPCM-12 fix holds** (`enhanced_drum_mapper.py:324`): the dual-key
  `e.get('velocity', e.get('volume', 0))` read is in place; `grep "get('velocity'"`
  across `dpcm_sampler/` returns only that line;
  `tests/test_enhanced_drum_mapper.py:85-118` now exercises `volume`-keyed
  (parser-shaped) events, including the zero-volume note-off skip. (Its side
  effect is the CRITICAL cross-ref above.)
- **#73/D-10 cascade**: `DEFAULT_MIDI_DRUM_MAPPING` covers 35–81; note 47 →
  `tom_mid`, which exists in the shipped index. Of all role/velocity names, only
  `side_stick`, `tambourine`, `splash`, `kick_soft/hard`, `snare_soft/hard`, and
  `vibraslap` are absent from the index — all except `vibraslap` (documented
  asset gap, #340) are covered by `DPCM_ROLE_ALIASES` or the
  velocity→primary→default fallback chain in `_resolve_dpcm_sample_name`, which
  only ever returns a name verified `in self.sample_index`.
- **#341/DP-DPCM-02 + #413/DP-DPCM-07**: `_real_sample_size` caches `None` for
  both unresolvable paths and falls back to the 1024 placeholder without
  crashing; `data`/`frequency` remain permanent, understood placeholders
  (index entries carry exactly `{'id', 'filename'}` — verified across all 1941
  entries; the skill prose's "1923" count is stale).
- **#295/DP-01 ceiling holds**: `dpcm_length_val = max(0, (size + 14) // 16)`
  with `size ≤ 4081` ⇒ `length_reg ≤ 255` (8-bit safe). The only production
  `add_sample` caller (`generate_dpcm_index.py:99-104`) passes `truncate=True`;
  no caller passes `truncate=False`. (But see DPCM-2026-08-21-3 for a 1-byte
  over-read edge the fix's own safety comment gets wrong.)
- **#140 filtered packing**: both export paths share `main.py:pack_dpcm_into_asm`
  (call sites `main.py:709` and `main.py:1234` — #380/TD-28 still consolidated);
  `$00` placeholder slots for missing-file samples are guarded at runtime by the
  `@write_dpcm` zero-length skip (`nes/audio_engine.asm:669-680`) and surfaced
  loudly by name at pack time (#367/DP-DPCM-05). (See DPCM-2026-08-21-4 for a
  sentinel-conflation nit.)
- **#72/D-09**: `CMD_DMC_LEVEL`/`dmc_level` has not been re-added anywhere
  (grep clean across exporter/engine/builder).
- **$4011 silence init** present in the engine (`nes/audio_engine.asm:197`) and
  both direct-export init variants (`exporter/exporter_ca65.py:788`, `:946`),
  matching `docs/APU_DMC_REFERENCE.md` §5 "Silence Initialization" (#348 holds).
- **`@write_dpcm` trigger order** (`nes/audio_engine.asm:663-703`): `$4015`
  stop (`$0F`) → MMC3 bank hot-swap → `$4010` → `$4012` → `$4013` → `$4015`
  enable (`$1F`); pitch is masked `& 0x0F` at pack time so `$4010` IRQ/loop
  bits can never be set. Matches the doc's trigger procedure.
- **DMA/controller warning**: `nes/project_builder.py:276-300` generates the
  DPCM-safe controller-read routine `docs/NES_DMA_REFERENCE.md` ("Mandatory
  Controller Protection") requires. Not omitted.
- **#69/D-06**: `_next_id` monotonic counter in place; eviction cannot re-key
  already-emitted events because `map_drums` emits the *index* id
  (`sample_data['id']`), never the manager's allocation id (#65 holds).
- **#70/D-07**: unified `metadata['size']` accounting plus the up-front
  `pending_size` check verified; memory pressure alone triggers eviction.
- **#74/D-11**: the noise-fallback discard warning
  (`tracker/track_mapper.py:361-363`) reports exactly `len(noise_events)` and is
  the only discard path for those events.
- **#DP-DPCM-13**: the leftover-track loop routes only drum-named tracks to
  noise and drops the rest with a per-track warning
  (`tracker/track_mapper.py:336-342`); `tracker/track_mapper.py:351` is the only
  writer of `nes_tracks['dpcm']` in the legacy path (grep across
  `tracker/`, `arranger/`, `nes/`, `main.py`).
- **#256/D-18**: `run_map` still pre-checks the index path and exits cleanly.
- **#200/#254/#343 dense remap**: `nes/emulator_core.py:209-238` remaps to
  dense 0..N-1, emits `dpcm_sample_map`, and warns loudly when >255 distinct
  samples are referenced (dense_id ≥ 255 aliasing is detected, not silent).
- **#76/D-13 is FIXED** (contrary to the skill prose, which still lists it
  open): `DrumMapperConfig.from_file` catches `TypeError` and re-raises a clear
  `ValueError` (`enhanced_drum_mapper.py:194-195`), and calls
  `result.validate()` before returning (`:188`) — fixed in `3b905fc`
  (2026-07-18), covered by
  `tests/test_drum_mapper_config.py::test_stray_key_raises_clear_error`, and
  already confirmed in the 2026-08-07 report. `/audit-sync` should retire the
  "Still open (#76/D-13)" paragraph in `audit-dpcm`'s Dimension 6.

## Findings

### DPCM-2026-08-21-1: `ffccf51` un-gated `map_drums`'s channel-blind scan — melodic notes 35–81 become phantom DPCM drum triggers (cross-ref, dedup)
- **Severity**: CRITICAL
- **Dimension**: 1 (drum-note mapping) / 8 (channel-pipeline integration)
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:315-385` (`map_drums`,
  no channel filter), `tracker/track_mapper.py:348` (passes the full unsplit
  `midi_events`), `dpcm_sampler/drum_engine.py:7-55` (35–81 note coverage)
- **Status**: Existing: **PIPE-2026-08-21-1** (this suite's pipeline audit) —
  deduped per suite protocol, not re-filed.
- **Description**: Independently confirmed. `map_drums` iterates every track
  and every event with no channel-9 (or any) gating; before `ffccf51` the
  `e.get('velocity', 0) == 0` guard made the loop dead on real parser output
  (`volume`-keyed), which accidentally masked the missing filter. The
  DP-DPCM-12 fix (correct in itself) removed the mask: now every melodic
  note-on whose pitch falls in 35–81 (most of the melodic range) resolves
  through `DEFAULT_MIDI_DRUM_MAPPING` to a real sample and is emitted as a
  DPCM trigger; notes outside the map become noise-fallback events. The
  comment at `tracker/track_mapper.py:260-263` even documents scanning the
  full input as intentional ("broader, channel-optional drum detection") —
  but no detection exists in `map_drums`. `--arranger` mode is unaffected.
- **Evidence**: See PIPE-2026-08-21-1 for the end-to-end reproduction
  (drumless `test_midi/simple_loop.mid` builds a ROM packing 3 phantom DPCM
  samples; `song build` falsely rejects the same song).
- **Impact**: Silently changes the song on essentially every legacy-mode
  drummed *or drumless* build; breaks `song build` for melodic banks.
- **Related**: DP-DPCM-12 (2026-08-07 report), #404/ARR-NEW-5-LEGACY (the
  channel-9 split that deliberately excluded this call).
- **Suggested Fix**: (as PIPE-2026-08-21-1) restrict `map_drums`'s input to
  channel-9 events (reuse `_split_events_by_channel`), falling back to
  drum-*named* tracks only when no channel info exists.

### DPCM-2026-08-21-2: Arranger DPCM slot ids are packed as catalog ids — every `--arranger` kick plays "Hit 1", every snare plays a kick
- **Severity**: HIGH
- **Dimension**: 8 (channel-pipeline integration) / 2 (index schema semantics)
- **Location**: `arranger/voice_allocator.py:317-321` (`DPCM_SAMPLE_SLOTS`
  = {kick: 0, snare: 1}), `:387` (`return self.DPCM_SAMPLE_SLOTS.get(...)`);
  `arranger/pipeline_integration.py:342-346` (`note = min(255, data['sample'] + 1)`,
  no `dpcm_sample_map` emitted); `dpcm_sampler/generate_dpcm_index.py:155-161`
  (missing `dpcm_sample_map` ⇒ dense ids treated as catalog ids)
- **Status**: Regression of **#87 (ARR-04)** — closed by `e1be17d`, but only
  divergence (a) (note-40 routing / noise periods) was fixed; divergence (b)
  ("the DPCM sample indices 0/1/2 do not match `dpcm_index.json`") was left
  as-is and the issue closed. Originally MEDIUM because unreachable (arranger
  drums were undetected, #86/ARR-01/02); those upstream bugs are now fixed, so
  the mis-mapping is live → HIGH.
- **Description**: The arranger's DPCM allocation returns a *slot* number
  (0 = kick, 1 = snare, unreachable fallback 2) with no relation to
  `dpcm_index.json`. `pipeline_integration` encodes it directly as
  `note = sample + 1` and emits **no** `dpcm_sample_map` side table. The pack
  stage's documented fallback (`get_dpcm_sample_ids_from_frames`: "its absence
  ... falls back to treating dense ids as catalog ids directly") then packs
  catalog entries with ids 0 and 1. In the shipped index, id 0 =
  `(Konami, Contra Force) Hit 1`, id 1 = `(Konami, Contra Force) Kick`,
  id 2 = `(Konami, Contra Force) Snare` (the real curated samples are
  `kick` = id 1318, `snare` = id 1620). The positional lookup tables are
  internally consistent, so playback "works" — it just plays the wrong
  drums: kick → a generic hit, snare → a kick.
- **Evidence**:
  ```python
  # arranger/voice_allocator.py:317-321, 387
  DPCM_SAMPLE_SLOTS = {"Acoustic Bass Drum": 0, "Bass Drum 1": 0, "Acoustic Snare": 1}
  return self.DPCM_SAMPLE_SLOTS.get(mapping.name, 2)
  # arranger/pipeline_integration.py:342-346 — no dpcm_sample_map:
  output['dpcm'][frame] = {'note': min(255, data['sample'] + 1), 'volume': 15}
  # dpcm_index.json: id 0 = "(Konami, Contra Force) Hit 1",
  #                  id 1 = "(Konami, Contra Force) Kick"; kick=1318, snare=1620
  ```
- **Impact**: Every `--arranger` build whose MIDI has channel-9 kick/snare
  packs and triggers the wrong percussion samples. Wrong audio on realistic
  input, no warning anywhere (the pack succeeds — the referenced ids 0/1
  resolve to real files). This is the arranger-path twin of the long-fixed
  legacy D-02/#65 id-space bug.
- **Related**: #87 (ARR-04), #65 (D-02), #200/D-14 (`dpcm_sample_map`
  mechanism the arranger path never adopted), ARR audits 2026-07-19 /
  2026-08-05 (tracked only the slot-2 dead-code aspect).
- **Hardware ref**: none (pure software id-space mismatch; the emitted
  `$4012`/`$4013` values are hardware-correct for the *wrong* sample).
- **Suggested Fix**: Resolve slot names to real catalog entries the same way
  the legacy path does — look up `kick`/`snare` in the loaded index, emit the
  raw catalog id, and produce `frames['dpcm_sample_map']` (or emit
  `sample_id`-shaped events and reuse `NESEmulatorCore`'s dense remap). Add an
  end-to-end arranger test asserting the packed filename for a kick is the
  catalog's `kick.dmc`.

### DPCM-2026-08-21-3: `length_reg` ceiling read overruns the 64-byte-aligned block by 1 byte for `size % 64 ∈ {0, 50..63}` — the #295 fix's "safe zero-pad" claim is wrong for 2.3% of the catalog
- **Severity**: LOW
- **Dimension**: 4 (sample size/address constraints)
- **Location**: `dpcm_sampler/dpcm_packer.py:79-88` (`_place_sample` comment +
  formula), `:38` (`aligned_size`), `:100-117` (`generate_assembly` contiguous
  placement)
- **Status**: NEW (residual edge of closed #295/DP-01; no prior report or
  issue covers the spill — verified against `docs/audits/AUDIT_DPCM_2026-08-0*.md`)
- **Description**: The engine reads `(length_reg*16)+1` bytes
  (`docs/APU_DMC_REFERENCE.md` §2, `$4013` formula). With
  `length_reg = (size+14)//16` (ceiling, correct per #295), the read length is
  `16*ceil((size-1)/16)+1`. The code comment asserts "the `.align 64` gap
  after each sample makes the few extra bytes safe zero-pad" — but when
  `size % 64` is 0 or in 50..63, the read length exceeds `aligned_size` by
  exactly 1 byte, and there *is* no gap: the next sample starts at the very
  next 64-aligned offset (`.align 64` inserts nothing when already aligned,
  and `_pack_samples` packs blocks contiguously by `aligned_size`). Measured
  against the real catalog: **44 of 1941 samples (2.3%)** hit this window.
  Mid-bank, the DMC's last byte comes from the *next sample's first byte*;
  for a sample ending a full 8KB bank (`$C000+$2000`), the read lands at
  `$E000` — outside the swapped DPCM window, in the fixed PRG bank (arbitrary
  code bytes). This is *not* the `$FFFF`→`$8000` wrap quirk (max end address
  is `$E000`, far below `$FFFF`); the wrap remains impossible, as prior
  audits established.
- **Evidence**: `size = 64` → `length_reg = (64+14)//16 = 4` → engine reads
  `4*16+1 = 65` bytes from a 64-byte aligned block; `size = 50..63` likewise
  read 65. Catalog measurement script (this audit): 44/1941 affected, spill
  always exactly 1 byte.
- **Impact**: 8 garbage delta bits (±2 output-level nudges each, clamped
  0–127 per doc §3) appended to the tail of an affected sample —
  ≈0.24 ms of wrong slope at rate 15; audibly negligible, never a crash or
  drop. Main cost is the false safety invariant in the comment, which a future
  packing change (e.g. removing `.align 64`, or tighter packing) could
  silently amplify.
- **Related**: #295/DP-01, #75.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2 (`$4013` = `(L*16)+1`
  bytes), §4 (64-byte address alignment), §3 (±2 step, 0–127 clamp).
- **Suggested Fix**: Size each sample's block as
  `max(aligned_size, ceil((length_reg*16+1)/64)*64)` (one extra 64-byte row
  for the affected 2.3%), or pad the `.incbin` with explicit zero bytes up to
  `length_reg*16+1`; update the `_place_sample` comment either way.

### DPCM-2026-08-21-4: `@write_dpcm`'s `$00`-length placeholder sentinel also suppresses genuine `length_reg = 0` samples — 2 catalog entries can never play
- **Severity**: LOW
- **Dimension**: 4 (range constraints) / 5 (trigger path)
- **Location**: `nes/audio_engine.asm:669-680` (zero-length skip),
  `dpcm_sampler/dpcm_packer.py:88` (`max(0, ...)` producing a legitimate 0),
  `dpcm_sampler/dpcm_packer.py:141-145` (`$00` placeholder scheme)
- **Status**: NEW (residual edge of closed #367/DP-DPCM-05)
- **Description**: Per `docs/APU_DMC_REFERENCE.md` §2, `$4013 = 0` is the
  *valid* encoding for a real 1-byte sample (`(0*16)+1 = 1`). The #367 fix
  reuses `len_table == $00` as the "never packed / file missing" sentinel, so
  a genuinely packed 0/1-byte sample is indistinguishable from a placeholder
  and is silently skipped at trigger time. The shipped catalog contains two
  such entries: id 1103 `click (2)` (1 byte) and id 1452 `mute` (0 bytes).
  A MIDI hit resolving to either is packed, warned about by nobody, and never
  fires.
- **Evidence**: `lda dpcm_len_table, y / bne @sample_ready / jmp @next_channel`
  treats L=0 as "unpacked"; catalog scan found exactly the two entries above.
- **Impact**: Negligible audio loss (a 1-byte sample is 8 delta bits ≈ 0.24 ms;
  `mute` being skipped is arguably the intent). Worth documenting so a future
  catalog with meaningful tiny samples doesn't hit it blind.
- **Related**: #367/DP-DPCM-05, #295/DP-01.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2 (`(L*16)+1` — L=0 is a
  1-byte sample, not "no sample").
- **Suggested Fix**: Either floor packed `length_reg` at 1 for any real sample
  (reads 17 bytes of its 64-byte block — harmless zero-pad) or warn at pack
  time when a real sample's `length_reg` computes to 0.

### DPCM-2026-08-21-5: `dpcm_converter` residuals beyond #342 — 8-bit PCM fed into a 0–127-clamped ±1-step model, and the first delta bit is never emitted
- **Severity**: LOW
- **Dimension**: 3 (1-bit delta conversion; module is orphaned — no pipeline caller)
- **Location**: `dpcm_sampler/dpcm_converter.py:14-43`
  (`convert_wav_to_unsigned_pcm` returns 0–255 uint8), `:46-60` (`delta_encode`
  clips `prev` to 0–127, steps ±1), `:63-84` (`dpcm_compress` starts at `i=1`)
- **Status**: NEW (distinct from the sub-bugs closed under #342/DP-DPCM-03 —
  start level and rate defaults, both verified fixed — and from the
  constant-input downward-ramp residual already documented in the 2026-08-06
  report as #342's accepted reduced scope)
- **Description**: Two previously-unreported model mismatches versus
  `docs/APU_DMC_REFERENCE.md` §3 (each bit adds/subtracts **2** on a **7-bit**
  0–127 counter):
  (a) **Range/step-scale mismatch** — the encoder's feedback tracker `prev`
  clips to 0–127 and steps ±1, but its input is unnormalized 8-bit PCM
  (0–255, silence = 128). Silence therefore sits *above* the tracker's
  ceiling, pinning `prev` at 127 and biasing the whole encode; and the ±1
  step means the sigma-delta error feedback models half the amplitude
  hardware actually reconstructs (±2/step). The docstring's "Compress 7-bit
  values" contract is not what `convert_wav_to_unsigned_pcm` delivers.
  (b) **First-bit drop** — `delta_encode` outputs post-step levels starting
  from init 0, but `dpcm_compress` derives bits only for `encoded[1:]`
  transitions, so the initial 0→`encoded[0]` step is never emitted; playback
  is offset by one step from the modeled reconstruction.
  Note: the reference doc's "Reader → Buffer → Shifter" diagram does not state
  the shifter's bit order explicitly, so the LSB-first packing (`bit << j`)
  can only be verified against NESdev consensus (bit 0 first — it matches),
  not a doc citation; worth one added sentence in the doc.
- **Evidence**: `data = ((data + 32768) / 256).astype(np.uint8)` (0–255) →
  `prev = np.clip(prev + step, 0, 127)`; `for i in range(1, len(encoded))`.
- **Impact**: None in production (module has no caller; `.dmc` catalog is
  pre-made). Anyone regenerating the catalog with this tool gets top-pinned,
  half-scale-modeled encodes. LOW per the orphaned-code rule.
- **Related**: #342/DP-DPCM-03 (closed), #337/REG-18 (test coverage),
  2026-08-06 report Dimension 3.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §3 (±2 steps, 0–127 clamp,
  7-bit counter), §1 (signal flow).
- **Suggested Fix**: Scale PCM to 0–127 (`data >> 1`) before `delta_encode`,
  step the tracker ±2, and emit bits from `encoded[0]` relative to the init
  level; add the explicit LSB-first sentence to the doc.

## Skeptical checklist (this cycle)

- [x] Note 47 (mid tom) resolves to `tom_mid`, present in the index — no
      silent failure.
- [x] The candidate cascade only returns names verified `in self.sample_index`;
      `kick_soft` (absent) falls through to `kick` (id 1318). Tests cover it.
- [x] `length`/`data`/`frequency`: `length` backfilled from disk (#341);
      `data`/`frequency` permanent placeholders; the dead similarity code
      stays deleted — nothing depends on `data`.
- [x] `length_reg` ceiling (#295) holds and is 8-bit-bounded — but see
      DPCM-2026-08-21-3 for the 1-byte aligned-block overrun edge.
- [x] `DrumMapperConfig.from_file` no longer leaks `TypeError` — #76 is
      **fixed** (`3b905fc`); skill prose is stale.
- [x] Evicted ids cannot be reused (`_next_id` monotonic) and cannot re-key
      emitted events (events carry index ids, not manager ids).
- [x] Memory limit enforced end-to-end with `pending_size`; few-but-large
      eviction works (accounting-only — no ROM effect, as documented).
- [x] Occupied-noise drum fallback discard is warned with the exact
      `len(noise_events)` count; it is the only discard path.
- [x] Dense-id round-trip near the byte ceiling: >255 distinct samples warns
      loudly (#343); `min(255, dense_id + 1)` holds to 255 distinct.
- [x] `$00` placeholder slots are unreachable at runtime via the
      `@write_dpcm` zero-length skip and warned by name at pack time (#367) —
      with the L=0 sentinel-conflation caveat filed as DPCM-2026-08-21-4.

Suggested next step:

```
/audit-publish docs/audits/AUDIT_DPCM_2026-08-21.md
```
