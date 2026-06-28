---
description: "Audit NES mappers, project builder, and CC65 ROM compilation"
argument-hint: "[--focus <dims>]"
---

# Mapper / Project-Builder / Compiler Audit

Audit the subsystem that turns generated music data into a buildable, bootable NES
ROM: the mapper abstraction (`mappers/`), the project builder (`nes/project_builder.py`),
and the CC65 compile path (`compiler/`). This is a correctness audit — the output is a
binary that must boot on hardware, so the bar is high: a wrong header byte, a stale
vector, or an undetected PRG overrun ships a broken ROM.

Shared protocol (layout, dedup, finding format): `.claude/commands/_audit-common.md`.
Severity definitions and the NES-hardware floors: `.claude/commands/_audit-severity.md`.
Do not restate them here. For any claim about mapper registers, bank windows, or iNES
header bytes, cite `docs/MAPPER_MMC1_REFERENCE.md` or `docs/MAPPER_MMC3_REFERENCE.md`
rather than asserting from memory — re-read the relevant section before reporting.

Reminder from `_audit-common.md`: the `prepare` stage writes `main.asm`/`music.asm`/`nes.cfg`
plus a build script, and `compile` runs `ca65`/`ld65` then checks a minimum ROM size.
Per `CLAUDE.md`, `prepare` and `run_full_pipeline` default to **MMC3** — but verify that
against the code, and treat any doc that still says MMC1 as drift (Dimension 10).

## Parameters (from $ARGUMENTS)
- `--focus <dims>` — comma-separated dimension numbers (e.g. `--focus 4,8`). Default: all.

## Extra Per-Finding Field
- **Dimension**: one of the 10 below.
- **Hardware ref**: the `docs/MAPPER_*.md` section backing any header/bank/register claim.

## Dimensions

### Dimension 1: iNES header ↔ nes.cfg consistency
For each of `mappers/nrom.py`, `mappers/mmc1.py`, `mappers/mmc3.py`, cross-check
`generate_header_asm()` against `generate_linker_config()` and the `prg_rom_size` /
`prg_bank_size` / `prg_bank_count` properties from `mappers/base.py`:
- PRG-ROM count in the header byte must equal the total PRG region size in the linker
  `MEMORY` block. NROM declares `$02` (2×16KB = 32KB) and a single `PRG` of `$8000`;
  MMC1 declares `$08` (8×16KB = 128KB) split into `PRGSWAP` `$1C000` + `PRGFIXED` `$4000`
  (112KB + 16KB); MMC3 declares `32` (×16KB = 512KB) across 64×`$2000` banks.
  Add the `MEMORY` region sizes and confirm they equal `prg_rom_size`.
- The mapper-number nibble in the header flags byte must equal `mapper_number`
  (NROM `$00`→0, MMC1 `$10`→1, MMC3 `$40`→4; the mapper low nibble lives in the high
  nibble of flags-6 — confirm against `docs/MAPPER_MMC3_REFERENCE.md`).
- A header that claims a different mapper or PRG size than `nes.cfg` is **HIGH**
  (`_audit-severity.md`: "Mapper header / `nes.cfg` mismatch").

### Dimension 2: reset/NMI/IRQ vectors and the 60Hz NMI music call
The reset/NMI/IRQ vectors at **$FFFA–$FFFF** must point at real code. Read the
`.segment "VECTORS"` block emitted by `_generate_main_asm()` in
`nes/project_builder.py` (the `.word nmi / .word reset / .word irq` triple) and confirm:
- All three labels (`nmi`, `reset`, `irq`) are defined in the same `main.asm`.
- `reset` ends by enabling NMI (`lda #$80 / sta $2000`) so the handler actually fires,
  and the `nmi` handler calls `jsr update_music` once per frame (the 60Hz tick — see
  `_audit-common.md` "Playback runs at 60 FPS via NMI").
- In the linker config the `VECTORS` segment loads at exactly `start = $FFFA` and the
  preceding code region (NROM/MMC1 `PRGFIXED`, MMC3 `PRG_FIX` ending `$FFF9`) does not
  overlap it. A missing label, an NMI that never calls `update_music`, or vectors that
  don't land at `$FFFA` is **CRITICAL** (bad vectors).
- MMC1 only: `generate_post_process_commands()` rewrites 6 bytes from `0xFFFA` to file
  offset `0x2000A` after link. Verify that offset is the fixed-bank tail of the 128KB
  image and that the copy actually lands the vectors where the CPU reads them — a wrong
  offset here silently bricks the ROM (CRITICAL). Note this fixup runs only via the
  mapper build script, not the `compiler/` path (cross-ref Dimension 8).

