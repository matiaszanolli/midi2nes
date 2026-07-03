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

This subsystem went through a heavy bug-fixing pass recently (mapper default resolution,
capacity pre-flight, header/segment fixes, CC65 subprocess hardening, build-script
routing). Several dimensions below now describe *fixed* behavior — the instruction in
each case is to verify the fix is complete and hunt for edge cases it doesn't cover,
not to re-report the original bug.

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
  (112KB + 16KB); MMC3 declares `32` (×16KB = 512KB) across 60 swap banks (`PRG_BANK_00..59`,
  `$2000` each) plus `PRG_80`/`PRG_A0`/`PRG_C0`/`PRG_FIX` (the fixed last 4×8KB).
  Add the `MEMORY` region sizes and confirm they equal `prg_rom_size`.
- The mapper-number nibble in the header flags byte must equal `mapper_number`
  (NROM `$00`→0, MMC1 `$10`→1, MMC3 `$40`→4; the mapper low nibble lives in the high
  nibble of flags-6 — confirm against `docs/MAPPER_MMC3_REFERENCE.md`).
- A header that claims a different mapper or PRG size than `nes.cfg` is **HIGH**
  (`_audit-severity.md`: "Mapper header / `nes.cfg` mismatch").

### Dimension 2: reset/NMI/IRQ vectors and the 60Hz NMI music call
The reset/NMI/IRQ vectors at **$FFFA–$FFFF** must point at real code. Read the
`.segment "VECTORS"` block emitted by `_generate_main_asm()` in
`nes/project_builder.py` (the `.word nmi / .word reset / .word irq` triple, currently
around lines 642–646) and confirm:
- All three labels (`nmi`, `reset`, `irq`) are defined in the same `main.asm`.
- `reset` ends by enabling NMI (`lda #$80 / sta $2000`, `nes/project_builder.py:613-614`)
  so the handler actually fires, and the `nmi` handler calls `jsr update_music`
  (`nes/project_builder.py:629`) once per frame (the 60Hz tick — see `_audit-common.md`
  "Playback runs at 60 FPS via NMI").
- In the linker config the `VECTORS` segment loads at exactly `start = $FFFA` and the
  preceding code region (NROM/MMC1 `PRGFIXED`, MMC3 `PRG_FIX` ending `$FFF9`) does not
  overlap it. A missing label, an NMI that never calls `update_music`, or vectors that
  don't land at `$FFFA` is **CRITICAL** (bad vectors). Commit `2d9c8dc` ("make the
  default pipeline assemble, link, and boot", #5/#7/#39) fixed the default (MMC3,
  patterns-on) path specifically — verify it still boots and hasn't regressed.
