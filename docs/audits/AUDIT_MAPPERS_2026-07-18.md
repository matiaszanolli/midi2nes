# Audit: Mappers / Project Builder / Compiler — 2026-07-18

Subsystem audited: `mappers/` (base, factory, nrom, mmc1, mmc3), `nes/project_builder.py`,
`compiler/compiler.py`, `compiler/cc65_wrapper.py`, and the `main.py` `--mapper`
resolution / capacity-preflight / `resolve_mapper` call sites. All 10 SKILL.md dimensions
covered, no `--focus` restriction.

This is a re-audit/delta pass. It re-verifies every "fixed" dimension the SKILL flags,
accounts for the current tree state after **#314/EXP-12** (which removed the dead
`seq_cmd_instrument`/`seq_cmd_dpcm_play` routines and ~85 bytes of BSS from
`nes/project_builder.py`'s bytecode-mode `music.asm`, keeping `fetch_sequence_byte`), and
re-confirms the one standing finding — now filed as **OPEN issue #316** — is still live.

**Dedup basis:** `/tmp/audit/issues.json` (24 issues, prefetched via `gh issue list`)
searched for `mapper`, `compile`, `auto`, `nrom`, `mmc1`, `mmc3`, `bank`, `capacity`,
`align`, `relative`, `cwd`, `path`, `resolve`; all prior `docs/audits/AUDIT_MAPPERS_*.md`.
The single finding below maps to open issue **#316** (`MAP-2026-07-18-1`) and its
regression-test gap **#323** (`REG-17`), so it is **noted, not re-filed**.