### Dimension 3: APU initialization in the boot path
A ROM whose APU is never initialized produces no/garbage sound and can leave channels in
an undefined state. Trace the boot path: `reset` → `jsr init_music`. Confirm that the
emitted code (in `music.asm` from the exporter, or the engine appended in
`nes/project_builder.py`) writes the APU enable register **$4015** and the frame-counter
register **$4017** before playback. The DPCM play path in `prepare_project()` writes
`$4010`/`$4012`/`$4013`/`$4015` — verify channel enables aren't left disabled after init.
Missing APU init is **CRITICAL** per `_audit-severity.md`. Cite `docs/NES_APU_REFERENCE.md`
for the register map and `docs/APU_FRAME_COUNTER_REFERENCE.md` for $4017.

### Dimension 4: PRG capacity / overrun detection (the central risk)
`mappers/base.py` defines `get_data_capacity()` and `can_fit_data()`, and
`mappers/factory.py` exposes `auto_select()` / `get_mapper("auto", data_size=...)`. The
question is whether music data that **exceeds** a mapper's PRG capacity is *detected*
before linking, or silently truncated/overrun.
- `grep -rn --include='*.py' 'can_fit_data\|auto_select\|get_data_capacity' .` and check
  whether any **pipeline** caller (not just `mappers/` internals or tests) actually
  invokes them. If `nes/project_builder.py` / `main.py` build a project with a fixed
  mapper and never size-check the music data, oversized data flows straight to `ld65`.
- Confirm what happens on overflow: does `ld65` error (caught by Dimension 8), or does
  `fillval`/region truncation hide it? Undetected overrun = **CRITICAL**
  (`_audit-severity.md`: "Music data overruns the mapper's PRG capacity silently").
- Sanity-check the capacity numbers themselves: NROM `get_data_capacity()` returns 30KB
  against a 32KB ROM; the base default subtracts a flat 2048 bytes for code+vectors.
  Flag a capacity that doesn't leave room for the actual code/engine size as MEDIUM.

### Dimension 5: bank-switching correctness (MMC1 / MMC3)
Re-derive the bank-switch sequences against the reference docs:
- MMC1 `generate_init_code()` / `generate_bank_switch_code()` use the 5-write serial
  load (`sta $8000`…) with `lsr a` shifting one bit per write into the control/bank
  registers. Confirm the write count, the target register address, and the control value
  (`$0C` = 16KB PRG mode, fixed high bank) against `docs/MAPPER_MMC1_REFERENCE.md`. A
  wrong write count or address leaves the mapper in an undefined state (CRITICAL if it
  affects the bank holding running code).
- MMC3 `generate_init_code()` selects bank registers via `$8000`/`$8001` (R6 `$46`,
  R7 `$47`) and `generate_bank_switch_code()` defines `switch_dpcm_bank`. Confirm the
  PRG mode bit, that R6/R7 map the windows the engine actually reads
  (`$C000-$DFFF` DPCM, `$A000-$BFFF` sequence — see `fetch_sequence_byte` in
  `nes/project_builder.py`), and that `sta $E000` disables the MMC3 IRQ. Cross-check
  against `docs/MAPPER_MMC3_REFERENCE.md`.
- Verify the `nes.cfg` bank layout matches: MMC3 maps banks 0–59 all at `start = $C000`
  (so addresses resolve in the swap window) and the last four at `$8000`/`$A000`/`$C000`/`$E000`
  — confirm this matches how the engine swaps and reads.

### Dimension 6: MapperFactory auto-selection
In `mappers/factory.py`, `auto_select(data_size)` walks `_default_mappers`
(`nrom`→`mmc1`→`mmc3`) and returns the first whose `can_fit_data()` is true; the
`get_mapper("auto", data_size=0)` convenience falls back to MMC1 when no size is given.
Check: the ordering is genuinely smallest-first by capacity; the "nothing fits" branch
raises with the largest mapper's capacity; the `data_size <= 0` → MMC1 default is
intentional (and note it conflicts with the MMC3 default used elsewhere — Dimension 10).
A threshold that picks a mapper too small for the data (so it overruns) ties back to
Dimension 4 and is CRITICAL.

### Dimension 7: project builder writes a consistent, buildable project
`NESProjectBuilder.prepare_project()` (`nes/project_builder.py`) must emit a set of files
`ld65` can actually link with the chosen mapper:
- `nes.cfg` comes from `self.mapper.generate_linker_config()`; `main.asm` interpolates
  `self.mapper.generate_header_asm()` / `generate_init_code()` / `generate_bank_switch_code()`.
  Confirm every segment the asm uses (`HEADER`, `ZEROPAGE`, `CODE`, `RODATA`, `BSS`, `OAM`,
  `VECTORS`, the `DPCM_*` segments) exists in that mapper's `nes.cfg`, and vice-versa.
- `_generate_main_asm()` already opens `.segment "HEADER"` before interpolating the
  header. Check each mapper's `generate_header_asm()`: NROM/MMC1 emit bare `.byte`
  directives (correct), but `mappers/mmc3.py` `generate_header_asm()` *also* emits its own
  `.segment "HEADER"` — a double segment declaration for the **default** mapper. Verify
  whether `ca65` accepts or rejects this, and whether the header bytes land correctly.