- MMC1 only: `generate_post_process_commands()` (`mappers/mmc1.py:116-120`) rewrites 6
  bytes from `0xFFFA` to file offset `0x2000A` after link. Verify that offset is the
  fixed-bank tail of the 128KB image and that the copy actually lands the vectors where
  the CPU reads them — a wrong offset here silently bricks the ROM (CRITICAL). This
  fixup now runs whenever `nes/project_builder.py`'s `_create_build_script()`
  (line 648) generates `build.sh`/`build.bat`, because it calls
  `self.mapper.generate_build_script()` for every mapper (fixed by #18, see Dimension 8).
  It still does **not** run via the `compiler/` path (`compiler/compiler.py`'s
  `ROMCompiler.compile()` never calls `generate_post_process_commands()`) — cross-ref
  Dimension 8 for the surviving gap.

### Dimension 3: APU initialization in the boot path
A ROM whose APU is never initialized produces no/garbage sound and can leave channels in
an undefined state. Trace the boot path: `reset` → `jsr init_music`. Both export paths
now write **$4015** and **$4017** before playback (fixed by #7, part of `2d9c8dc`) —
verify this still holds and check for paths that might bypass it:
- Direct/table export (`--no-patterns`): `exporter/exporter_ca65.py`'s `init_music`
  (around lines 756-768) writes `lda #$40 / sta $4017` (frame counter mode 1, IRQ off)
  and `lda #$0F / sta $4015` (enable all 4 channels), plus disables the pulse sweep
  units (`$4001`/`$4005`).
- Bytecode export: `init_music` jumps to `audio_init` (`nes/audio_engine.asm`, around
  lines 90-138), which performs the equivalent `$4017`/`$4015` writes before returning.
- The DPCM play path (`seq_cmd_dpcm_play` in `nes/project_builder.py`, ~lines 138-160)
  writes `$4010`/`$4012`/`$4013` then toggles `$4015` (disable-then-enable-with-DMC) to
  trigger playback — verify channel enables aren't left disabled after the trigger.
- Missing APU init on any of these paths is **CRITICAL** per `_audit-severity.md`. Cite
  `docs/NES_APU_REFERENCE.md` for the register map and `docs/APU_FRAME_COUNTER_REFERENCE.md`
  for $4017.

### Dimension 4: PRG capacity / overrun detection (the central risk)
This is now a wired pre-flight, not an open question — verify completeness and look for
gaps it doesn't cover (#11, #126, #127, all fixed).
- `main.py:check_mapper_capacity()` (~lines 145-163) calls
  `mapper.validate_segment_sizes(estimate_segment_sizes(music_asm_path))` and raises
  `ValueError` (caught and turned into a clean exit) before any project files are
  written. It is invoked from `run_prepare()` (~line 246) and from the full pipeline
  (~line 690), in both cases *before* `NESProjectBuilder.prepare_project()` runs.
- `BaseMapper.validate_segment_sizes()` (`mappers/base.py:161-178`) is a flat
  total-vs-`get_data_capacity()` check — correct for NROM/MMC1, which don't distribute
  data across banks. `MMC3Mapper.validate_segment_sizes()` (`mappers/mmc3.py:171-222`)
  overrides it to size each region separately: `RODATA`+`CODE` against the `PRG_FIX`
  budget, `CODE_8000` against the 8KB `$8000` window, and each `BANK_NN`/`DPCM_NN`
  against the 8KB bank size plus a check that no bank index exceeds `SWAP_BANK_COUNT`
  (60) — this closes the "no cap on bank count" gap (#127).
- Remaining things to verify on each audit:
  - `estimate_segment_sizes()` (`main.py:93-...`) is a **text-scan heuristic** (regex
    counts over `.byte`/`.word`/`.incbin` per active `.segment`), not a real assembly.
    Check it can't systematically *under*-count (e.g. multi-directive lines, macros that
    expand to more bytes than one `.byte`/`.word` per line) in a way that lets an
    oversized song pass the pre-flight and hit a raw `ld65` region-overflow instead —
    `ld65` remains the correctness backstop, but a misleading pre-flight message is at
    least MEDIUM.
  - The capacity gate lives entirely in `main.py` (the CLI layer). Confirm
    `NESProjectBuilder.prepare_project()` itself (`nes/project_builder.py`) does **not**
    call `validate_segment_sizes`/`check_mapper_capacity` — a caller using
    `NESProjectBuilder` as a library directly (bypassing `main.py`) gets no pre-flight
    and relies solely on `ld65` erroring at link time. Flag as a defense-in-depth gap
    (MEDIUM) rather than a silent-overrun risk, since `ld65` still errors on overflow.
  - Sanity-check the capacity numbers themselves: NROM `get_data_capacity()`
    (`mappers/nrom.py:67-69`) returns 30KB against a 32KB ROM; `BaseMapper`'s default
    (`mappers/base.py:140-147`) subtracts a flat 2048 bytes for code+vectors. Flag a
    capacity that doesn't leave room for the actual code/engine size as MEDIUM.
- Do not confuse this pre-flight with `can_fit_data()`/`auto_select()` — see Dimension 6;
  those are a separate mechanism not called from this path.

### Dimension 5: bank-switching correctness (MMC1 / MMC3)
Re-derive the bank-switch sequences against the reference docs:
- MMC1 `generate_init_code()` (`mappers/mmc1.py:75-100`) uses the 5-write serial
  load (`sta $8000`…) with `lsr a` shifting one bit per write into the control/bank
  registers. Confirm the write count, the target register address, and the control value
  (`$0C` = 16KB PRG mode, fixed high bank) against `docs/MAPPER_MMC1_REFERENCE.md`. A
  wrong write count or address leaves the mapper in an undefined state (CRITICAL if it
  affects the bank holding running code).
- MMC3 `generate_init_code()` (`mappers/mmc3.py:103-123`) selects bank registers via
  `$8000`/`$8001` (R6 `$46`, R7 `$47`) and `generate_bank_switch_code()` (lines 125-141)
  defines `switch_dpcm_bank`. Confirm the PRG mode bit, that R6/R7 map the windows the
  engine actually reads (`$C000-$DFFF` DPCM, `$A000-$BFFF` sequence — see
  `fetch_sequence_byte` in `nes/project_builder.py` ~lines 199-231), and that
  `sta $E000` disables the MMC3 IRQ. Cross-check against `docs/MAPPER_MMC3_REFERENCE.md`.
- Verify the `nes.cfg` bank layout matches (`mappers/mmc3.py:50-101`): MMC3 maps banks
  0–59 all at `start = $C000` (so addresses resolve in the swap window) and the last
  four at `$8000`/`$A000`/`$C000`/`$E000` — confirm this matches how the engine swaps
  and reads.

### Dimension 6: MapperFactory auto-selection
In `mappers/factory.py`, `auto_select(data_size)` (lines 83-114) walks `_default_mappers`
(`nrom`→`mmc1`→`mmc3`) and returns the first whose `can_fit_data()` is true; the
module-level `get_mapper("auto", data_size=0)` (lines 161-177) falls back to MMC3 when
no size is given, deliberately matching the pipeline's hardcoded default (fixed by #25,
commit `573890e`; remaining doc-rot cleaned up by #43/#44, commit `ab6f95d`).
Check on each audit:
- The ordering is genuinely smallest-first by capacity; the "nothing fits" branch
  raises with the largest mapper's capacity.
- **Neither `auto_select()` nor `can_fit_data()` is actually called from any `main.py`
  pipeline path.** `run_prepare()` and the full pipeline both instantiate
  `MMC3Mapper()` directly (`main.py:244`, `main.py:685`), bypassing
  `NESProjectBuilder`'s own `mapper_name="auto"` default entirely. The only place the
  `get_mapper("auto", 0)` → MMC3 fallback is exercised is if `NESProjectBuilder` is
  constructed without an explicit mapper and without ever calling
  `auto_select_mapper(data_size)` — which nothing in `main.py` does. This isn't a
  correctness bug (the hardcoded default and the auto-fallback happen to agree), but
  flag it as LOW/tech-debt: the size-based auto-selection machinery is effectively
  unreachable from the CLI and only exercised by `mappers/` unit tests.
- A threshold that picks a mapper too small for the data (so it overruns) ties back to
  Dimension 4 and is CRITICAL — but note this can only happen via direct library use of
  `auto_select()`/`auto_select_mapper()`, not via any current CLI path.

### Dimension 7: project builder writes a consistent, buildable project
`NESProjectBuilder.prepare_project()` (`nes/project_builder.py:75-544`) must emit a set
of files `ld65` can actually link with the chosen mapper:
- `nes.cfg` comes from `self.mapper.generate_linker_config()`; `main.asm` interpolates
  `self.mapper.generate_header_asm()` / `generate_init_code()` / `generate_bank_switch_code()`.
  Confirm every segment the asm uses (`HEADER`, `ZEROPAGE`, `CODE`, `RODATA`, `BSS`, `OAM`,
  `VECTORS`, `CODE_8000`, the `DPCM_*`/`BANK_*` segments) exists in that mapper's
  `nes.cfg`, and vice-versa. The default (MMC3, patterns-on) pipeline now assembles,
  links, and boots end-to-end (#5/#7/#39, `2d9c8dc`) — re-verify this holds rather than
  re-deriving it from scratch each time.
- `mappers/mmc3.py`'s `generate_header_asm()` (lines 38-48) now emits **bare** `.byte`
  directives only, matching the NROM/MMC1 contract — the previous double
  `.segment "HEADER"` declaration is fixed (#22, commit `007f5c4`). One loose end: the
  *standalone*-export path in `exporter/exporter_ca65.py:108-112` still guards with
  `if '.segment "HEADER"' not in header_asm: lines.append('.segment "HEADER"')`, and the
  adjacent comment ("MMC3 embeds its own `.segment "HEADER"`; NROM/MMC1 don't.",
  `exporter/exporter_ca65.py:109`) now describes behavior no longer true for MMC3 — the
  branch is harmless (it still emits the segment correctly for every mapper) but the
  comment is stale doc-rot (LOW).
- ZP/BSS variable definitions vs `.importzp`/`.global` declarations must match between
  `main.asm` and `music.asm` (e.g. `sequence_ptr`, `sequence_bank`, `frame_counter`,
  `switch_dpcm_bank`). An undefined symbol surfaces only at link time. A project that
  cannot link is at least HIGH.

### Dimension 8: compiler validation & CC65 error surfacing
`compiler/compiler.py` (`ROMCompiler.validate_project` / `compile`) and
`compiler/cc65_wrapper.py` (`CC65Wrapper.assemble` / `link` / `check_toolchain` /
`get_version`):
- `validate_project()` (`compiler/compiler.py:39-65`) requires `main.asm`, `music.asm`,
  `nes.cfg`. Confirm it actually runs before assembly and that the missing-file list is
  accurate.
- `assemble()` (`compiler/cc65_wrapper.py:119-173`) and `link()` (lines 175-236) check
  `result.returncode != 0` and raise `CompilationError` carrying `stderr`. This is
  correct today — verify it stays that way.
- `check_toolchain()` (`compiler/cc65_wrapper.py:34-81`) and `get_version()`
  (lines 83-117) now resolve `ca65`/`ld65` via `shutil.which()` first and probe
  `--version` on the **resolved path**, not the bare command name, with a
  `try/except (FileNotFoundError, subprocess.TimeoutExpired)` guard around each
  `subprocess.run` (fixed by #14, commit `48da1ea`) — verify a vanished/renamed binary
  between the `which()` check and the probe still raises `ToolchainError` cleanly rather
  than an uncaught exception.
- `compile_rom()`'s broad `except Exception` (`compiler/compiler.py:173-175`) still just
  prints `f"[ERROR] Compilation failed: {e}"` and returns `False` — no traceback, and
  this is independent of any `verbose` flag (`run_compile()` at `main.py:230` and the
  full pipeline at `main.py:704` both call `compile_rom(project_path, output_rom)` with
  no `verbose` argument at all). This is **still open** (#32): a non-`CompilationError`/
  `ValidationError` exception (e.g. a bug in the compiler itself) is swallowed to a
  one-line message with no stack trace, even with `--verbose`. HIGH per
  `_audit-severity.md` ("CC65 nonzero exit / stderr ignored" is the closest floor; here
  it's the *wrapper* masking an unexpected exception, not CC65 itself).
- Build-script routing is fixed (#18, commit `e68866a`): `nes/project_builder.py`'s
  `_create_build_script()` (line 648) now calls `self.mapper.generate_build_script(is_windows)`
  for every mapper — the previous hardcoded `_create_build_script_mmc3()` no longer
  exists, so MMC1's `generate_post_process_commands()` vector fixup (Dimension 2) does
  run via `build.sh`/`build.bat`. The gap that survives: `compiler/compiler.py`'s
  `ROMCompiler.compile()` (lines 67-146) never calls `generate_post_process_commands()`
  at all — it only assembles, links, and size-checks. A project built with a mapper
  that needs a post-link fixup (currently only MMC1) and compiled via
  `compiler.compile_rom()`/`main.py compile` instead of running `build.sh` ships without
  the fixup. This is unreachable from the CLI today (no `--mapper` flag exists;
  `prepare`/the full pipeline hardcode `MMC3Mapper()`, which needs no fixup — Dimension 2),
  but is a real latent bug for the public `NESProjectBuilder(mapper_name="mmc1")` +
  `compiler.compile_rom()` API combination. Flag as HIGH/CRITICAL if exercised (bricks
  the ROM's vectors), and recommend `ROMCompiler.compile()` call
  `self.mapper.generate_post_process_commands()` (needs a mapper reference passed in)
  after linking so both compile paths stay in sync.
- Cross-reference (not owned by this audit, but undermines confidence in the above):
  REG-10 (#128, open) — the ROM-compile integration tests in
  `tests/test_rom_validation_integration.py` (e.g. ~lines 95-100, 150-153, 202-205,
  257-259, 332-335) `pytest.skip()` whenever `compile_rom()` raises or returns falsy,
  instead of failing. A regression in any of the fixes above (including the MMC1
  post-process gap) can land without CI catching it. See `/audit-regression`.

### Dimension 9: MIN_ROM_SIZE check
`ROMCompiler.MIN_ROM_SIZE = 32768` (`compiler/compiler.py:27`) and `compile()`
(lines 133-138) rejects a linked ROM smaller than it. Still open (#28): verify the
threshold matches the smallest legitimate output (NROM is exactly 32KB PRG + 16-byte
header = 32784 bytes, so a successfully linked NROM ROM is *larger* than 32768 —
confirm the check can't false-positive on a valid NROM), and that it can't false-pass a
truncated MMC1/MMC3 image that is ≥32768 bytes but far smaller than its declared PRG
size (MMC1 declares 128KB+16, MMC3 declares 512KB+16). A size check that passes a
truncated 512KB-declared ROM is a MEDIUM gap (it should compare against the selected
mapper's `prg_rom_size` + 16, not a flat constant — note `ROMCompiler.compile()` doesn't
currently have a mapper reference to compare against, so fixing this needs threading one
through).

### Dimension 10: default-mapper doc drift
The codebase's "defaults" agree on MMC3: `main.py:run_prepare` (line 244) and
`run_full_pipeline` (line 685) instantiate `MMC3Mapper()` explicitly; `NESProjectBuilder.__init__`
defaults `mapper_name="auto"`; and `get_mapper("auto", data_size=0)` falls back to MMC3
(`mappers/factory.py:172-177`). This conflict was resolved by #25 (commit `573890e`) and
remaining doc mentions cleaned up by #43/#44 (commit `ab6f95d`). Re-check on each audit
rather than trusting this is permanent:
- `grep -niE 'always use mmc1|default.*mapper|mmc1' README.md CLAUDE.md docs/*.md`. As of
  this pass, `CLAUDE.md` and `README.md` consistently describe MMC3 as the pipeline
  default with MMC1/NROM as selectable; the only other `mmc1` hits are legitimate
  (MMC1 register/bank-switch reference docs, an SRAM aside in
  `docs/2A03_CPU_REFERENCE.md`, and DPCM docs noting MMC1 as *a* capable mapper choice) —
  none reassert MMC1 as *the* default.
- Any code path or `docs/*.md` that reasserts MMC1 as *the* default is doc-rot (LOW); a
  real auto-vs-pipeline default *disagreement* (were one reintroduced — e.g. if
  `main.py` stopped passing an explicit mapper, or `get_mapper("auto", 0)` changed its
  fallback) would be MEDIUM.

## Skeptical checklist (run before writing each finding)
- [ ] Sum the `nes.cfg` `MEMORY` regions — do they equal `prg_rom_size`? Does the header PRG byte agree?
- [ ] Does the mapper-number nibble in the header equal `mapper_number`? (cite the doc)
- [ ] Are `nmi`/`reset`/`irq` all defined, and does `nmi` `jsr update_music`?
- [ ] Does `reset` enable NMI (`sta $2000`) and init the APU ($4015/$4017) via `init_music`/`audio_init`?
- [ ] Is `check_mapper_capacity()`/`validate_segment_sizes()` actually reached before `ld65` runs on both the `prepare` and full-pipeline paths? Does it run at all when `NESProjectBuilder` is used directly, bypassing `main.py`?
- [ ] Are `can_fit_data()`/`auto_select()` reached from any real pipeline path, or only from `mappers/` tests? (Verified answer as of this pass: only tests — see Dimension 6.)
- [ ] On a capacity overflow, does the pre-flight message name the right region, and does `ld65` still error if the heuristic under-counts?
- [ ] Do MMC1's 5-write loads and MMC3's R6/R7 selects match `docs/MAPPER_*.md`?
- [ ] Do `assemble`/`link` raise on nonzero return code with stderr attached? Does `compile_rom()`'s broad `except Exception` still swallow a traceback?
- [ ] Does every segment used in `main.asm`/`music.asm` exist in the active mapper's `nes.cfg`?
- [ ] Does `compiler/compiler.py`'s `ROMCompiler.compile()` invoke `generate_post_process_commands()` for mappers that need a post-link fixup (MMC1), or only `build.sh` does?
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
