# Audit: Mappers / Project Builder / Compiler — 2026-08-21

Subsystem audited: `mappers/` (base, factory, nrom, mmc1, mmc3, capacity),
`nes/project_builder.py`, `nes/audio_engine.asm` (boot/NMI/jukebox paths),
`compiler/compiler.py`, `compiler/cc65_wrapper.py`, and the `main.py`
`--mapper` resolution / capacity pre-flight / `run_prepare` / `run_compile` /
`run_full_pipeline` / `run_song_build` call sites. All 10 SKILL.md dimensions
covered; no `--focus` restriction. Audited tree: `master` at HEAD `949f0c6`.

**Delta since the last mapper audit (2026-08-07, HEAD `f4c2283`):** `mappers/`
and `compiler/` are untouched (`git diff --stat f4c2283..HEAD`). The changed
audit-relevant code is `exporter/exporter_ca65.py` (+15), `nes/project_builder.py`
(+48/−17), and `nes/song_bank.py` (docstring only) — all from `8ea7ac3`
("song build works for any bank size"), which claims to fix both findings the
2026-08-07 pass filed. This pass verified both fixes empirically (real
`ca65`/`ld65` builds, `ld65 -Ln` label inspection) and re-verified every
previously-fixed behavior the SKILL.md flags for re-checking.

**Method:** every claim re-derived from live source; register/bank claims
cite `docs/MAPPER_MMC1_REFERENCE.md` / `docs/MAPPER_MMC3_REFERENCE.md` (both
re-read this pass). Empirical evidence: live CC65 builds (ca65/ld65 at
`/usr/bin`) of a synthetic 1-song jukebox, a 46-bank 2-song jukebox, and an
MMC1 direct-export project, plus a live reproduction of the one NEW MEDIUM
finding via the real `main.py prepare` + `main.py compile` CLI. Scratch
artifacts under `/tmp/audit/mappers2026-08-21/`.

**Dedup basis:** `/tmp/audit/issues.json` + `/tmp/audit/issues_all.json`
(`gh issue list`, 304 issues, all states — only #2/#3 open, neither
mapper-related), all prior `docs/audits/AUDIT_MAPPERS_*.md`, and the six
sibling reports already written today (`AUDIT_{PIPELINE,NES_HARDWARE,
EXPORTERS,DPCM,ARRANGER,PATTERNS}_2026-08-21.md`). Findings this pass
independently confirmed but that a sibling already filed today are listed
under "Cross-audit dedup" below, not re-reported.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 1 |
| LOW      | 1 |
| **Total** | **2** |

**Highest-leverage fix:** MAP-2026-08-21-1 — make
`NESProjectBuilder.prepare_project` consult the jukebox marker already present
in a `export_song_bank_bytecode`-produced music.asm instead of relying solely
on the caller-supplied `song_count`, so the split `prepare`/`compile` flow
(and direct library callers) can't silently build a jukebox project that is
guaranteed to die at `ld65` with 8 unresolved externals.

**One-line verdict:** the default single-song pipeline (MMC3, patterns-on)
still produces a bootable, exact-size (524,304-byte) ROM with correct vectors
and APU init, and — new this pass — the `song build` jukebox route now works
end-to-end for both a 1-song and a multi-song bank: both 2026-08-07 findings
(MAP-2026-08-07-1 CRITICAL, MAP-2026-08-07-2 HIGH) are confirmed fixed in
`8ea7ac3`, with regression tests in place.

---

## Fix verification (2026-08-07 findings — both CLOSED, verified live)

- **MAP-2026-08-07-1 (CRITICAL, per-song `CODE_8000` reset): FIXED.**
  `_build_song_bytecode` now emits `.segment "CODE_8000"` itself immediately
  before the instrument table (`exporter/exporter_ca65.py:1330`), the exact
  "move it inside the function" variant the original finding suggested, so no
  caller-side segment state can strand a later song's tables in a `BANK_NN`
  segment. Live 2-song build (song 0 spanning ~46 banks): `ld65 -Ln` shows
  `song0_instrument_table` at `$8200` **and `song1_instrument_table` at
  `$823A`** — both inside `CODE_8000`/`PRG_80` (physical bank 62), where the
  jukebox `EVAL_MACRO` indirection reads them. `song_table_ptr_lo/hi/bank`
  land at `$8274`/`$827E`/`$8288`, also fixed-window. Regression test:
  `tests/test_ca65_export.py:694-731` asserts every song's tables sit in
  `CODE_8000`.
