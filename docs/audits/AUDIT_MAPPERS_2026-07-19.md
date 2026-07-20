# Audit: Mappers / Project Builder / Compiler — 2026-07-19

Subsystem audited: `mappers/` (base, factory, nrom, mmc1, mmc3), `nes/project_builder.py`,
`compiler/compiler.py`, `compiler/cc65_wrapper.py`, and the `main.py` `--mapper`
resolution / capacity pre-flight / `resolve_mapper` / `enforce_direct_export_dpcm_mapper`
call sites. All 10 SKILL.md dimensions covered; no `--focus` restriction.

**Method:** every claim re-verified against live code, and the mapper build paths were
reproduced end-to-end with the real CC65 toolchain (`ca65`/`ld65` at `/usr/bin`). NROM,
MMC1, and MMC3 ROMs were built from `test_midi/simple_loop.mid` this pass and their iNES
headers + `$FFFA–$FFFF` vectors inspected in the binary.

**Dedup basis:** `/tmp/audit/issues.json` (18 open issues) searched for `mapper`,
`compile`, `auto`, `nrom`, `mmc1`, `mmc3`, `bank`, `capacity`, `dpcm`, `direct`,
`marker`, `resolve`; all prior `docs/audits/AUDIT_MAPPERS_*.md` (2026-06-28 … 2026-07-18)
reviewed. Prior-audit standing finding **#316** (relative-path project dir doubling) is
confirmed **FIXED** this pass — `compiler/compiler.py:148` now `Path(project_dir).resolve()`.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 3 |
| LOW      | 0 |
| **NEW this pass** | **3** |

**One-line verdict:** The default single-command pipeline (MMC3, patterns-on) produces a
bootable 512 KB ROM end-to-end, and the alternate `--no-patterns --mapper nrom|mmc1`
paths also build and validate — all three new findings are defense-in-depth / usability
gaps that fail cleanly (pre-flight or `ld65` catches them), never a broken ROM.

**Live re-verification (this pass):**

| Build | ROM size | Header (PRG / mapper nibble) | Vectors (nmi/reset/irq) | Validation |
|-------|----------|------------------------------|-------------------------|------------|
| `simple_loop.mid` (MMC3 default, patterns) | 524,304 B (512 KB + 16) | `$20`=32 / `$40`→4 | `$E02F` / `$E000` / `$E03D` | bootable |
| `--no-patterns --mapper nrom` | 32,784 B (32 KB + 16) | `$02`=2 / `$00`→0 | `$8016` / `$8000` / `$8024` | bootable |
| `--no-patterns --mapper mmc1` | 131,088 B (128 KB + 16) | `$08`=8 / `$10`→1 | `$C045` / `$C000` / `$C053` (file offset `0x2000A`) | bootable |