Every claim below was verified against live code, and the mapper build paths were
reproduced end-to-end with the real CC65 toolchain (`ca65`/`ld65` at `/usr/bin`):
NROM, MMC1, and MMC3 ROMs were built and their iNES headers + `$FFFA–$FFFF` vectors
inspected this pass.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 1 (Existing: #316 — not re-filed) |
| MEDIUM   | 0 |
| LOW      | 0 |
| **NEW this pass** | **0** |

**One-line verdict:** The **default** single-command pipeline (MMC3, patterns-on) still
produces a bootable 512 KB ROM end-to-end (re-verified live: `python main.py
test_midi/simple_loop.mid out.nes` → **524,304-byte** ROM, header PRG byte `32`, mapper
nibble `4`, reset/NMI/IRQ at `$E000/$E02F/$E03D` inside the fixed bank, APU initialized,
`ROM Health: FAIR` from non-fatal pattern-density warnings only). The one open defect is
the documented **step-by-step** flow (`prepare` → `compile`) with a *relative* project
directory, tracked as **#316**.

**Highest-leverage fix:** #316 (`MAP-2026-07-18-1`, HIGH) — resolve `project_dir`
(and `output_path`) to an absolute path at the top of `ROMCompiler.compile()`.

---

## Findings

### MAP-2026-07-18-1: `compile` subcommand fails on the exact relative-path invocation `CLAUDE.md` documents — `ROMCompiler.compile()` doubles the project directory into the assemble/link source paths
- **Severity**: HIGH
- **Dimension**: 8 (compiler validation & CC65 error surfacing)
- **Location**: `compiler/compiler.py:141-142` (`project_dir = Path(project_dir)` / `output_path = Path(output_path)`, neither `.resolve()`d), then `compiler/compiler.py:156-180` (`assemble`/`link` called with the same possibly-relative `project_dir` as both the source-path prefix **and** the subprocess `cwd`); `compiler/cc65_wrapper.py:141,148-154` (`assemble`: `cmd = ["ca65", str(source_file), ...]` run with `cwd=working_dir`) and `cc65_wrapper.py:199-217` (`link`); reached from `main.py:445` (`run_compile`: `project_path = Path(args.input)`, no resolve) → `main.py:472` (`compile_rom(project_path, ...)`).
- **Status**: **Existing: #316** (also tracked by #323/REG-17, the missing regression test). Confirmed **still present** this pass — `compiler/compiler.py:141` remains `Path(project_dir)` with no `.resolve()`.
- **Description**: `ROMCompiler.compile()` never converts `project_dir` to an absolute path. When the caller passes a relative directory — exactly what `run_prepare`'s own printed guidance (`main.py:521-522`) and `CLAUDE.md`'s "Step-by-step pipeline" section show (`python main.py compile nes_project/ output.nes`) — `assemble()`/`link()` receive **both** a relative `source_file`/`config_file` **and** that same relative path as `cwd=`. `subprocess.run(cmd, cwd=working_dir)` resolves `working_dir` against the current process cwd, but the `source_file` argument inside `cmd` is passed through unchanged, so `ca65` — now already running inside `nes_project/` — looks for `nes_project/main.asm` relative to that, i.e. `nes_project/nes_project/main.asm`, which does not exist. Only an absolute `project_dir` avoids the doubling. Mapper-agnostic (shared `ROMCompiler`/`CC65Wrapper` code), so NROM/MMC1/MMC3 are affected identically.
- **Evidence**:
  ```
  $ python main.py compile nes_project/ output.nes      # the documented form
  [ERROR] Failed to assemble main.asm: Fatal error: Cannot open input file
          'nes_project/main.asm': No such file or directory : Tool: ca65, Exit code: 1
  # nes_project/main.asm exists on disk; passing an ABSOLUTE dir compiles fine.
  ```
  `./build.sh` inside `nes_project/` is unaffected (it uses bare relative filenames from within the already-`cd`'d directory, per `generate_build_script`'s `ca65 main.asm -o main.o`).
- **Impact**: `main.py compile <relative-dir> <out>` is unusable as documented for every mapper — the literal command in `CLAUDE.md` and in `run_prepare`'s printed next-step. The single-command full pipeline is **not** affected (it builds `project_path` from `tempfile.TemporaryDirectory()`, always absolute). Blast radius: the entire step-by-step/debugging CLI flow plus any library caller of `ROMCompiler.compile()`/`compile_rom()` passing a relative path.
- **Related**: #323/REG-17 (no test exercises `ROMCompiler.compile()` with a relative `project_dir`). Distinct from #297/MAP-2026-07-06-1 (mapper mis-resolution, fixed) — this is a subprocess-path bug in the same `compile` code path.
- **Hardware ref**: n/a (subprocess/CLI path handling, not a register or header claim).
- **Suggested Fix**: In `ROMCompiler.compile()` resolve both paths immediately —
  `project_dir = Path(project_dir).resolve()` and `output_path = Path(output_path).resolve()` —
  before any `assemble`/`link` call, so every downstream `project_dir / "..."` argument is
  absolute and `cwd=working_dir` no longer interacts with the source-file argument. Add the
  #323/REG-17 regression test with a relative `project_dir`.

---

## Current-tree verification: #314/EXP-12 removal is clean

The task flagged that #314/EXP-12 recently removed the dead
`seq_cmd_instrument`/`seq_cmd_dpcm_play` routines and ~85 bytes of BSS from
`nes/project_builder.py`'s bytecode-mode `music.asm`, keeping `fetch_sequence_byte`.
Verified this pass:

- **No dangling references** to `seq_cmd_instrument`/`seq_cmd_dpcm_play` remain in product
  code or `.asm`. The only live mentions are: the explanatory comment at
  `nes/project_builder.py:135-140`, and a **regression test that pins the removal** —
  `tests/test_nes_project_builder.py:578-598` asserts those symbols and the `ch_*`/
  `apu_shadow_*` BSS are **absent** from the generated bytecode `music.asm`.
- **`fetch_sequence_byte` was kept** and is still `.global`-defined in
  `nes/project_builder.py:148-178` and `.import`ed + called six times by
  `nes/audio_engine.asm` (lines 11, 198, 225, 231, 259, 263, 266).
- **The bytecode engine still links and boots**: the live MMC3 pattern-compressed build
  above produced a valid 524,304-byte ROM with real note data (3 patterns, 100% coverage),
  proving no symbol was left dangling by the removal.
- The DPCM-trigger path the SKILL's Dimension 3 attributes to the (now-removed)
  `seq_cmd_dpcm_play` still exists elsewhere: inline in `audio_engine.asm` for the bytecode
  path, and via the direct-export `play_dpcm` routine (MMC3-only, guarded by
  `enforce_direct_export_dpcm_mapper`, `main.py:284-317`). No functional gap from the removal.

## Re-verified unchanged/correct this pass (no regression)

- **Dimension 1 — iNES header ↔ nes.cfg.** Built live and inspected: NROM header PRG byte
  `2` / flags-6 `$00` (mapper 0), 32,784-byte ROM; MMC1 `8` / `$10` (mapper 1),
  131,088-byte ROM; MMC3 `32` / `$40` (mapper 4), 524,304-byte ROM. `nes.cfg` `MEMORY`
  sums recomputed: NROM `PRG` `$8000` = 32 KB = `$02`×16 KB; MMC1 (7×`PRG_BANK_NN` `$4000`
  + `PRGFIXED` `$4000`) = 128 KB = `$08`×16 KB; MMC3 (60×`PRG_BANK_NN` `$2000` +
  `PRG_A0`+`PRG_C0`+`PRG_80` `$2000` each + `PRG_FIX` `$1FFA` + `VECTORS` `$0006`) =
  512 KB = `32`×16 KB. All three sum exactly; mapper nibbles match `mapper_number`.
  Hardware ref: `docs/MAPPER_MMC3_REFERENCE.md` (flags-6 mapper-low-nibble).
- **Dimension 2 — vectors + 60 Hz NMI.** `nmi`/`reset`/`irq` all defined in
  `_generate_main_asm` (`nes/project_builder.py:311-377`); `reset` does the mapper
  `generate_init_code()`, then `jsr init_music`, then `lda #$80 / sta $2000` to enable NMI;
  `nmi` does `jsr update_music`. `VECTORS` loads at `$FFFA` for every mapper. Live vector
  reads land in real code for all three (NROM reset `$8000`, MMC1 reset `$C000` at file
  offset `0x2000A`, MMC3 reset `$E000`). MMC1's post-link vector fixup is gone (#213):
  `MMC1Mapper` inherits the no-op `BaseMapper.generate_post_process_commands`, and ld65
  places the vectors correctly unassisted (verified: MMC1 ROM's last 6 bytes = valid
  `$C045/$C000/$C053`).
- **Dimension 3 — APU init in the boot path.** `reset → jsr init_music` reaches
  `$4015`/`$4017` writes on both paths; the live ROMs pass `rom_diagnostics`' APU-init
  gate. MMC3's `generate_init_code()` leads with `sta $E000` (IRQ disable, value ignored —
  harmless undefined A) before configuring PRG mode 1 and R6/R7. Hardware ref:
  `docs/NES_APU_REFERENCE.md`, `docs/APU_FRAME_COUNTER_REFERENCE.md`,
  `docs/MAPPER_MMC3_REFERENCE.md`.