- ZP/BSS variable definitions vs `.importzp`/`.global` declarations must match between
  `main.asm` and `music.asm` (e.g. `sequence_ptr`, `sequence_bank`, `frame_counter`,
  `switch_dpcm_bank`). An undefined symbol surfaces only at link time. A project that
  cannot link is at least HIGH.

### Dimension 8: compiler validation & CC65 error surfacing
`compiler/compiler.py` (`ROMCompiler.validate_project` / `compile`) and
`compiler/cc65_wrapper.py` (`CC65Wrapper.assemble` / `link` / `check_toolchain`):
- `validate_project()` requires `main.asm`, `music.asm`, `nes.cfg`. Confirm it actually
  runs before assembly and that the missing-file list is accurate.
- `assemble()` and `link()` must check `result.returncode != 0` and raise
  `CompilationError` carrying `stderr`. A swallowed nonzero exit reported as success is
  **HIGH** (`_audit-severity.md`: "CC65 nonzero exit / stderr ignored"). Verify stderr is
  not discarded and that `compile_rom()`'s broad `except Exception` in `compiler.py`
  prints rather than silently returns success.
- `check_toolchain()` must detect missing `ca65`/`ld65` (`shutil.which` + `--version`)
  and raise `ToolchainError` rather than letting a later `FileNotFoundError` mask it.
- Note the build-script path divergence: `nes/project_builder.py` always calls
  `_create_build_script_mmc3()` (a hardcoded MMC3 script), so `mapper.generate_build_script()`
  and the MMC1 vector fixup (Dimension 2) are bypassed for projects built via `build.sh`
  rather than `compiler/`. Flag the inconsistency between the two compile paths.

### Dimension 9: MIN_ROM_SIZE check
`ROMCompiler.MIN_ROM_SIZE = 32768` and `compile()` rejects a linked ROM smaller than it.
Verify: the threshold matches the smallest legitimate output (NROM is exactly 32KB PRG +
16-byte header = 32784 bytes, so a successfully linked NROM ROM is *larger* than 32768 —
confirm the check can't false-positive on a valid NROM, and can't false-pass a truncated
MMC1/MMC3 image that is ≥32768 but far smaller than its declared PRG size). A size check
that passes a truncated 512KB-declared ROM is a MEDIUM gap (it should compare against the
mapper's expected `prg_rom_size`, not a flat constant).

### Dimension 10: default-mapper doc drift
The codebase has *three* different "defaults": `main.py:run_prepare` and
`run_full_pipeline` instantiate `MMC3Mapper()` explicitly; `NESProjectBuilder.__init__`
defaults `mapper_name="auto"`; and `get_mapper("auto", data_size=0)` falls back to MMC1.
Reconcile these against the docs:
- `CLAUDE.md` line 31/160 say MMC3; `CLAUDE.md` line 194 still says "Always use MMC1".
- The README and `docs/MAPPER_MMC1_REFERENCE.md` may still describe MMC1 as the always-on
  mapper. `grep -niE 'always use mmc1|default.*mapper|mmc1' README.md CLAUDE.md docs/*.md`.
Each contradiction between code and a `docs/*.md` is doc-rot (LOW), but the fact that the
auto-default (MMC1) disagrees with the hardcoded pipeline default (MMC3) is a real
behavioral trap worth MEDIUM if a caller relies on `mapper_name="auto"`.

## Skeptical checklist (run before writing each finding)
- [ ] Sum the `nes.cfg` `MEMORY` regions — do they equal `prg_rom_size`? Does the header PRG byte agree?
- [ ] Does the mapper-number nibble in the header equal `mapper_number`? (cite the doc)
- [ ] Are `nmi`/`reset`/`irq` all defined, and does `nmi` `jsr update_music`?
- [ ] Does `reset` enable NMI (`sta $2000`) and init the APU ($4015/$4017) via `init_music`?
- [ ] Is `can_fit_data`/`auto_select` ever called on a real pipeline path, or only in tests/factory?
- [ ] On overflow, does `ld65` error (and is that error surfaced) or is data silently dropped?
- [ ] Do MMC1's 5-write loads and MMC3's R6/R7 selects match `docs/MAPPER_*.md`?
- [ ] Do `assemble`/`link` raise on nonzero return code with stderr attached?
- [ ] Does every segment used in `main.asm`/`music.asm` exist in the active mapper's `nes.cfg`?
- [ ] Did I try to disprove the finding by re-reading the code path?

## Output
Write the report to **`docs/audits/AUDIT_MAPPERS_<TODAY>.md`** (replace `<TODAY>` with
today's date, `YYYY-MM-DD`). Structure:
1. **Summary** — finding counts by severity, the highest-leverage fix, and a one-line
   verdict on whether the default-mapper pipeline produces a bootable ROM.
2. **Findings** — base format from `_audit-common.md` plus `Dimension` and `Hardware ref`,
   ordered by severity (CRITICAL first).

Then suggest:
```
/audit-publish docs/audits/AUDIT_MAPPERS_<TODAY>.md
```
