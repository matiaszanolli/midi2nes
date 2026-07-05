# Audit: Mappers / Project Builder / Compiler — 2026-07-05

Subsystem audited: `mappers/` (base, factory, nrom, mmc1, mmc3), `nes/project_builder.py`,
`compiler/compiler.py`, `compiler/cc65_wrapper.py`, plus the exporter seam
(`exporter/exporter_ca65.py`) and the `main.py` `--mapper` pipeline call sites. All 10
SKILL.md dimensions covered. Like the 07-03 pass, this audit **built and linked real ROMs
with the installed CC65 toolchain** (`ca65`/`ld65` at `/usr/bin`) rather than relying on
static review alone — this surfaced one new CRITICAL that static review would have missed.

This is an incremental re-audit on top of `docs/audits/AUDIT_MAPPERS_2026-07-03.md` (6
findings, 2 CRITICAL). Since that pass the subsystem was heavily reworked:

- **MAP-1** (per-bank `BANK_NN`+`DPCM_NN` sum) — **FIXED** (`mmc3.py:200-236`, #212). Verified.
- **MAP-2** (MMC1 post-link vector fixup bricking ROMs) — **FIXED**: the fixup was deleted;
  `MMC1Mapper.generate_post_process_commands` now falls back to the no-op base
  (`mmc1.py:116-124`, #213). Verified: a linked MMC1 ROM keeps its correct vectors.
- **MAP-3** (`ROMCompiler.compile` skipped post-process) — **FIXED**: `compile()` now takes a
  `mapper` and runs `_run_post_process()` after link (`compiler/compiler.py:73-103,178-189`,
  #214). Verified.
- **MAP-4** (unused MMC3 `OAM` segment) — **FIXED**: no `OAM` region/segment remains in
  `mmc3.py`. Verified via `grep`.
- **MAP-5** (stale HEADER-guard comment) — **FIXED**: `exporter/exporter_ca65.py:110` now
  reads "this exporter is the sole owner of `.segment \"HEADER\"` (#22)". Verified.
- **MAP-6 / #217** (auto-select unreachable) — **FIXED**: a real `--mapper {auto,nrom,mmc1,mmc3}`
  CLI flag now exists; `resolve_mapper()`/`check_mapper_capacity()` wire NROM/MMC1 into the
  `prepare`/`compile`/full-pipeline paths (`main.py:184-247,1034-1046`). Verified by building.
- **#28** (flat `MIN_ROM_SIZE`) — **FIXED**: `compile()` now compares against
  `mapper.prg_rom_size + 16` when a mapper is supplied; both call sites pass one
  (`main.py:361,907`). Verified.
- **#32** (`compile_rom` broad `except` swallowed traceback) — **FIXED**:
  `compiler/compiler.py:244-252` now prints the traceback under `--verbose`. Verified.

The #217 `--mapper` flag is the pivotal change: it makes NROM and MMC1 **reachable from the
CLI for the first time**. The prior audits' repeated caveat "unreachable from `main.py`, only
via the public API" no longer holds. That new reachability is where this pass found its
CRITICAL.

**Dedup basis:** `/tmp/audit/issues.json` (32 open issues) plus a scan of `docs/audits/`.
No open issue references MMC1 direct-export addressing / the 16 KB window (searched `mmc1`,
`window`, `16k`, `direct`, `bank`); the only `mmc1`/`direct` hits are unrelated (NH-25,
NH-14, TD-11). This CRITICAL is NEW.

## ⚠️ Prompt-injection note

No injected instructions were encountered in any tool output during this audit. All findings
come from reading source files and from real `ca65`/`ld65` build + link-map output.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 0 |
| MEDIUM   | 0 |
| LOW      | 0 |
| **Total**| **1** |

**One-line verdict:** The **default** pipeline (MMC3, patterns-on) **does now reliably
produce a bootable ROM** — verified by building MMC3, NROM, and MMC1 ROMs end-to-end and
passing post-build validation, and both 07-03 CRITICALs are confirmed fixed. But the newly
CLI-reachable **`--mapper mmc1`** path (and `--mapper auto` for 30–112 KB songs, which routes
to MMC1) **silently ships a broken ROM** whenever the direct-export frame tables exceed 16 KB,
because MMC1's linker layout puts that data at run addresses the flat-addressing direct engine
can never read.

**Highest-leverage fix:** MAP-2026-07-05-1 — MMC1's `generate_linker_config()` lays `RODATA`
across a single 112 KB `PRGSWAP` region declared at `start = $8000`, so `ld65` assigns run
addresses that spill past the 16 KB `$8000-$BFFF` window into `$C000-$FFFF` (the fixed-bank
address space) with **no error**. The `--no-patterns` direct engine reads frame tables with
flat 16-bit `(ptr),y` addressing and never bank-switches, so every frame whose table entry
lands past `$BFFF` reads fixed-bank engine bytes as note/timer data. Either constrain MMC1
direct-export capacity to the 16 KB window in `validate_segment_sizes`/`get_data_capacity`, or
give the direct engine MMC1 bank-switching (and lay each swap bank at `$8000` like MMC3 does).

---

## Findings (CRITICAL first)

### MAP-2026-07-05-1: MMC1 direct export overflows the 16 KB `$8000-$BFFF` window into fixed-bank address space — `ld65` links clean, playback reads garbage past 16 KB
- **Severity**: CRITICAL
- **Dimension**: 4 (PRG capacity / overrun detection) / 5 (bank-switching correctness)
- **Location**: `mappers/mmc1.py:47-73` (`generate_linker_config`: `PRGSWAP: start = $8000,
  size = $1C000` — one linear 112 KB region; `RODATA: load = PRGSWAP`); `mappers/mmc1.py:75-100`
  (`generate_init_code` fixes bank 0 at `$8000` and never changes it); `mappers/base.py:140-178`
  (MMC1 inherits the flat `get_data_capacity` = 112 KB and flat `validate_segment_sizes`);
  `exporter/exporter_ca65.py:439-452` (direct play routine: `#<pulse1_note + frame_counter`
  → `temp_ptr` → `lda (temp_ptr),y`, flat 16-bit, no bank switch); `main.py:198-202`
  (`resolve_mapper('auto')` → `MapperFactory.auto_select`), `mappers/factory.py:98-107`.
- **Status**: NEW (latent since the mapper abstraction was introduced, but only reachable from
  the CLI since #217/MAP-6 added `--mapper`; not covered by any open issue or prior audit —
  07-03's MAP-2 was a different MMC1 defect, the post-link vector fixup, now fixed).
- **Description**: MMC1 is a banked mapper: only a 16 KB window (`$8000-$BFFF`) of its
  switchable PRG is CPU-visible at a time, plus the fixed last bank at `$C000-$FFFF`
  (`docs/MAPPER_MMC1_REFERENCE.md`). But `generate_linker_config()` declares the whole
  switchable pool as a **single** `MEMORY` region `PRGSWAP: start = $8000, size = $1C000`
  (112 KB) and loads `RODATA` (the direct-export frame tables) into it. `ld65` therefore
  assigns `RODATA` run addresses **linearly from `$8000` upward across 112 KB** — anything
  past the first 16 KB gets a run address ≥ `$C000`, which at runtime is the **fixed bank**
  (engine code + vectors), not the table data. Two independent facts make this fatal and
  silent:
  1. **No bank switching in the direct engine.** `--no-patterns` builds don't include
     `audio_engine.asm`; the generated play routines read `lda (temp_ptr),y` where
     `temp_ptr = table_base + frame_counter` is a flat 16-bit address
     (`exporter/exporter_ca65.py:439-452`). `generate_init_code` selects bank 0 for `$8000`
     once and never switches it. So only the first 16 KB of `RODATA` is ever readable; the
     rest sits in PRGSWAP banks 1–6 that are never mapped in.
  2. **The capacity gate allows 112 KB.** MMC1 uses the base flat `validate_segment_sizes`
     against `get_data_capacity()` = 112 KB (`base.py:140-147,161-178`), so a 16–112 KB
     direct export passes the pre-flight ("✓ fits"). `MapperFactory.auto_select` uses the same
     `can_fit_data`, so `--mapper auto` routes any 30–112 KB song to MMC1
     (`auto_select(40*1024)` → MMC1, verified). And MMC1 is *only* ever a direct-export mapper:
     `resolve_mapper` forces MMC3 for any pattern/bytecode `music.asm`
     (`main.py:197-209`), so the broken 112 KB budget is MMC1's *only* real operating mode.
- **Evidence**: Built and linked a real MMC1 project through the actual pipeline. A 3-channel,
  ~23 s synthetic MIDI produces 31,504 bytes of `RODATA`:
  ```
  $ python main.py --no-patterns --mapper mmc1 big.mid mmc1_val.nes
    ✓ Music data 31,504 bytes fits the MMC1 PRG regions      <- pre-flight says OK
  ✅ SUCCESS! ROM created: mmc1_val.nes   (131,088 bytes)     <- ships, validation passes
  ```
  `ld65 -m map.txt` on the same prepared project confirms the overflow into fixed-bank space,
  with no linker error:
  ```
  RODATA                008000  00FB0F  007B10  00001     <- run $8000..$FB0F (31,504 bytes)
  VECTORS               00FFFA  00FFFF  000006  00001
  init_music   00C1BA    update_music  00C1D3             <- engine lives at $C000+ (fixed bank)
  ```
  Run addresses `$C000-$FB0F` of `RODATA` alias the fixed bank at runtime. A frame-table byte
  the engine expects at, say, `$D5xx` is physically in PRGSWAP bank 1 (file offset `0x4010`+),
  never mapped in; the CPU instead reads an `init_music`/engine opcode byte and plays it as a
  note/timer. Threshold: `RODATA > 0x4000` (16,384 bytes) — roughly a >23 s song on 3 tone
  channels, less with noise/DPCM tables. For comparison, **NROM is safe**: its `PRG` is one
  flat 32 KB region `start = $8000, size = $8000` (`nrom.py:51`), fully CPU-addressable, and a
  near-capacity NROM build links with `RODATA` ending at `$B5B0` (well under `$FFFA`), engine
  `CODE` only 241 bytes — the 2 KB reserve is ample. Only MMC1 has the banked-window mismatch.
- **Impact**: `--mapper mmc1` (and `--mapper auto` for any 30–112 KB direct-export song)
  produces a ROM that boots (vectors and APU init are intact, so post-build `validate_rom`
  passes — verified "SUCCESS") but plays **garbage for the entire portion of the song past the
  first 16 KB of frame data**. Silent: no `ld65` error, no capacity-gate warning, no validation
  failure. This nullifies MMC1's advertised purpose entirely — `mmc1.py:8` sells it for
  "Medium-sized music projects (30KB - 120KB)", but direct export can only use 16 KB and
  bytecode is force-routed to MMC3, so MMC1 can never actually hold more than 16 KB of playable
  music. Meets the CRITICAL floor "Music data overruns the mapper's PRG capacity silently
  (truncated/garbage playback)." Blast radius: every MMC1 build of a normal-length song and
  every `auto`-selected build in the 30–112 KB range.
- **Related**: #217/MAP-6 (added the `--mapper` flag that made MMC1 CLI-reachable), 07-03
  MAP-2/#213 (a *different*, now-fixed MMC1 defect), Dimension 4 capacity-gate work (#126/#127/#212).
- **Hardware ref**: `docs/MAPPER_MMC1_REFERENCE.md` (16 KB switchable window at `$8000-$BFFF`
  + fixed last bank at `$C000-$FFFF` in PRG mode 3) — confirms the switchable pool is not
  linearly CPU-addressable and must be declared as per-bank `$8000`-based regions with runtime
  bank switching, exactly as MMC3 does (`mmc3.py:57-70`, all `PRG_BANK_NN` at `start = $C000`).
- **Suggested Fix** (either): (a) *Cheapest and correct-by-construction*: cap MMC1 direct-export
  capacity at the addressable window — override `get_data_capacity()` / `validate_segment_sizes`
  so `RODATA` is checked against 16 KB (minus a small reserve), turning the current silent
  garbage-ROM into a clear "song too large for MMC1 direct export — use MMC3" pre-flight error;
  and correspondingly declare `PRGSWAP` as `size = $4000` so `ld65` errors instead of
  overflowing into fixed space. This makes MMC1's real ceiling honest. (b) *Full capability*:
  redeclare the switchable banks as separate `$8000`-based `MEMORY` regions (like MMC3) and
  teach the direct engine to bank-switch (`generate_bank_switch_code` writes to `$E000`) based
  on which 16 KB slice `frame_counter` falls into — a larger change that would actually deliver
  the advertised 112 KB. Also add an integration test that builds an MMC1 ROM with >16 KB of
  direct-export data and asserts a clean failure (option a) or correct late-frame reads
  (option b), since REG-10 (#128) currently `pytest.skip()`s on any compile hiccup and would
  not catch this.

---

## Previously identified, still open (dedup per `_audit-common.md`)

- None outstanding from the mapper domain. The two items the 07-03 pass carried forward,
  **#28** (flat `MIN_ROM_SIZE`) and **#32** (broad `except` masking the traceback), are both
  now **fixed** in `compiler/compiler.py` (verified above), and MAP-1..MAP-6 are all closed
  and verified fixed. Cross-domain, **REG-10 (#128)** (ROM-compile integration tests that
  `pytest.skip()` on real compile failures) remains open and is why the CRITICAL above could
  land without CI catching it — flagged for `/audit-regression`, not owned here.

## Dimension coverage map

| Dim | Area | Result |
|-----|------|--------|
| 1 | iNES header ↔ nes.cfg | Verified via real builds: NROM ships 32,784 B (32 KB PRG + 16), MMC1 131,088 B (128 KB + 16), MMC3 512 KB + 16 — each header PRG byte (`$02`/`$08`/`32`) and mapper nibble (`$00`/`$10`/`$40`) matches its `nes.cfg`. No mismatch. |
| 2 | Vectors + 60Hz NMI | All three ROMs boot; `validate_rom` passes reset/NMI/IRQ + APU checks. 07-03 MAP-2 (MMC1 vector fixup) confirmed **fixed** (#213) — linked MMC1 vectors stay correct. |
| 3 | APU init | Post-build validation confirms APU init present on NROM/MMC1/MMC3 builds. No finding. |
| 4 | PRG capacity/overrun | **MAP-2026-07-05-1 (CRITICAL, NEW)** — MMC1 flat 112 KB capacity is 7× its 16 KB addressable window; direct export silently overflows. NROM 2 KB reserve verified ample (engine `CODE` = 241 B). MMC3 per-bank sum (MAP-1/#212) verified fixed. |
| 5 | Bank switching | MMC3 `$46`/`$47` R6/R7 + `$E000` IRQ-disable match `docs/MAPPER_MMC3_REFERENCE.md`. MMC1 5-write serial load + `$0C` control match `docs/MAPPER_MMC1_REFERENCE.md`. The MMC1 defect is the *absence* of bank switching on the direct-export read path (folded into the CRITICAL), not a wrong sequence. |
| 6 | MapperFactory auto-select | Now genuinely reachable via `--mapper auto` → `resolve_mapper` → `auto_select` (#217, verified). Smallest-fits-first order correct. But `auto` inherits the MMC1 capacity bug (routes 30–112 KB songs to broken MMC1) — see CRITICAL. |
| 7 | Project builder buildability | NROM/MMC1/MMC3 all assemble+link. MAP-4 (OAM) and MAP-5 (stale comment) confirmed **fixed**. Segment sets consistent between `main.asm`/`music.asm`/`nes.cfg` per mapper. |
| 8 | Compiler / CC65 surfacing | `assemble`/`link` raise with stderr (unchanged). MAP-3/#214 (`_run_post_process`) and #32 (traceback under `--verbose`) confirmed **fixed**. |
| 9 | MIN_ROM_SIZE | #28 confirmed **fixed**: exact `mapper.prg_rom_size + 16` check; both `compile_rom` call sites pass `mapper` (`main.py:361,907`). |
| 10 | Default-mapper doc drift | Clean: `CLAUDE.md`/`README.md` describe MMC3 as the default with MMC1/NROM selectable; `--mapper` default is `mmc3` (`main.py:1034`). No doc reasserts MMC1 as *the* default. No finding. |

---

Next step:
```
/audit-publish docs/audits/AUDIT_MAPPERS_2026-07-05.md
```