- **Dimension 4 — PRG capacity pre-flight.** `check_mapper_capacity` →
  `mapper.validate_segment_sizes` still wired before `ld65` on both `run_prepare`
  (`main.py:497`) and the full pipeline (`main.py:1064`). `estimate_segment_sizes`
  (`main.py:123-167`) confirmed accurate for the bytecode path — that path emits sequence
  data as countable `.byte` rows (`exporter/exporter_ca65.py:1202-1286`), not macro
  invocations, so it does **not** systematically undercount. MMC3's per-region check
  (`RODATA`+`CODE` vs `PRG_FIX`; `CODE_8000` vs `$8000` window; summed `BANK_NN`+`DPCM_NN`
  per shared physical bank; `max_bank >= SWAP_BANK_COUNT`) and MMC1's per-bank check both
  unchanged and correct. Note the standing defense-in-depth gaps (unchanged, not new):
  `NESProjectBuilder.prepare_project()` itself does not call the capacity gate (library
  callers bypassing `main.py` rely on `ld65`), and #301 (below).
- **Dimension 5 — bank switching.** MMC1's 5-write serial control (`$0C` = 16 KB PRG
  mode, fixed high bank) / bank loads (`mappers/mmc1.py:108-147`) and MMC3's R6(`$46`)/
  R7(`$47`) selects via `$8000`/`$8001` with `sta $E000` IRQ-disable
  (`mappers/mmc3.py:111-149`) unchanged. #291's load-bearing physical-bank order
  (`PRG_A0`/`PRG_C0`/`PRG_80`/`PRG_FIX` = banks 60/61/62/63, so `PRG_80` hosting
  `CODE_8000` is the fixed second-to-last bank) unchanged at `mappers/mmc3.py:75-79`.
  Hardware refs: `docs/MAPPER_MMC1_REFERENCE.md`, `docs/MAPPER_MMC3_REFERENCE.md`.
