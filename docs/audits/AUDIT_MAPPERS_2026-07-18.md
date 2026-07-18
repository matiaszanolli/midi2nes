# Audit: Mappers / Project Builder / Compiler — 2026-07-18

Subsystem audited: `mappers/` (base, factory, nrom, mmc1, mmc3), `nes/project_builder.py`,
`compiler/compiler.py`, `compiler/cc65_wrapper.py`, and the `main.py` `--mapper`
resolution / capacity-preflight / `resolve_mapper` call sites. All 10 SKILL.md dimensions
covered, no `--focus` restriction.

This is a re-audit/delta pass following `AUDIT_MAPPERS_2026-07-06.md`. Relevant commits
since that pass (`git log --oneline` on `mappers/`, `compiler/`, `nes/project_builder.py`,
`main.py`):
- `452d5b2` (#297) — recover the prepared mapper from `nes.cfg` in `compile`
- `757ff86` (#291), `833174b`/`8bbfe9a` (#283/#284/#285), `7af88a4` (#281/#282) — all
  pre-date and are already covered by the 07-06 report; re-verified unchanged below.

**Dedup basis:** `/tmp/audit/issues.json` (27 open issues, prefetched) searched for
`mapper`, `compile`, `auto`, `nrom`, `mmc1`, `mmc3`, `bank`, `capacity`, `align`, `relative`,
`cwd`, `path`; all prior `docs/audits/AUDIT_MAPPERS_*.md`, plus a scan of
`AUDIT_SAFETY_*.md`/`AUDIT_REGRESSION_*.md`/`AUDIT_PIPELINE_*.md` for any prior mention of
subprocess working-directory or relative-path handling in the compiler. No existing issue
or report covers this pass's NEW finding.

Every finding below was verified against live code, not just re-read: the NEW finding
was reproduced end-to-end with the real CC65 toolchain (`ca65`/`ld65` V2.18, present at
`/usr/bin`), and the "previously identified, now fixed" items were re-verified with a
direct `resolve_mapper`/`_prepared_mapper_name_from_cfg` repro.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 1 |
| MEDIUM   | 0 |
| LOW      | 0 |
| **Total (NEW)** | **1** |

Plus two previously-open findings confirmed **now fixed** as a side effect of #297 (see
below), and one pre-existing open issue (**#301**) re-verified unchanged, not re-filed.

**One-line verdict:** The **default** single-command pipeline (MMC3, patterns-on) still
produces a bootable 512KB ROM end-to-end (re-verified live: `python main.py input.mid
out.nes` → 524,304-byte ROM, valid vectors, APU initialized, `ROM Health: FAIR` from
non-fatal pattern-density warnings only) — no regression. But the **documented
step-by-step flow** (`prepare` → `compile`) is broken for the exact invocation
`CLAUDE.md` itself documents (`python main.py compile nes_project/ output.nes`, a
relative path): `ROMCompiler.compile()` passes a still-relative `project_dir / "main.asm"`
as the assemble source while also setting that same relative `project_dir` as the
subprocess `cwd`, so `ca65` resolves the source path against its own new working
directory and doubles the directory component, failing with `Cannot open input file
'nes_project/main.asm'`. Confirmed reproducible for every mapper (mapper-agnostic bug in
shared compiler code), with the only workaround being to pass an absolute project
directory — never mentioned by the tool's own `prepare` success message or `CLAUDE.md`.

**Highest-leverage fix:** MAP-2026-07-18-1 (HIGH) — resolve `project_dir` (and
`output_path`) to an absolute path at the top of `ROMCompiler.compile()`, mirroring what
the full pipeline gets for free from `tempfile.TemporaryDirectory()`.

---

## Findings (most severe first)

### MAP-2026-07-18-1: `compile` subcommand fails on the exact relative-path invocation `CLAUDE.md` documents — `ROMCompiler.compile()` doubles the project directory into the assemble/link source paths
- **Severity**: HIGH
- **Dimension**: 8 (compiler validation & CC65 error surfacing)
- **Location**: `compiler/compiler.py:141-180` (`ROMCompiler.compile`: `project_dir = Path(project_dir)` with no `.resolve()`, then `self.cc65.assemble(project_dir / "main.asm", project_dir / "main.o", project_dir)` and the equivalent `music.asm`/`link` calls, all passing the same possibly-relative `project_dir` as both the path component and the subprocess `cwd`); `compiler/cc65_wrapper.py:141,150` (`assemble`: `cmd = ["ca65", str(source_file), ...]` run with `subprocess.run(cmd, cwd=working_dir, ...)`) and the equivalent in `link()` (`cc65_wrapper.py:199-217`); reached from `main.py:445` (`run_compile`: `project_path = Path(args.input)`, no resolve) and `main.py:472` (`compile_rom(project_path, output_rom, ...)`).
- **Status**: NEW
- **Description**: `ROMCompiler.compile()` never converts `project_dir` to an absolute path. When the caller passes a relative directory (e.g. `nes_project/`, which is exactly what `run_prepare`'s own printed guidance says to pass: `main.py:521-522`, "Or compile + validate in one step: python main.py compile {args.output} <output.nes>", and what `CLAUDE.md`'s own documented example shows: `python main.py prepare music.asm nes_project/` then `python main.py compile nes_project/ output.nes`), `assemble()`/`link()` are called with **both** a relative `source_file`/`config_file` argument **and** that same relative path as the subprocess's `cwd=`. `subprocess.run(cmd, cwd=working_dir)` resolves `working_dir` against the *current* process's cwd to find where to run `ca65`, but the `source_file` argument inside `cmd` is passed through unchanged (still `"nes_project/main.asm"`) — so `ca65`, now running with its own working directory already inside `nes_project/`, looks for `nes_project/main.asm` *relative to that*, i.e. `nes_project/nes_project/main.asm`, which does not exist. Only an **absolute** `project_dir` avoids the doubling, because then `source_file` is already absolute and `cwd` is irrelevant to resolving it. This is mapper-agnostic (it lives in the shared `ROMCompiler.compile()`/`CC65Wrapper` code, not any `mappers/*.py`), so it affects NROM, MMC1, and MMC3 identically whenever `compile` (or a library caller of `compile_rom`/`ROMCompiler.compile`) is invoked with a relative project directory.
- **Evidence**:
  ```
  $ cd /tmp/audit/mapper_test/docflow
  $ python3 main.py prepare ../music_nrom.asm nes_project --mapper nrom
    ✓ Music data 4,000 bytes fits the NROM PRG regions
    Using NROM with 32KB PRG-ROM
   Prepared NES project -> nes_project
   Or compile + validate in one step: python main.py compile nes_project <output.nes>

  $ python3 main.py compile nes_project/ output.nes      # exactly the documented form
  Compiling NES ROM from nes_project ...
  [ERROR] Failed to assemble main.asm: Fatal error: Cannot open input file 'nes_project/main.asm': No such file or directory
  : Tool: ca65, Exit code: 1
  [ERROR] ROM compilation failed

  $ python3 main.py compile "$(pwd)/nes_project" "$(pwd)/output.nes"   # absolute path
  Compiling NES ROM from /tmp/audit/mapper_test/docflow/nes_project ...
  Validating ROM...
    ✓ ROM Health: ... (or FAIR, non-fatal warnings only)
  [OK] Compiled ROM -> /tmp/audit/mapper_test/docflow/output.nes
  ```
  `nes_project/main.asm` exists on disk at both points (`ls nes_project/` shows `main.asm`,
  `music.asm`, `nes.cfg`, `build.sh`, `audio_engine.asm`) — the failure is purely the
  path-doubling, not a missing file. `./build.sh` inside `nes_project/` is unaffected
  (it uses bare relative filenames from within the already-`cd`'d directory, matching
  `generate_build_script`'s `ca65 main.asm -o main.o` form — no `project_dir` prefix to
  double).
- **Impact**: `main.py compile <relative-dir> <out>` is unusable as documented for every mapper — this is not a rare edge case, it is the literal command in `CLAUDE.md`'s "Step-by-step pipeline for debugging" section and in `run_prepare`'s own printed next-step instructions. Any user or script that `cd`s into a parent directory and runs `compile` with a project subdirectory name (the natural, common invocation) gets a confusing `ca65` file-not-found instead of a working build; the only workaround (pass an absolute path) is undocumented. The single-command full pipeline (`run_full_pipeline`) is **not** affected — it builds `project_path` from `tempfile.TemporaryDirectory()`, which always yields an absolute path — so the default MIDI→ROM flow (re-verified live this pass, 524,304-byte MMC3 ROM, no regression) is unaffected. Blast radius is therefore the entire step-by-step/debugging CLI flow (`prepare` → `compile`) plus any library caller of `ROMCompiler.compile()`/`compile_rom()` that passes a relative path, across all three mappers equally.
- **Related**: Not a duplicate of MAP-2026-07-06-1 (that was a mapper-*mis-resolution* bug, fixed by #297) — this is a distinct subprocess-path bug in the same `compile` code path, uncovered because every existing unit test for `run_compile` mocks `main.compile_rom` (`tests/test_main.py:773-799`, `TestRunCompile`) and every real end-to-end CC65 integration test uses pytest's `temp_dir`/`tmp_path` fixtures, which are always absolute (`tests/conftest.py:50-54`, `tempfile.TemporaryDirectory()`) — so no existing test exercises `ROMCompiler.compile()` with a relative `project_dir`.
- **Hardware ref**: n/a (subprocess/CLI path handling, not a register or header claim).
- **Suggested Fix**: In `ROMCompiler.compile()` (`compiler/compiler.py:141-142`), resolve both paths immediately: `project_dir = Path(project_dir).resolve()` and `output_path = Path(output_path).resolve()`, before any `assemble`/`link` call. This makes every downstream `project_dir / "..."` argument absolute regardless of what the caller passed, so `cwd=working_dir` no longer interacts with the source-file argument. (Alternatively/additionally, `cc65_wrapper.py`'s `assemble`/`link` could pass source/config filenames alone — `source_file.name` — when `working_dir` is set, since `cwd` already puts the process there; resolving in `compile()` is the smaller, single-point fix.)

---

## Previously identified, now fixed (dedup per `_audit-common.md`)

Both findings from `AUDIT_MAPPERS_2026-07-06.md` are **confirmed fixed** this pass, by the
same commit:

- **MAP-2026-07-06-1 (was MEDIUM)** — `compile` defaulted to MMC3 and could not recover a
  NROM-prepared project, rejecting a valid NROM ROM with a misleading MMC3 size-mismatch.
  Fixed by `452d5b2` (#297): `_prepared_mapper_name_from_cfg()` (`main.py:218-236`) reads
  the `# midi2nes-mapper: <name>` marker `NESProjectBuilder.prepare_project()` now stamps
  as the first line of `nes.cfg` (`nes/project_builder.py:320-322`), and `run_compile`
  (`main.py:460-461`) uses it to resolve the mapper authoritatively before falling back to
  `--mapper`. Re-verified live this pass:
  ```
  >>> _prepared_mapper_name_from_cfg('.../nes.cfg')   # NROM project, no --mapper on compile
  'nrom'
  >>> resolve_mapper('nrom', '.../music.asm').name
  'NROM'
  ```
  and the same NROM project compiled and linked correctly (mod the unrelated
  MAP-2026-07-18-1 relative-path issue above, worked around with an absolute path for
  this check) with the exact 32,784-byte NROM size, not a spurious MMC3 mismatch.
- **#269 / PL-08 (was OPEN, "`compile --mapper` has no `auto`")** — resolved as a side
  effect of the same #297 fix: since `run_compile` now recovers the mapper from `nes.cfg`
  first and only falls back to `--mapper` for older marker-less projects, a
  `prepare --mapper auto` project's `compile` invocation no longer needs an `auto` choice
  on `--mapper` at all — the `nes.cfg` marker already carries the *resolved* concrete
  mapper name (`prepare` never stamps `"auto"` itself; `self.mapper.name.lower()` is
  always a concrete mapper by the time `prepare_project()` runs). `main.py:1198`'s
  `choices=['nrom', 'mmc1', 'mmc3']` (still no `'auto'`) is therefore no longer a live gap
  for the documented flow. The GitHub issue is still open at the time of this audit;
  recommend closing it as fixed-by-#297 (or downgrading to a cosmetic "add `auto` to the
  choices list for symmetry" LOW) rather than re-filing.

Also re-verified unchanged/correct this pass (no regression):
- **Dimension 1** — NROM MEMORY (`PRG` `$8000`) = 32,768B = header `$02`×16KB; MMC1
  (7×`PRG_BANK_NN` `$4000` + `PRGFIXED` `$4000`) = 131,072B = header `$08`×16KB; MMC3
  (60×`PRG_BANK_NN` `$2000` + `PRG_A0`+`PRG_C0`+`PRG_80` `$2000` each + `PRG_FIX`
  `$1FFA` + `VECTORS` `$0006`) = 524,288B = header `32`×16KB. Mapper nibbles `$00`/`$10`/
  `$40` = 0/1/4, matching `mapper_number`. Recomputed via `mappers/*.py:prg_rom_size`
  properties this pass — all three sum exactly, no mismatch.
- **Dimension 2/3** — `nmi`/`reset`/`irq` all defined in `nes/project_builder.py`'s
  `_generate_main_asm` template (lines 437-486); `reset` does `sei`/`cld`/stack setup,
  the mapper's `generate_init_code()`, then `jsr init_music`, then `sta $2000` (`lda
  #$80`) to enable NMI; `nmi` does `jsr update_music`. `VECTORS` loads at `$FFFA` for
  every mapper. MMC3's `generate_init_code()` leads with `sta $E000` before any `lda` —
  re-checked against `docs/MAPPER_MMC3_REFERENCE.md:39` ("`$E000`: IRQ Disable
  (Acknowledges and disables interrupts)") — this MMC3 register ignores the written
  value, so an undefined accumulator at that point is harmless, not a bug.
- **Dimension 4** — capacity pre-flight (`main.py:check_mapper_capacity` →
  `mapper.validate_segment_sizes`) still wired before `ld65` on both `prepare` and the
  full pipeline; `MMC3Mapper`/`MMC1Mapper` per-bank sum-and-check logic unchanged and
  correct. `#301` (LOW, `.align 64` DPCM padding undercount, packer-guarded) re-verified
  present and unchanged (`main.py:123-167` `estimate_segment_sizes` still has no
  `.align` branch; `dpcm_sampler/dpcm_packer.py:38,60-64` still caps each bank's
  *aligned* total at 8192 at pack time, so the gap remains unreachable through the
  normal packer path) — already tracked as open issue #301, not re-filed.
- **Dimension 5** — MMC1's 5-write serial control/bank loads and MMC3's R6(`$46`)/
  R7(`$47`) selects via `$8000`/`$8001` unchanged; #291's physical bank ordering
  (`PRG_A0`/`PRG_C0`/`PRG_80`/`PRG_FIX` = banks 60/61/62/63) unchanged in
  `mappers/mmc3.py:75-79`.
- **Dimension 6** — `MapperFactory.auto_select` ordering (nrom→mmc1→mmc3, smallest
  fits first) unchanged; `resolve_mapper`'s bytecode-engine force, direct-export
  bank-pack guard, and `enforce_direct_export_dpcm_mapper` DPCM-forces-MMC3 guard all
  still raise clean `ValueError`s (re-read `main.py:239-317`, unchanged since 07-06).
- **Dimension 7** — every mapper's `nes.cfg` segments still match what `main.asm`/
  `music.asm` reference; the default MMC3 pattern-compressed pipeline still assembles,
  links, and boots (re-verified live this pass, see verdict above). The new
  MAP-2026-07-18-1 finding is a *subprocess path-handling* bug, not a segment/symbol
  mismatch, so it's filed under Dimension 8, not 7.
- **Dimension 8 (remainder)** — `assemble()`/`link()` still raise `CompilationError` with
  `stderr` attached on nonzero return code; `check_toolchain()`/`get_version()` still
  guard `subprocess.run` with `try/except (FileNotFoundError, TimeoutExpired)`;
  `compile_rom()`'s broad `except Exception` still calls `traceback.print_exc()` under
  `--verbose`; `ROMCompiler.compile()` still invokes `mapper.generate_post_process_commands()`
  post-link when a mapper is passed. All unchanged since 07-06 and confirmed by the
  passing `tests/test_mappers.py` (39/39) and `tests/test_rom_validation_integration.py`
  (all real-CC65 integration tests, all absolute-path-based, all passing) this pass.
- **Dimension 9** — exact ROM size check (`mapper.prg_rom_size + 16`) unchanged and
  correct; `mapper is None` flat-32768 fallback still only used by callers that pass no
  mapper (defense-in-depth gap, not a new finding).
- **Dimension 10** — no doc drift found. `CLAUDE.md`/`README.md`/`docs/*.md` consistently
  describe MMC3 as the pipeline default; all `mmc1` doc hits are legitimate MMC1
  reference/comparison content, none reassert MMC1 as *the* default.

## Still-open, not re-filed

- **#301** (OPEN, LOW) — capacity pre-flight undercounts DPCM `.align 64` padding.
  Confirmed still present, still packer-guarded/unreachable through the normal pipeline
  (see Dimension 4 above).
- **#269 / PL-08** (OPEN) — per the analysis above, this is effectively resolved as a
  side effect of #297. Recommend the maintainer close it (or retarget it to the
  cosmetic "add `'auto'` to `compile --mapper`'s `choices=` for CLI symmetry" LOW) rather
  than treat it as a live gap; not re-filed as a new finding here.

## Dimension coverage map

| Dim | Area | Result |
|-----|------|--------|
| 1 | iNES header ↔ nes.cfg | Verified, all three mappers sum exactly to `prg_rom_size`; mapper nibbles correct. No mismatch. |
| 2 | Vectors + 60Hz NMI | `nmi`/`reset`/`irq` defined; `reset` enables NMI + `jsr init_music`; `nmi` `jsr update_music`; `VECTORS` at `$FFFA`. No finding. |
| 3 | APU init | MMC3's undefined-A `sta $E000` re-checked against `docs/MAPPER_MMC3_REFERENCE.md` — harmless (any value disables IRQ). No finding. |
| 4 | PRG capacity/overrun | Pre-flight wired and correct. #301 (LOW, DPCM align undercount) still open, unchanged, not re-filed. |
| 5 | Bank switching | MMC1 5-write load / MMC3 R6/R7 selects and #291 physical-bank order unchanged and correct. No finding. |
| 6 | MapperFactory auto-select | `auto_select` ordering and all `resolve_mapper` guards unchanged and correct. No finding. |
| 7 | Project builder buildability | Segments consistent for all mappers; default pipeline still boots (re-verified live). No finding. |
| 8 | Compiler / CC65 surfacing | **MAP-2026-07-18-1 (HIGH, NEW)**: relative `project_dir` doubles into the assemble/link source path and breaks the documented `compile` invocation for every mapper. Everything else (nonzero-exit handling, toolchain probing, `--verbose` traceback, post-process wiring) unchanged and correct. |
| 9 | ROM size check | Exact-size check unchanged and correct. No finding. |
| 10 | Default-mapper doc drift | No drift found. |

---

Next step:
```
/audit-publish docs/audits/AUDIT_MAPPERS_2026-07-18.md
```