- **MAP-2026-08-07-2 (HIGH, `JUKEBOX_BUILD` gate `> 1`): FIXED.** Gate is now
  `song_count is not None` at both sites (`nes/project_builder.py:311`,
  `:354`). Live 1-song jukebox build assembles, links, and produces an
  exact-size 524,304-byte ROM. Regression tests: real 1-song compile/link at
  `tests/test_ca65_export.py:1202-1218`, gate check at
  `tests/test_nes_project_builder.py:562-573`.

## Findings

### MAP-2026-08-21-1: Split `prepare`/`compile` on a jukebox music.asm always fails at ld65 with 8 unresolved externals — the jukebox marker is in the file but `prepare_project` never consults it

- **Severity**: MEDIUM
- **Dimension**: 7 (project builder writes a consistent, buildable project)
- **Location**: `nes/project_builder.py:83-98` (`prepare_project` — jukebox
  mode is decided solely by the caller-supplied `song_count` parameter),
  `:107,122` (music.asm content is read and scanned for the `"MMC3 Macro
  Bytecode"` engine marker, but the jukebox variant of that same first line —
  `"MMC3 Macro Bytecode -- multi-song jukebox build"`,
  `exporter/exporter_ca65.py:1577` — is never distinguished), `main.py:608-640`
  (`run_prepare` calls `builder.prepare_project(args.input)` with no
  `song_count`)
- **Status**: NEW (no sibling report today and no prior audit covers the
  split-flow/jukebox combination; the fixed MAP-2026-08-07-2 was the
  `song build` route itself, which passes `song_count` correctly)
