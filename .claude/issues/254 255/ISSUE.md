# #254 — D-17: MAX_SAFE_SAMPLE_ID=254 guard defeats the dense-remap fix — all shipped-catalog drums route to noise, DPCM disabled

**Severity:** HIGH · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-05.md

## Description
Commit `b49a649` (#200, #201) fixed D-14 by (a) adding named drum samples to `dpcm_index.json`, and (b) renumbering each song's *referenced* catalog ids to a compact song-local `0..N-1` "dense" range in `NESEmulatorCore.process_all_tracks` before the single-byte `note` encoding (`note = min(255, dense_id + 1)`), emitting a `dpcm_sample_map` (dense→catalog) side table so the export/pack stage can recover the real `.dmc` files. This is the correct fix: a real song references far fewer than 255 distinct drums, so the byte ceiling is never hit and no aliasing occurs.

But the **same commit** also added a `MAX_SAFE_SAMPLE_ID = 254` guard in `EnhancedDrumMapper` that runs in the earlier `map` stage and drops any hit whose *raw catalog* id exceeds 254 to the noise fallback (lines 298-304, 389-392, 471-476), incrementing `_oversized_sample_id_count`. The guard's premise — "this id would collide with another sample once clamped to a single byte downstream" — is exactly the collision the dense-remap already prevents. Because the guard fires in `map_drums` (map stage) *before* `process_all_tracks` (frames stage), it removes the high-id hits before the dense-remap can renumber them, so the remap never sees them.

The shipped `dpcm_index.json` now has 1941 samples, and **all 26 resolvable drum-role names sit at ids ≥ 1083** (kick=1318, snare=1620, hihat_closed=1926, tom_mid=1924, crash=1929, ride=1526, cowbell=1119, clap=1096, …). Every one exceeds 254, so every resolvable drum hit is routed to noise. `map_drums` emits **zero** DPCM events on the shipped catalog, and `nes/emulator_core.py`'s dense-remap is dead code for it.

## Location
- `dpcm_sampler/enhanced_drum_mapper.py:202` (`MAX_SAFE_SAMPLE_ID = 254`), `:298-304` (non-pattern hit → noise when id > 254), `:389-392` (pattern path), `:471-476` (layered path)
- vs. the dense-remap it pre-empts at `nes/emulator_core.py:213-235`
- shipped `dpcm_index.json` (named drums at ids 1083–1940)

Verified against current code: guard present at `enhanced_drum_mapper.py:202,298,389,471`; dense-remap present at `nes/emulator_core.py:189-234` (`note = min(255, dense_id + 1)`, `dpcm_sample_map` emitted).

## Evidence
```
$ python3 -c "
from dpcm_sampler.enhanced_drum_mapper import EnhancedDrumMapper
m = EnhancedDrumMapper(dpcm_index_path='dpcm_index.json')
events = {'drums':[{'frame':0,'note':36,'velocity':100},   # kick
                   {'frame':10,'note':38,'velocity':100},   # snare
                   {'frame':20,'note':42,'velocity':100}]}  # closed hi-hat
dpcm, noise = m.map_drums(events)
print('DPCM:', dpcm); print('NOISE:', noise)"
Warning: 3 drum hit(s) resolved to a DPCM sample id > 254 (out of 1941 in
    dpcm_index.json) — routed to noise instead of risking aliasing ...
DPCM: []
NOISE: [{'frame': 0, 'note': 36, ...}, {'frame': 10, ...}, ...]
```
All three named drums resolve to real sample names (`kick`, `snare`, `hihat_closed`), but their catalog ids (1318, 1620, 1926) all exceed 254, so all three drop to noise. 0 of the 26 resolvable role names have id ≤ 254.

The dense-remap the guard pre-empts is proven correct in isolation (`tests/test_audio_fixes.py:160,165`: `sample_id=200 → dpcm_sample_map {'0':200}`, `sample_id=9999 → {'0':9999}`) — but no test drives it end-to-end **through** `map_drums`, so the guard swallowing every hit was never caught.

## Impact
On the shipped `dpcm_index.json`, every song built through the default pipeline (or `export`) loses **all** of its DPCM percussion — every drum hit plays as noise instead of the sampled drum the mapping resolved. A stdout warning is printed (so not fully silent), but the drums are gone from DPCM and the recently-added named samples + the dense-remap infrastructure are both inert. Blast radius: every drummed song on the shipped catalog. Kept below CRITICAL only because playback still produces audible (noise) percussion rather than a broken ROM.

## Related
#200/D-14 (the fix this defeats), #201 (the role-name samples added at ids >254 that this guard then discards), prior D-15 (asset gap — now data-present but guard-blocked), D-18. Introduced by the same fix commit `b49a649`.

## Suggested Fix
Remove the `MAX_SAFE_SAMPLE_ID` guard from `EnhancedDrumMapper` (lines 298-304, 389-392, 471-476) — the dense-remap in `process_all_tracks` already guarantees no catalog id reaches the byte encoding unremapped, and `map_drums` output always flows through `process_all_tracks` before export. If a belt-and-suspenders check is still wanted, move it to the *dense* id after remapping (assert `dense_id + 1 <= 255`, i.e. a song references ≤ 254 distinct drums) rather than the raw catalog id. Add an end-to-end test that drives `map_drums` → `process_all_tracks` with the real shipped index and asserts a kick+snare song produces two distinct non-noise DPCM events.

## Completeness Checks
- [ ] **CONTRACT**: The `map` stage output (drum→DPCM vs noise routing) stays consistent with what `process_all_tracks` (frames stage) expects to dense-remap
- [ ] **SIBLING**: All three guard sites (non-pattern, pattern, layered paths) fixed together
- [ ] **TESTS**: An end-to-end test drives `map_drums` → `process_all_tracks` with the shipped `dpcm_index.json` and asserts non-noise DPCM events
- [ ] **DOC**: If DPCM behavior is documented anywhere, it reflects that shipped-catalog drums now produce DPCM events

---

# #255 — MAP-2026-07-05-1: MMC1 direct export overflows the 16 KB $8000-$BFFF window into fixed-bank space — links clean, plays garbage past 16 KB

**Severity:** CRITICAL · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-05.md

## Description
MMC1 is a banked mapper: only a 16 KB window (`$8000-$BFFF`) of switchable PRG is CPU-visible at a time, plus the fixed last bank at `$C000-$FFFF` (`docs/MAPPER_MMC1_REFERENCE.md`). But `MMC1Mapper.generate_linker_config()` declares the whole switchable pool as a **single** MEMORY region `PRGSWAP: start = $8000, size = $1C000` (112 KB) and loads `RODATA` (the direct-export frame tables) into it. `ld65` therefore assigns `RODATA` run addresses linearly from `$8000` upward across 112 KB — anything past the first 16 KB gets a run address >= `$C000`, which at runtime is the fixed bank (engine code + vectors), not the table data.

Two facts make this fatal and silent:
1. **No bank switching in the direct engine.** `--no-patterns` builds read `lda (temp_ptr),y` where `temp_ptr = table_base + frame_counter` is a flat 16-bit address (`exporter/exporter_ca65.py:439-452`). `generate_init_code` selects bank 0 for `$8000` once and never switches. Only the first 16 KB of `RODATA` is ever readable.
2. **The capacity gate allows 112 KB.** `MMC1Mapper.get_data_capacity()` returns `112*1024`, and the inherited flat `validate_segment_sizes` (`mappers/base.py:161-178`) checks the combined total against that. `check_mapper_capacity` (`main.py:229-247`) uses it, so a 16–112 KB direct export passes pre-flight. `MapperFactory.auto_select` uses `can_fit_data` against the same 112 KB, so `--mapper auto` routes any 30–112 KB direct-export song to MMC1. And `resolve_mapper` forces MMC3 for any pattern/bytecode `music.asm` (`main.py:197-209`), so direct export is MMC1's *only* real operating mode.

## Location
- `mappers/mmc1.py:47-73` (`generate_linker_config`: `PRGSWAP: start = $8000, size = $1C000`; `RODATA: load = PRGSWAP`)
- `mappers/mmc1.py:75-100` (`generate_init_code` fixes bank 0 at `$8000`, never changes it)
- `mappers/mmc1.py:126-128` (`get_data_capacity` = 112 KB) + `mappers/base.py:161-178` (inherited flat `validate_segment_sizes`)
- `exporter/exporter_ca65.py:439-452` (direct play routine: `#<pulse1_note + frame_counter` → `temp_ptr` → `lda (temp_ptr),y`, flat 16-bit, no bank switch)
- `main.py:198-202` (`resolve_mapper('auto')` → `MapperFactory.auto_select`), `mappers/factory.py:84-107`

## Evidence
Built and linked a real MMC1 project through the actual pipeline. A 3-channel, ~23 s synthetic MIDI produces 31,504 bytes of `RODATA`:
```
$ python main.py --no-patterns --mapper mmc1 big.mid mmc1_val.nes
  ✓ Music data 31,504 bytes fits the MMC1 PRG regions      <- pre-flight says OK
✅ SUCCESS! ROM created: mmc1_val.nes   (131,088 bytes)     <- ships, validation passes
```
`ld65 -m map.txt` confirms the overflow into fixed-bank space, with no linker error:
```
RODATA                008000  00FB0F  007B10  00001     <- run $8000..$FB0F (31,504 bytes)
VECTORS               00FFFA  00FFFF  000006  00001
init_music   00C1BA    update_music  00C1D3             <- engine lives at $C000+ (fixed bank)
```
Run addresses `$C000-$FB0F` of `RODATA` alias the fixed bank at runtime. A frame-table byte the engine expects at `$D5xx` is physically in PRGSWAP bank 1 (file offset `0x4010`+), never mapped in; the CPU instead reads an engine opcode byte and plays it as a note/timer. Threshold: `RODATA > 0x4000` (16,384 bytes) — roughly a >23 s song on 3 tone channels, less with noise/DPCM tables. NROM is safe by contrast (single flat 32 KB region, fully CPU-addressable).

## Impact
`--mapper mmc1` (and `--mapper auto` for any 30–112 KB direct-export song) produces a ROM that boots (vectors + APU init intact, so `validate_rom` passes) but plays **garbage for the entire portion of the song past the first 16 KB of frame data**. Fully silent: no `ld65` error, no capacity-gate warning, no validation failure. This nullifies MMC1's advertised purpose — `mmc1.py:8` sells it for "Medium-sized music projects (30KB - 120KB)", but direct export can only use 16 KB and bytecode is force-routed to MMC3, so MMC1 can never actually hold more than 16 KB of playable music. Meets the CRITICAL floor "Music data overruns the mapper's PRG capacity silently (truncated/garbage playback)." Blast radius: every MMC1 build of a normal-length song and every `auto`-selected build in the 30–112 KB range.

## Suggested Fix
Either:
- (a) *Cheapest, correct-by-construction*: cap MMC1 direct-export capacity at the addressable window — override `get_data_capacity()` / `validate_segment_sizes` so `RODATA` is checked against 16 KB (minus a small reserve), turning the silent garbage-ROM into a clear "song too large for MMC1 direct export — use MMC3" pre-flight error; and declare `PRGSWAP` as `size = $4000` so `ld65` errors instead of overflowing. Makes MMC1's real ceiling honest.
- (b) *Full capability*: redeclare the switchable banks as separate `$8000`-based MEMORY regions (like MMC3) and teach the direct engine to bank-switch (`generate_bank_switch_code` writes to `$E000`) based on which 16 KB slice `frame_counter` falls into — delivers the advertised 112 KB.

Also add an integration test that builds an MMC1 ROM with >16 KB of direct-export data and asserts a clean failure (option a) or correct late-frame reads (option b), since REG-10 (#128) currently `pytest.skip()`s on any compile hiccup and would not catch this.

**Hardware ref:** `docs/MAPPER_MMC1_REFERENCE.md` — 16 KB switchable window at `$8000-$BFFF` + fixed last bank at `$C000-$FFFF` (PRG mode 3); the switchable pool is not linearly CPU-addressable and must be declared as per-bank `$8000`-based regions with runtime bank switching, exactly as MMC3 does (`mmc3.py:57-70`).

**Related:** #217/MAP-6 (added the `--mapper` flag that made MMC1 CLI-reachable), #213 (a different, now-fixed MMC1 defect), #128/REG-10 (skip-on-failure integration tests that hid this).

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **CONTRACT**: If a stage's JSON/segment shape changes, the consumer (project builder / linker cfg) was updated in lockstep
- [ ] **CC65**: The capacity gate fails before `ld65`, or `ld65` region overflow surfaces as a nonzero exit + stderr
- [ ] **SIBLING**: Same banked-window vs flat-capacity check applied to MMC3 (verified OK) and any future banked mapper
- [ ] **TESTS**: A regression test builds an MMC1 ROM with >16 KB direct-export data and pins the fix (clean failure or correct late reads)
- [ ] **DOC**: `mmc1.py:8` "30KB-120KB" claim and any docs asserting MMC1's usable direct-export size corrected to match the real ceiling