- **Dimension 6 — MapperFactory auto-select.** `auto_select` ordering (nrom→mmc1→mmc3,
  smallest-fits-first; "nothing fits" raises with the largest mapper's capacity) and
  `get_mapper("auto", 0)`'s MMC3 fallback unchanged. `resolve_mapper` (`main.py:239-281`)
  is the live `--mapper auto` caller; its bytecode-engine force
  (`_requires_mmc3_bytecode_engine`), direct-export bank-pack guard
  (`_direct_export_packed_mapper_name`), and `enforce_direct_export_dpcm_mapper` all raise
  clean `ValueError`s. Any auto pick that overruns is still caught by the Dimension-4
  pre-flight before `ld65`.
- **Dimension 7 — buildable project.** Every segment `main.asm`/`music.asm` reference
  exists in the active mapper's `nes.cfg` (confirmed by the three live builds, all `rc=0`).
  MMC3's `generate_header_asm()` emits bare `.byte` only; the exporter is the sole owner of
  `.segment "HEADER"`; no stray `OAM` region (#215). ZP/BSS `.importzp`/`.global` symbols
  (`sequence_ptr`, `sequence_bank`, `frame_counter`, `switch_dpcm_bank`,
  `fetch_sequence_byte`) resolve — including the benign case where NROM/MMC1 direct export
  declares `.global switch_dpcm_bank` with no definition (an unreferenced import ld65 does
  **not** error on; both direct builds linked cleanly).
- **Dimension 8 — compiler / CC65 surfacing.** `assemble()`/`link()` raise
  `CompilationError` with `stderr` on nonzero return code; `check_toolchain()`/
  `get_version()` probe the `shutil.which()`-resolved path under
  `try/except (FileNotFoundError, TimeoutExpired)` → `ToolchainError` (#14);
  `compile_rom()`'s broad `except Exception` calls `traceback.print_exc()` under
  `--verbose` while the typed `CompilationError`/`ValidationError` paths print a clean
  one-liner (#32); `ROMCompiler.compile()` invokes `generate_post_process_commands()`
  post-link when a mapper is passed, and `_run_post_process`'s `shell=True` runs only the
  static mapper-constant snippet (#214/#263). MMC1 no longer has a fixup (#213). **The one
  live defect here is #316 above.**
- **Dimension 9 — ROM size check.** `compile()` checks the exact `mapper.prg_rom_size + 16`
  when a mapper is passed (both CLI callers do); the three live ROM sizes match exactly
  (32,784 / 131,088 / 524,304). The `mapper is None` flat-`MIN_ROM_SIZE=32768` fallback
  remains a defense-in-depth-only path for library callers (unchanged, not a new finding).
- **Dimension 10 — default-mapper doc drift.** No drift. `CLAUDE.md`/`README.md`/`docs/*.md`
  consistently describe MMC3 as the pipeline default with MMC1/NROM selectable; all `mmc1`
  hits are legitimate reference/comparison content.

## Still-open, not re-filed

- **#316 / MAP-2026-07-18-1** (OPEN, HIGH) — the relative-path `compile` doubling above.
  Confirmed still present; owner should apply the `.resolve()` fix and land #323/REG-17.
- **#323 / REG-17** (OPEN) — no test calls `compile_rom`/`ROMCompiler.compile()` with a
  relative `project_dir`, which is why #316 slipped past CI (every real integration test
  uses absolute `tmp_path` fixtures).
- **#301 / MAP-2026-07-06-2** (OPEN, LOW) — capacity pre-flight undercounts DPCM `.align 64`
  padding. Re-verified present (`estimate_segment_sizes` still has no `.align` branch) but
  packer-guarded/unreachable through the normal pipeline (`dpcm_sampler/dpcm_packer.py`
  caps each bank's aligned total at pack time). Unchanged, not re-filed.
- **#269 / PL-08** (OPEN) — `compile --mapper` has no `auto`. Effectively resolved as a
  side effect of #297 (compile recovers the concrete mapper from the `nes.cfg` marker, so
  `auto` is never needed there); recommend closing or downgrading to a cosmetic LOW rather
  than treating as a live gap.

## Dimension coverage map

| Dim | Area | Result |
|-----|------|--------|
| 1 | iNES header ↔ nes.cfg | Verified live (headers + sums) for all 3 mappers. No finding. |
| 2 | Vectors + 60 Hz NMI | `nmi`/`reset`/`irq` defined; NMI enabled + `jsr update_music`; vectors at `$FFFA` land in code (live). No finding. |
| 3 | APU init | `$4015`/`$4017` reached on both paths; MMC3 undefined-A `sta $E000` harmless. No finding. |
| 4 | PRG capacity / overrun | Pre-flight wired + correct; heuristic accurate for bytecode `.byte` path. #301 (LOW) still open, packer-guarded. Standing lib-bypass gap unchanged. |
| 5 | Bank switching | MMC1 5-write / MMC3 R6/R7 + #291 physical-bank order unchanged + correct. No finding. |
| 6 | MapperFactory auto-select | `auto_select` ordering + all `resolve_mapper` guards raise cleanly. No finding. |
| 7 | Project builder buildability | Segments consistent; #314/EXP-12 removal clean (no dangling symbols); all 3 mappers link live. No finding. |
| 8 | Compiler / CC65 surfacing | **#316 (HIGH, Existing)**: relative `project_dir` doubles into assemble/link source path. Everything else unchanged + correct. |
| 9 | ROM size check | Exact-size check matches live ROM sizes for all 3 mappers. No finding. |
| 10 | Default-mapper doc drift | No drift. |

---

Next step:
```
/audit-publish docs/audits/AUDIT_MAPPERS_2026-07-18.md
```