- **Description**: The repo's established pattern for the split
  `prepare`/`compile` flow is that everything needed to build correctly is
  recoverable from the artifacts themselves: the bytecode-engine marker forces
  MMC3 (`_requires_mmc3_bytecode_engine`), the bank-pack and DPCM markers
  force/reject mappers (#283, #362), and the nes.cfg mapper stamp makes
  `compile` self-sufficient (#297, #269). The jukebox attribute breaks this
  pattern: `export_song_bank_bytecode` stamps its own distinguishing marker
  into music.asm line 1 (`-- multi-song jukebox build`), but
  `prepare_project` decides `JUKEBOX_BUILD` purely from the `song_count`
  parameter only `run_song_build` passes. Running the documented
  `python main.py prepare <music.asm> <dir>` on a jukebox music.asm (or
  calling `prepare_project` as a library without `song_count`) therefore
  succeeds — capacity pre-flight passes, all files written, "Ready for CC65
  compilation!" — and the resulting project can never link: the engine's
  single-song branch references `pulse1_sequence`/`channel_start_banks`/
  `instrument_table`/`audio_init`-side labels the jukebox music.asm doesn't
  define.
- **Evidence**: Live reproduction at HEAD:
  ```
  $ python3 main.py prepare /tmp/audit/.../jb1/music.asm jb1_prep
    ✓ Music data 2,993 bytes fits the MMC3 PRG regions
   Prepared NES project -> jb1_prep      ← succeeds
  $ python3 main.py compile jb1_prep jb1_prep.nes
  Unresolved external 'pulse1_sequence' referenced in: ...audio_engine.asm(151,153)
  Unresolved external 'pulse2_sequence' ... 'triangle_sequence' ...
  ld65: Error: 8 unresolved external(s) found - cannot create output file
  [ERROR] ROM compilation failed
  ```
  (jb1/music.asm produced by `export_song_bank_bytecode` — first line:
  `; CA65 Assembly Export (MMC3 Macro Bytecode -- multi-song jukebox build)`.)
- **Impact**: No corrupt ROM is ever produced (ld65 fails hard), so this is a
  UX/defense-in-depth gap, not a correctness break — but the failure arrives
  two steps late, as a cryptic linker dump instead of a clean message, from a
  `prepare` step that explicitly reported success. Blast radius: the split
  prepare/compile debugging flow and any library consumer of
  `NESProjectBuilder` handed a jukebox music.asm; the normal `song build`
  route is unaffected.
- **Related**: Same "split flow loses build metadata → raw ld65 error" class
  as #297/MAP-2026-07-06-1, #362/MAP-2026-07-19-2, #283/MAP-2026-07-05B-3
  (all fixed via markers). Complements the fixed MAP-2026-08-07-2.
- **Hardware ref**: N/A (assembler/linker symbol resolution).
- **Suggested Fix**: In `prepare_project`, detect the jukebox variant from
  `music_content` (e.g. `"multi-song jukebox build" in music_content`) and
  either (a) treat it as jukebox mode when `song_count` is None — the Start-skip
  code and `JUKEBOX_BUILD` don't need the exact count, only `audio_advance_song`'s
  runtime `song_count` byte does, which music.asm itself exports — or (b) at
  minimum raise a clean `ExportError` telling the caller to pass `song_count`/
  use `song build`. Add a regression test running `run_prepare`-style
  `prepare_project(jukebox_music_asm)` with no `song_count`.

---

### MAP-2026-08-21-2: `CC65Wrapper.assemble`/`link` invoke bare `ca65`/`ld65`, not the resolved paths `check_toolchain` probed — and their `subprocess.run` guards omit `FileNotFoundError`

- **Severity**: LOW
- **Dimension**: 8 (compiler validation & CC65 error surfacing)
- **Location**: `compiler/cc65_wrapper.py:141` (`cmd = ["ca65", ...]`),
  `:199` (`cmd = ["ld65", ...]`), vs `:45-79` (`check_toolchain` resolves via
  `shutil.which()` and deliberately probes the **resolved** `self._ca65_path`/
  `self._ld65_path` "so we exercise the exact binary shutil.which found,
  avoiding a TOCTOU/PATH divergence (#14)"); `:147-160`/`:210-223` (only
  `subprocess.TimeoutExpired` is caught around the real assemble/link runs —
  unlike the probes, which also catch `FileNotFoundError`)
- **Status**: NEW (the #14 fix hardened `check_toolchain`/`get_version`; no
  prior finding covers the assemble/link invocations themselves)
- **Description**: The #14 hardening's stated rationale — probe the exact
  binary `which()` found so the check and the use can't diverge — is undercut
  one call later: `assemble()` and `link()` re-resolve `"ca65"`/`"ld65"`
  through PATH at spawn time instead of using the stored `_ca65_path`/
  `_ld65_path`. A binary that vanishes or is PATH-shadowed between
  `check_toolchain()` and the real run raises a raw `FileNotFoundError`
  (their `except` clause covers only `TimeoutExpired`), which escapes as a
  generic `[ERROR] Compilation failed: [Errno 2] ...` via `compile_rom`'s
  broad `except Exception` rather than the typed `ToolchainError` every other
  missing-tool path produces.
- **Evidence**: `check_toolchain` stores `self._ca65_path = shutil.which("ca65")`
  (`:45`) and probes `[self._ca65_path, "--version"]` (`:59`) with
  `except (FileNotFoundError, subprocess.TimeoutExpired)` (`:66`); `assemble`
  then builds `cmd = ["ca65", str(source_file), ...]` (`:141`) and guards only
  `except subprocess.TimeoutExpired` (`:155`). Same asymmetry in `link`.
- **Impact**: Cosmetic/hardening only — the window is a race between two
  subprocess calls, and the failure still surfaces as a nonzero exit with a
  message (never a false "success"), so no severity floor from
  `_audit-severity.md` applies. Consistency with the module's own #14
  invariant is the point.
- **Related**: #14 (commit `48da1ea`).
- **Hardware ref**: N/A.
- **Suggested Fix**: Use `self._ca65_path or "ca65"` / `self._ld65_path or
  "ld65"` in the `cmd` lists, and add `FileNotFoundError` to the two `except`
  clauses, mapping it to `ToolchainError`.

---

## Cross-audit dedup (independently confirmed this pass, filed by siblings today — not re-reported)

| Sibling ID | What this pass confirmed independently |
|---|---|
| **PIPE-2026-08-21-3** (CRITICAL, pipeline) / NH-HW-2026-08-21-3 | `load_song_streams_indexed` computes `current_song*5` in 8-bit A (`nes/audio_engine.asm:267-272`) and walks `song_table_*` with an 8-bit `iny` loop, while `export_song_bank_bytecode` emits the stride-5 table and `song_count: .byte ${len(songs):02X}` with **no cap on `len(songs)`** (`exporter/exporter_ca65.py:1623-1643`) — indices wrap from song 51 (channel ≥ 1) onward; 52–60 tiny songs fit the 60-bank pool, so the corrupt range is reachable. (For >255 songs `${n:02X}` widens to 3+ hex digits and ca65 rejects the `.byte`, so that extreme fails at build, not silently.) Dedup: already filed; a `len(songs) > 51` guard in the exporter would close it at export time. |
| **PIPE-2026-08-21-4** (HIGH, pipeline) | `run_song_build` (`main.py:992-1025`) has no backup/restore around compile/validate (unlike `run_compile`/`run_full_pipeline`) and calls `builder.prepare_project(...)` with no try/except and no return-value check — a capacity `ValueError` raised from `prepare_project`'s internal pre-flight (`nes/project_builder.py:239`) surfaces as a raw traceback. |
| **NH-HW-2026-08-21-1** (HIGH, nes-hardware) | Engine's `current_inst * 8` is an 8-bit `asl`×3 (`nes/audio_engine.asm:487-491`) and `EVAL_MACRO`'s Y-indexing is 8-bit in both branches, so instrument ids ≥ 32 alias mod 32 — while `_register_instrument` (`exporter/exporter_ca65.py:1009-1028`) allows up to 256. |
| **NH-HW-2026-08-21-6** (MEDIUM, nes-hardware) | Jukebox auto-advance/`@end_of_stream` interaction starts channels one NMI frame late at a transition. |
| **EXP-2026-08-21-8** (LOW, exporters) | `fetch_sequence_byte`'s header comment (`nes/project_builder.py:171`) claims the sequence bank swaps into `$8000-$9FFF`; the code selects R7 and translates into `$A000-$BFFF` (`ora #$A0`) — comment drift only, code correct per `docs/MAPPER_MMC3_REFERENCE.md` §2-3. |

## Dimensions with no (new) findings

| # | Dimension | Result |
|---|-----------|--------|
| 1 | iNES header ↔ nes.cfg | Re-summed from source. NROM: header `$02` (2×16KB) vs one `PRG` region `$8000` = 32KB ✓; flags-6 `$00` ✓. MMC1: `$08` (8×16KB=128KB) vs 7×`PRG_BANK_NN` ($4000 each) + `PRGFIXED` $4000 = 128KB ✓; flags-6 `$10` → mapper 1 ✓. MMC3: `.byte 32` (512KB) vs 60×$2000 + `PRG_A0`+`PRG_C0`+`PRG_80` (3×$2000) + `PRG_FIX` $1FFA + `VECTORS` $0006 = 512KB exactly ✓; flags-6 `$40` → mapper 4 ✓ (`docs/MAPPER_MMC3_REFERENCE.md` §2). NROM/MMC1 emit 15 explicit header bytes into the 16-byte fill-region (trailing byte = fill/zero) — flags-7..15 all zero, correct for mappers 0/1. Physical-bank order `PRG_A0/PRG_C0/PRG_80/PRG_FIX` (banks 60/61/62/63) intact (#291) — live 2-song build confirms `CODE_8000` content links at CPU `$8000` and the ROM is exactly 524,304 bytes. |
| 2 | Vectors + 60Hz NMI | `nmi`/`reset`/`irq` all defined in `_generate_main_asm` (`nes/project_builder.py:441-491`); `reset` ends with `lda #$80 / sta $2000`; `nmi` does `jsr update_music` before the jukebox Start-skip block, which uses the DPCM-safe `read_joypad_safe` (double-read compare) — not a second naive strobe. Traced the Start-skip X-clobber: `audio_advance_song` exits with X=$FF, so `prev_start_state` stores $FF instead of $10 after a skip — benign, since the flag is only ever tested for zero/nonzero (edge detection stays correct); noted, not filed. Start bit mask `#$10` matches the 8-read `rol` order (bit 4). MMC1 vectors verified **empirically**: linked a real MMC1 direct-export project with no post-process step; file offset `0x2000A` holds `nmi=$C045, reset=$C000, irq=$C053` — reset is byte 0 of `PRGFIXED`, and irq−nmi = 14 bytes = exactly the NMI handler body (3 pushes + `jsr` + 3 pulls + `rti`), confirming ld65 places the vectors unassisted (#213 holds; `grep` confirms no mapper overrides `generate_post_process_commands`). |
| 3 | APU init | Both paths verified in source: direct-export `init_music` (`exporter/exporter_ca65.py:943-955`) writes `$4011`=0, `$4017`=$40, `$4015`=$0F, `$4001`/`$4005`=$08; bytecode/jukebox path shares `audio_init_hw_and_state` (`nes/audio_engine.asm:193-215`) with the identical sequence, reached by both `audio_init` (fall-through) and `audio_init_song` (`jmp`). `@write_dpcm`/`@cmd_dpcm_play` end with `$4015`=$1F (all 4 channels + DMC re-enabled) — enables never left off. Refs: `docs/NES_APU_REFERENCE.md` §3.1-3.2, `docs/APU_FRAME_COUNTER_REFERENCE.md`. |
| 4 | PRG capacity pre-flight | All four verify-the-fix items pass live: (#390) `.byte "some, string", $00` + a 3-numeric line sizes as 16 bytes exactly; (#363) constructing `NESProjectBuilder` directly and calling `prepare_project` on an oversized music.asm raises the region-naming `ValueError` ("instrument/macro tables (CODE_8000, 12,800 bytes) exceed the MMC3 $8000 window") with no CLI involved; (#389) that gate runs on the final written music.asm (`nes/project_builder.py:239`, after overlay/engine/stub transforms); `MMC3Mapper.validate_segment_sizes` still sums shared `BANK_NN`+`DPCM_NN` (#212) and caps bank index at `SWAP_BANK_COUNT` (#127). The jukebox path is double-gated (raw exporter output at `main.py:1007` + final at `nes/project_builder.py:239`), and multi-song `CODE_8000` growth (N instrument/macro tables + song tables) is inside the checked segment, so it's caught pre-ld65. `estimate_segment_sizes`'s `.align` rounding (#301) intact. |
| 5 | Bank switching | MMC1 init: `$80` reset write then 5-write LSB-first serial of `$0C` (mode 3 — fix last bank at `$C000`, switch `$8000`) to `$8000`, bank via `$E000` — matches `docs/MAPPER_MMC1_REFERENCE.md` §1-3 exactly. MMC3: `$46`/`$47` = P-bit(6)+R6/R7; mode 1 maps R6→`$C000` (DPCM window), R7→`$A000` (sequence window) per `docs/MAPPER_MMC3_REFERENCE.md` §2-3, matching `fetch_sequence_byte`'s `ora #$A0` translation and `switch_dpcm_bank`; `sta $E000` = IRQ disable (value-independent) ✓. Init serial writes can't be interrupted (NMI enabled only after `init_music` returns). |
| 6 | MapperFactory auto-selection | Ordering smallest-first ✓; nothing-fits branch reports the largest budget *for the mode* (MMC1's pool in direct mode) with the "enable pattern compression" hint ✓. All three direct-export call sites pass `direct=True` (`main.py:397, 687, 1207`); the bytecode path resolves via `resolve_mapper` (banked capacity / forced MMC3) ✓ (#361 holds). Marker guard order in `resolve_mapper` — bytecode/DPCM before bank-pack ✓ (#362 holds); `export_direct_frames` stamps the DPCM marker whenever `frames['dpcm']` is non-empty (`exporter/exporter_ca65.py:634-635`) ✓. `run_song_build` bypasses auto-selection entirely (hardcoded MMC3), per v1 scope. |
| 7 | Buildable project | Beyond MAP-2026-08-21-1: every segment used by main.asm/music.asm/audio_engine.asm (`HEADER`,`ZEROPAGE`,`BSS`,`CODE`,`RODATA`,`VECTORS`,`CODE_8000`,`DPCM`,`BANK_NN`,`DPCM_NN`) exists in MMC3's nes.cfg and vice versa; no `OAM` reappearance (#215). Engine's unconditional top-of-file `.import`s of single-song labels are never *referenced* under `JUKEBOX_BUILD`, so ld65 doesn't flag them (confirmed by the passing live jukebox links). ZP contract (`ptr1/temp1/temp2/frame_counter` exportzp ↔ importzp; `sequence_ptr/sequence_bank` main.asm-owned) consistent. `prepare_multi_song_project`/`add_song_bank` stubs remain deleted. |
| 8 | Compiler validation / CC65 surfacing | Beyond MAP-2026-08-21-2: `validate_project` runs before assembly with an accurate missing list; `assemble`/`link` raise `CompilationError` with stderr on nonzero rc; `check_toolchain`/`get_version` guarded per #14; `compile_rom` prints traceback only under verbose (#32), typed errors stay one-liners; `_run_post_process` only ever receives static mapper text (no override exists today); mapper recovery from the nes.cfg stamp works in both `run_compile` (`main.py:578-581`) and library `ROMCompiler.compile` (`_recover_mapper_from_cfg`) (#297/#269/#363 hold). REG-10 cross-check: `tests/test_rom_validation_integration.py` hard-asserts `compile_rom(...)` (lines 78, 116, 150, 188) under `@pytest.mark.requires_cc65` — no skip-masking (#128 holds). |
| 9 | ROM size check | Exact-size check (`mapper.prg_rom_size + 16`) verified live twice: both jukebox ROMs 524,304 bytes, MMC1 ROM 131,088 bytes. `MIN_ROM_SIZE` floor now only reachable for a mapper-less *and* marker-less library call (the cfg-stamp recovery covers stamped projects) — residual gap already noted in prior reports, unchanged, not re-filed. |
| 10 | Default-mapper doc drift | `grep -niE 'always use mmc1|default.*mapper' README.md CLAUDE.md docs/*.md` — every hit correctly names MMC3 as the default; remaining `mmc1` mentions are legitimate reference/aside material. No drift. |

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_MAPPERS_2026-08-21.md
```