All vectors land inside each mapper's fixed/code region; APU init present on both export
paths (`init_music` writes `$4017`/`$4015`; bytecode `audio_init` writes `$4011`/`$4017`/`$4015`).
The exact ROM-size check (`compiler/compiler.py:207-216`) matches each mapper's declared
size exactly. MMC3 `nes.cfg` `MEMORY` regions sum to exactly 524,288 (60×`$2000` +
`PRG_A0`/`PRG_C0`/`PRG_80` 3×`$2000` + `PRG_FIX` `$1FFA` + `VECTORS` `$0006`), agreeing
with the header PRG byte. MMC1/MMC3 register sequences match `docs/MAPPER_MMC1_REFERENCE.md`
(Mode 3, `$0C` control, `$E000` PRG-bank serial writes) and `docs/MAPPER_MMC3_REFERENCE.md`
(`$46`/`$47` = mode-1 R6/R7 selects, R6→`$C000` DPCM, R7→`$A000` sequence, `$E000` IRQ off,
`PRG_80`/`PRG_FIX` in physical-bank order per #291). Dimension 10 doc-drift grep: clean —
no source or doc reasserts MMC1 as *the* default.

---

## Findings

### MAP-2026-07-19-1: `--mapper auto` overstates MMC3's direct-export (`--no-patterns`) capacity by ~85×, so `auto` can only ever pick MMC3 for a direct song it then rejects
- **Severity**: MEDIUM
- **Dimension**: 6 (MapperFactory auto-selection)
- **Location**: `mappers/factory.py:83-114` (`auto_select` uses `can_fit_data` → `get_data_capacity`); `mappers/base.py:162-181` (flat `get_data_capacity`); `mappers/mmc3.py:31-36` (`prg_rom_size` 512 KB, no `direct_export_bank_size` override → inherits `None`); reached from `main.py:604-606` and `main.py:1003-1005` (`estimate_direct_export_size` → `MapperFactory.auto_select`).
- **Status**: NEW
- **Description**: For a direct (`--no-patterns`) export, MMC3 does **not** bank-pack frame tables (`direct_export_bank_size()` returns `None`, inherited from `BaseMapper`), so `export_direct_frames` emits everything into `RODATA`, which loads into the 8 KB fixed bank `PRG_FIX`. MMC3's *real* direct-export budget is therefore `PRG_FIX_SIZE − FIXED_BANK_ENGINE_RESERVE = 6,138` bytes (`mappers/mmc3.py:179-202`) — smaller than NROM's 30 KB and MMC1's 112 KB. But `auto_select` ranks mappers by the flat `get_data_capacity` (NROM 30 KB < MMC1 112 KB < **MMC3 522,240 B**), i.e. exactly backwards from real direct-export capacity. Consequently MMC3 is auto-picked only when the estimated direct size is >112 KB (too big for MMC1), and in that entire window the MMC3 direct pre-flight (`validate_segment_sizes`) always rejects it. Net effect: `--mapper auto --no-patterns` can never actually produce an MMC3 direct ROM; in the 112 KB–510 KB window `auto` "selects" MMC3 and the very next step declares MMC3 too small.
- **Evidence**:
  ```
  $ python3 -c "from mappers.factory import MapperFactory as F; m=F.auto_select(200*1024); \
      print(m.name, m.get_data_capacity()); print(m.validate_segment_sizes({'RODATA':200*1024}))"
  MMC3 522240
  ['fixed-bank data (204,800 bytes of CODE+RODATA) exceeds the MMC3 PRG_FIX budget
   (~6,138 bytes). The direct (--no-patterns) export packs frame tables into the 8 KB
   fixed bank — enable pattern compression or shorten the song.']
  ```
- **Impact**: `--mapper auto --no-patterns` on any song whose direct frame tables estimate between ~112 KB and ~510 KB. Blast radius is the CLI auto-selection UX only — the capacity pre-flight (Dimension 4) always fires before `ld65`, so **no broken ROM ships**; the failure is a confusing "auto picked MMC3, then MMC3 is too small" message. Workaround: drop `--no-patterns` (the default MMC3 bytecode path bank-switches and does fit), or shorten the song.
- **Related**: Dimension 4 pre-flight (`main.py:check_mapper_capacity`) is the backstop that keeps this from becoming a silent overrun; #255 (MMC1 direct bank-packing, which MMC3 direct lacks).
- **Hardware ref**: `docs/MAPPER_MMC3_REFERENCE.md` §2–3 (`$E000-$FFFF` fixed last bank; only `$C000-$DFFF` swappable in Mode 1 — direct tables have no swap window and must fit the single fixed bank).
- **Suggested Fix**: Make `auto_select` export-mode-aware — for a direct export, rank by each mapper's real direct budget (`direct_export_bank_size()` pool for MMC1, `PRG_FIX` budget for MMC3), or simply exclude MMC3 from direct-export auto-selection and let the pre-flight message point at pattern compression. Alternatively add a dedicated "direct capacity" method distinct from the flat `get_data_capacity`.

### MAP-2026-07-19-2: Direct-export DPCM has no `music.asm` marker, so the split `prepare`/`compile` flow can't re-force MMC3 and fails at `ld65` on a mismatched `--mapper`
- **Severity**: MEDIUM
- **Dimension**: 6 / 8 (`--mapper` resolution across the split flow)
- **Location**: `main.py:321-354` (`enforce_direct_export_dpcm_mapper`, requires `frames`, called only at `main.py:611` / `main.py:1010`); `main.py:276-318` (`resolve_mapper`, the only guard the marker-less `prepare`/`compile` path has) checks `_requires_mmc3_bytecode_engine` (marker `"MMC3 Macro Bytecode"`) and `_direct_export_packed_mapper_name` (marker `"; Direct export bank-packed for …"`) but **not** direct-export DPCM; `exporter/exporter_ca65.py:206-207` stamps the bank-pack marker only when `direct_export_bank_size()` is not `None` (MMC3 returns `None`, so a direct-export DPCM `music.asm` gets **no** marker).
- **Status**: NEW
- **Description**: The direct-export DPCM guard `enforce_direct_export_dpcm_mapper` (which forces MMC3 for `auto` and rejects an explicit `nrom`/`mmc1` because `play_dpcm` writes MMC3's `$8000`/`$8001` ports and `DpcmPacker` emits MMC3-only `DPCM_NN` segments) runs **only** where the in-memory `frames` dict is available — i.e. the `export` subcommand and `run_full_pipeline`. A direct-export DPCM `music.asm` (necessarily built as MMC3, since `export` forces it) carries **no marker** identifying it as DPCM/MMC3-only, unlike the bytecode path ("MMC3 Macro Bytecode") and the MMC1 bank-packed path ("Direct export bank-packed for MMC1"). So `main.py prepare --mapper nrom music.asm proj/` (then `compile`) runs `resolve_mapper('nrom', music.asm)` which finds neither marker and honors NROM; `check_mapper_capacity` with NROM sums the `DPCM_NN` bytes into the flat total (NROM/`base.validate_segment_sizes` has no `DPCM_NN` branch) and passes if small; the mismatch surfaces only as a raw `ld65` "Missing memory area assignment for DPCM_00" at link time.
- **Evidence**: `export_direct_frames` (`exporter/exporter_ca65.py:206`) — `if mapper is not None and mapper.direct_export_bank_size() is not None:` — MMC3's `direct_export_bank_size()` is the inherited `None`, so the marker line is never emitted for the exact mapper direct-export DPCM is forced onto. `resolve_mapper` (`main.py:289-303`) has no DPCM branch; `NROMMapper`/`BaseMapper.validate_segment_sizes` treat `DPCM_NN` as generic flat data.
- **Impact**: The manual step-by-step flow `export --no-patterns` (a DPCM song → MMC3) followed by `prepare`/`compile --mapper nrom|mmc1`. Fails cleanly at `ld65` (no broken ROM), but with a cryptic linker error instead of the clean "DPCM is MMC3-only" `ValueError` the single-command pipeline gives. This is the one remaining hole in the split-flow hardening that #283/#285 (bank-pack marker) and #297/#269 (nes.cfg marker) otherwise closed.
- **Related**: #281/#282 (`enforce_direct_export_dpcm_mapper`); #283/#285 (`_direct_export_packed_mapper_name` marker); #297/#269 (`nes.cfg` mapper marker) — this finding is the direct-DPCM analogue those markers don't cover.
- **Hardware ref**: `docs/MAPPER_MMC3_REFERENCE.md` §5 (DPCM sample banks swapped via R6 at `$8000`/`$8001` — MMC3-only); `docs/MAPPER_MMC1_REFERENCE.md` §4 (MMC1 DPCM streaming unimplemented).
- **Suggested Fix**: Stamp a `"; Direct export DPCM (MMC3-only)"` marker in `export_direct_frames`/`DpcmPacker` output when a DPCM channel is present, and have `resolve_mapper` force MMC3 / reject non-MMC3 on it — mirroring the bank-pack marker. Or teach `resolve_mapper`/`validate_segment_sizes` to treat any `DPCM_NN` segment in a non-MMC3 target as an unsupported-mapper error up front.

### MAP-2026-07-19-3: Capacity pre-flight and exact ROM-size check live only in the `main.py` CLI layer — a library consumer of `NESProjectBuilder`/`compile_rom` gets neither gate
- **Severity**: MEDIUM
- **Dimension**: 4 / 9 (capacity pre-flight; ROM size check)
- **Location**: `main.py:373-391` (`check_mapper_capacity`, called from `run_prepare` `main.py:534`, `run_full_pipeline` `main.py:1113` — the CLI layer only); `nes/project_builder.py:82-279` (`prepare_project` does **not** call `validate_segment_sizes`/`check_mapper_capacity`); `compiler/compiler.py:113-118,206-221` (`compile(mapper=None)` falls back to the flat `MIN_ROM_SIZE = 32768` floor).
- **Status**: NEW
- **Description**: Both correctness gates for this subsystem are wired in `main.py`, not in the reusable classes. `NESProjectBuilder.prepare_project()` writes `nes.cfg`/`main.asm`/`music.asm` with no capacity check, and `ROMCompiler.compile()`/`compile_rom()` enforce the exact per-mapper size only when a `mapper` is passed — otherwise just the flat 32768-byte floor. A consumer that uses these classes as a library directly (bypassing `main.py`, e.g. building `NESProjectBuilder(...).prepare_project(...)` then `compile_rom(dir, out)` with no `mapper` arg) therefore gets: (a) no pre-link overflow message — relies entirely on `ld65` erroring; and (b) only the 32768 floor, which a truncated MMC3 (512 KB) or MMC1 (128 KB) image ≥ 32768 bytes would slip past.
- **Evidence**: `prepare_project` (`nes/project_builder.py:82`) contains no `validate_segment_sizes` call — verified by reading the full method. `compile()` size check (`compiler/compiler.py:207`) is guarded `if mapper is not None:` with an `elif rom_size < self.MIN_ROM_SIZE:` fallback. Both CLI callers (`run_compile` `main.py:509`, full pipeline `main.py:1127`) *do* pass the resolved mapper, so the CLI is fully covered; only non-CLI library use is exposed.
- **Impact**: Defense-in-depth only. `ld65` still errors on a genuine region overflow, so this is not a silent-overrun path; the gap is a missing clean pre-flight message and a weaker (flat-floor) size check for library consumers. No current in-tree caller is affected.
- **Related**: #11/#126/#127 (capacity pre-flight); #28/M-8 (exact ROM-size check). Prior 2026-06-28 audit noted `prepare_project` has no capacity check as part of the (now-resolved) auto-select-wiring finding.
- **Hardware ref**: `docs/MAPPER_MMC3_REFERENCE.md` §2 (per-window budgets `validate_segment_sizes` enforces); n/a for the flat-floor size check.
- **Suggested Fix**: Move (or mirror) the capacity pre-flight into `NESProjectBuilder.prepare_project()` and make the mapper argument effectively required for the size check (e.g. recover it from the `nes.cfg` marker inside `compile()` when `mapper is None`, the same way `run_compile` already does via `_prepared_mapper_name_from_cfg`).

---

## Dimensions with no findings

| # | Dimension | Result |
|---|-----------|--------|
| 1 | iNES header ↔ nes.cfg | Verified. NROM `$02`/32 KB single `PRG $8000`; MMC1 `$08`/128 KB (7×16 KB swap + 16 KB `PRGFIXED`); MMC3 `32`/512 KB (`MEMORY` regions sum to exactly 524,288). Mapper nibbles `$00`/`$10`/`$40` = 0/1/4. Headers inspected live. No mismatch. |
| 2 | Reset/NMI/IRQ vectors + 60 Hz NMI | `nmi`/`reset`/`irq` all defined in `main.asm`; `reset` enables NMI (`lda #$80`/`sta $2000`); `nmi` `jsr update_music`; `VECTORS` at `$FFFA`. Live vectors point into code for all 3 mappers; MMC1 lands at file `0x2000A` (no fixup, #213 holds). |
| 3 | APU init in boot path | Direct `init_music` writes `$4017`/`$4015` + sweep-off; bytecode `audio_init` writes `$4011`/`$4017`/`$4015`. Present on both paths. (`$4011` DAC zero missing only on direct path = open #348, out of scope.) |
| 4 | PRG capacity / overrun detection | `check_mapper_capacity` reached before `ld65` on both `prepare` and full-pipeline; MMC3 per-region + BANK/DPCM shared-bank summing (#212) and bank-count cap (#127) correct; `estimate_segment_sizes` handles `.align`/bounded `.incbin`, and real generated `music.asm` has no string `.byte`/multi-directive under-count. (Library-bypass gap → MAP-2026-07-19-3.) |
| 5 | Bank-switching correctness | MMC1 5-write `$0C`→Mode 3 / `$E000` serial matches doc; MMC3 `$46`/`$47` mode-1 R6/R7, R6→`$C000`, R7→`$A000` (`fetch_sequence_byte` `and #$1F`/`ora #$A0`), `$E000` IRQ off; `PRG_80`/`PRG_FIX` physical-bank order (#291) — MMC3 ROM builds and validates. |
| 6 | MapperFactory auto-selection | Ordering smallest-first; bytecode/bank-pack/DPCM force+reject guards raise cleanly. Two gaps found → MAP-2026-07-19-1, -2. |
| 7 | Project builder writes buildable project | Every segment used in `main.asm`/`music.asm` exists in the active `nes.cfg` and vice-versa; single `HEADER` owner (exporter standalone / builder non-standalone); all 3 mappers link. |
| 8 | Compiler validation & CC65 surfacing | `validate_project` runs first; `assemble`/`link` raise `CompilationError` with stderr on nonzero exit; `check_toolchain`/`get_version` probe resolved paths with guards (#14); `compile_rom` prints traceback under `--verbose` (#32); `_run_post_process` `shell=True` runs static text only, no mapper currently returns commands. #316 relative-path bug confirmed FIXED. |
| 9 | ROM size check | Exact per-mapper check (`prg_rom_size + 16`) verified live: 32,784 / 131,088 / 524,304 bytes. (Library `mapper=None` flat-floor fallback → MAP-2026-07-19-3.) |
| 10 | Default-mapper doc drift | Clean — `CLAUDE.md`/`README.md`/`docs/*.md` consistently describe MMC3 as default, MMC1/NROM selectable. No source/auto disagreement. |

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_MAPPERS_2026-07-19.md
```
