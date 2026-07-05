# MAP-2026-07-05-1: MMC1 direct export overflows the 16 KB $8000-$BFFF window into fixed-bank space — links clean, plays garbage past 16 KB

Filed as https://github.com/matiaszanolli/midi2nes/issues/255

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
