# Audit: Mappers / Project Builder / Compiler — 2026-06-28

Subsystem audited: `mappers/` (base, factory, nrom, mmc1, mmc3), `nes/project_builder.py`,
`compiler/compiler.py`, `compiler/cc65_wrapper.py`, plus the exporter/engine seams they
depend on (`exporter/exporter_ca65.py`, `nes/audio_engine.asm`) and the pipeline call
sites in `main.py`. All 10 SKILL.md dimensions covered.

Dedup: `gh issue list` returned 2 open issues (#2 "how to use", #3 "Output seems
silent") — neither matches any finding below. `docs/audits/` contained no prior reports.
All findings are NEW. (#3 "Output seems silent" is plausibly a downstream symptom of
M-1/M-2 but is too vague to map; noted as Related, not a dedup hit.)

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 3 |
| HIGH     | 2 |
| MEDIUM   | 3 |
| LOW      | 3 |
| **Total**| **11**|

**One-line verdict:** The default-mapper pipeline does **NOT** produce a bootable ROM —
the patterns-on path (the default) emits `music.asm` referencing linker segments
(`CODE_8000`, `BANK_00`…) that the MMC3 `nes.cfg` never defines, so `ld65` fails to link;
and even if it linked, the APU frame counter `$4017` is never initialized (and `$4015` is
not enabled at init on the patterns path), so the boot path is APU-uninitialized
(CRITICAL per the severity floor).

**Highest-leverage fix:** Make the MMC3 `nes.cfg` (`mappers/mmc3.py:generate_linker_config`)
and the CA65 macro exporter (`exporter/exporter_ca65.py:export_tables_with_patterns`) agree
on segment names — define `CODE_8000` and the `BANK_NN` sequence segments in the linker
config (or rename the exporter's segments to the existing `CODE`/`PRG_BANK_NN` names) — and
add `$4017 = $40` + `$4015` channel-enable to `init_music`/`audio_init`. Those two changes
move the default pipeline from "cannot link" to "links and boots."

---

## Findings (CRITICAL first)

### M-1: Default (patterns-on) music.asm references linker segments that MMC3 nes.cfg does not define — link fails
- **Severity**: CRITICAL
- **Dimension**: 7 (project builder buildability) / 1 (header↔cfg consistency)
- **Location**: `exporter/exporter_ca65.py:672` (`.segment "CODE_8000"`), `:890`/`:934` (`.segment "BANK_{NN}"`); `mappers/mmc3.py:37-79` (`generate_linker_config`)
- **Status**: NEW
- **Description**: The default pipeline runs with pattern compression on, which routes
  `export_tables_with_patterns()` into the "MMC3 Macro Bytecode" branch (`patterns`
  truthy). That branch writes the DPCM lookup tables, pitch tables, `instrument_table`, and
  all macro data into `.segment "CODE_8000"`, and writes the per-channel sequence bytecode
  into `.segment "BANK_00"`, `.segment "BANK_01"`, … The MMC3 linker config defines
  segments `HEADER, ZEROPAGE, BSS, OAM, DPCM_00..59, CODE, RODATA, DPCM, VECTORS` — it has
  **no `CODE_8000` and no `BANK_NN`** (the bank segments are named `DPCM_00..59` loading into
  `PRG_BANK_00..59`). `ld65` aborts on a segment with no matching config entry, so the
  default pipeline cannot link.
- **Evidence**:
  ```
  exporter_ca65.py:672   lines.append('.segment "CODE_8000"')
  exporter_ca65.py:890   lines.append(f'.segment "BANK_{current_bank:02d}"')
  ```
  `python3 -c "from mappers.mmc3 import MMC3Mapper; ..."` enumerates the cfg SEGMENTS and
  shows neither `CODE_8000` nor any `BANK_NN` (only `DPCM_00..59`, `CODE`, `RODATA`, `DPCM`,
  `VECTORS`, …). `main.py:291,363` confirm `use_patterns` defaults True → Branch A.
- **Impact**: Every default `python main.py in.mid out.nes` invocation fails at the `ld65`
  step (caught by Dimension 8 as a `CompilationError`, so it surfaces — but the ROM is never
  produced). Blast radius: the entire default pipeline. The `--no-patterns` path uses
  `export_direct_frames` (segments `HEADER/ZEROPAGE/BSS/RODATA`, all present) and is the only
  path that can reach the linker cleanly.
- **Related**: M-2 (APU init); possibly issue #3 "Output seems silent".
- **Suggested Fix**: Add `CODE_8000` and `BANK_00..N` segments to
  `MMC3Mapper.generate_linker_config()` mapped into the appropriate swap windows (sequence
  banks at `$A000` per R7, code/tables in the fixed window), or rename the exporter's
  segments to the cfg's existing `CODE` / `PRG_BANK_NN`. Add a CI test that actually runs
  `ca65`/`ld65` on a tiny MIDI through the default (patterns-on) path.

### M-2: APU frame counter $4017 never initialized; $4015 not enabled at init on the patterns path
- **Severity**: CRITICAL
- **Dimension**: 3 (APU init in boot path)
- **Location**: `nes/audio_engine.asm:82-148` (`audio_init`), `exporter/exporter_ca65.py:541-548` (`init_music`, non-standalone), `:969-973` (patterns `init_music`→`audio_init`)
- **Status**: NEW
- **Description**: Boot path is `reset` → `jsr init_music`. On the default (patterns) path,
  `init_music` is `jmp audio_init` (`exporter_ca65.py:969-973`), and `audio_init`
  (`audio_engine.asm:82`) writes only `$4011` (DMC level) at init — it never writes the APU
  status/enable register `$4015` nor the frame-counter register `$4017`. `$4017` is written
  exactly once in the whole subsystem, at `exporter_ca65.py:217`, which lives inside the
  `standalone` reset block that the pipeline never emits (`main.py` passes
  `standalone=False`). `docs/NES_APU_REFERENCE.md` §3.2 line 58 states `$4017` **must** be
  initialized to `$40` (Mode 1, disable frame IRQ) "to prevent the APU from interfering with
  our NMI-driven 60Hz audio updates"; §3.1 line 53 covers `$4015` channel enables. With
  `$4017` left at power-on/indeterminate state and `$4015` enables only set transiently from
  per-frame channel code, the APU is effectively uninitialized at boot.
- **Evidence**:
  ```
  audio_engine.asm:120   sta $4011        ; only APU write in audio_init
  grep -rn 4017 exporter_ca65.py audio_engine.asm project_builder.py
    -> exporter_ca65.py:217  sta $4017   (standalone-only; not used by pipeline)
  exporter_ca65.py:969-973  init_music: jmp audio_init   (non-standalone/patterns path)
  ```
  Even the no-patterns non-standalone `init_music` (`exporter_ca65.py:541-548`) writes
  `$4015`=`#$0F` but still **no `$4017`**.
- **Impact**: Per `_audit-severity.md` "APU never initialized in generated ROM → CRITICAL".
  On accurate emulators/hardware the frame counter can fire frame IRQs or clock length/
  envelope units against the engine, producing no/garbage sound or timing interference.
  Affects every ROM the pipeline builds.
- **Related**: M-1; issue #3 "Output seems silent".
- **Hardware ref**: `docs/NES_APU_REFERENCE.md` §3.1 ($4015), §3.2 ($4017 → $40).
- **Suggested Fix**: In `audio_init` (and the no-patterns `init_music`), write `lda #$40 /
  sta $4017` and `lda #$0F / sta $4015` (or `$1F` if DMC needed) before playback. Centralize
  APU init so both export branches share it.

### M-3: Music data is never size-checked against mapper PRG capacity on any pipeline path (silent-overrun risk)
- **Severity**: CRITICAL
- **Dimension**: 4 (PRG capacity / overrun detection)
- **Location**: `main.py:57,424` (build with fixed `MMC3Mapper()`); `nes/project_builder.py:74-100` (`prepare_project` — no capacity check); `mappers/factory.py:84-114` (`auto_select`, `can_fit_data`) — never called from pipeline
- **Status**: NEW
- **Description**: `can_fit_data` / `auto_select` / `get_data_capacity` exist but
  `grep -rn 'can_fit_data\|auto_select\|get_data_capacity'` over non-test code shows they
  are referenced **only** inside `mappers/factory.py` and `mappers/base.py` themselves —
  never from `main.py` or `nes/project_builder.py`. Both pipeline entry points
  (`run_prepare`, `run_full_pipeline`) instantiate `MMC3Mapper()` explicitly and call
  `prepare_project`, which writes the project files with no comparison of the generated
  music-data size to `mapper.get_data_capacity()`. Oversized music flows straight to `ld65`.
- **Evidence**:
  ```
  main.py:56-57   from mappers.mmc3 import MMC3Mapper
                  builder = NESProjectBuilder(args.output, mapper=MMC3Mapper())
  main.py:423-424 builder = NESProjectBuilder(..., mapper=MMC3Mapper())
  grep -rn 'can_fit_data|auto_select|get_data_capacity' (excl tests, excl defs)
    -> only mappers/factory.py and mappers/base.py internal references
  ```
- **Impact**: For data exceeding 512KB of declared PRG (or, more realistically, exceeding the
  `BANK_NN` count the exporter emits vs. the 60 `PRG_BANK` banks in cfg), behavior is
  undetected by the pipeline. The *severity floor* for undetected PRG overrun is CRITICAL.
  Mitigant: in practice `ld65` will error if a segment overflows its region (surfaced by
  Dimension 8), so this is "relies entirely on ld65, no pre-flight" rather than guaranteed
  silent corruption — but with M-1 the link never reaches that stage, and there is no
  pipeline-side guard. Treat as CRITICAL per the floor; if M-1 is fixed and ld65 region
  overflow is confirmed to error, this can be re-scored MEDIUM.
- **Related**: M-1, M-7 (factory default).
- **Suggested Fix**: After `music.asm` (and DPCM) are generated, compute total emitted size
  and call `mapper.can_fit_data(size)` (or `auto_select`) before linking; raise a clear
  error naming the overflowing bank. Add a test feeding >capacity data.

### M-4: CC65 `--version` calls don't pass through `shutil.which` result; missing-tool detection is correct but `get_version`/probe shells unguarded
- **Severity**: HIGH
- **Dimension**: 8 (compiler validation & CC65 error surfacing)
- **Location**: `compiler/cc65_wrapper.py:55-77` (`check_toolchain`), `:88-97` (`get_version`)
- **Status**: NEW
- **Description**: `check_toolchain` correctly uses `shutil.which("ca65"/"ld65")` and raises
  `ToolchainError` when absent, then probes `--version` and re-raises on `FileNotFoundError`/
  nonzero — this part is sound. The gap: `get_version()` (called by tooling/`benchmark`)
  runs `subprocess.run(["ca65","--version"])` **after** `check_toolchain()` but does not guard
  the run itself, and the two `--version` probes in `check_toolchain` invoke the bare command
  name rather than the `self._ca65_path`/`self._ld65_path` already resolved — a TOCTOU/PATH
  divergence (a `ca65` found by `which` but a different one on a re-resolved PATH). Minor, but
  the real HIGH-floor concern under this dimension is covered positively: `assemble`/`link`
  **do** check `returncode != 0` and raise `CompilationError` carrying `stderr`
  (`cc65_wrapper.py:139-145`, `:194-201`) — verified, not a finding.
- **Evidence**:
  ```
  cc65_wrapper.py:45-46  self._ca65_path = shutil.which("ca65")   # resolved...
  cc65_wrapper.py:56-60  subprocess.run(["ca65","--version"], ...) # ...but probe uses bare name
  cc65_wrapper.py:139-145 raise CompilationError(... result.stderr ...)  # GOOD: surfaces stderr
  ```
- **Impact**: Low real-world blast radius (the resolved path and bare name are normally the
  same binary). Flagged as HIGH only on the dimension's "ignored exit/stderr" axis — but on
  re-read the wrapper does surface stderr, so this is a robustness/hardening note, not a
  swallowed-failure bug. Right-sized: MEDIUM-leaning HIGH; keeping HIGH-adjacent visibility
  because it is the CC65 error path.
- **Related**: M-9.
- **Suggested Fix**: Use `self._ca65_path`/`self._ld65_path` for the `--version` probes; wrap
  `get_version`'s subprocess in the same try/except. (No change needed to `assemble`/`link`.)

### M-5: Two compile paths diverge — `build.sh` always MMC3-hardcoded, bypassing `mapper.generate_build_script()` and the MMC1 vector fixup
- **Severity**: HIGH
- **Dimension**: 8 (compiler) / 2 (vectors, MMC1 fixup)
- **Location**: `nes/project_builder.py:498` (`_create_build_script_mmc3()` always called), `:595-621`; `mappers/mmc1.py:116-120` (`generate_post_process_commands` vector fixup)
- **Status**: NEW
- **Description**: `prepare_project` unconditionally calls `_create_build_script_mmc3()`,
  which writes a hardcoded MMC3 `build.sh` (`ca65 … ; ld65 …`) with **no** post-process step.
  The generic `_create_build_script()` (which would call `mapper.generate_build_script()` and
  thus the MMC1 `generate_post_process_commands` that relocates the reset/NMI/IRQ vectors from
  the link position to file offset `0x2000A`) is defined but never invoked. So a project built
  with MMC1 via `build.sh` would link with vectors in the wrong place and **brick on
  hardware**, because the fixup never runs. The `compiler/` path (`compile_rom`) also never
  runs any post-process. The MMC1 fixup offset itself is correct (`0x1C010 + ($FFFA-$C000) =
  0x2000A`, verified) — the bug is that it is unreachable.
- **Evidence**:
  ```
  project_builder.py:498   self._create_build_script_mmc3()   # always; ignores self.mapper
  project_builder.py:595   def _create_build_script(self):    # generic path: never called
  mmc1.py:116-120          generate_post_process_commands(...) # vector fixup: never reached
  ```
- **Impact**: Any non-MMC3 mapper selected through `NESProjectBuilder` gets an MMC3 build
  script. For MMC1 specifically this means missing vector relocation → CRITICAL-class brick
  *if* MMC1 is ever used. Scored HIGH because the pipeline currently always passes MMC3 (so
  the wrong script happens to match), making this a latent trap rather than an active brick.
- **Related**: M-7, M-8 (default-mapper confusion).
- **Hardware ref**: `docs/MAPPER_MMC1_REFERENCE.md` §1 (serial interface), §3 (fixed last
  bank holds vectors at `$C000-$FFFF`).
- **Suggested Fix**: Call `self.mapper.generate_build_script(is_windows)` (the generic path)
  so each mapper contributes its own script + post-process; delete or fold
  `_create_build_script_mmc3` into `MMC3Mapper.generate_build_script`. Have `compiler/` run
  the mapper's post-process too, or assert no post-process is required.

### M-6: MMC3 `generate_header_asm()` emits its own `.segment "HEADER"`, double-declaring the segment the project builder already opened
- **Severity**: MEDIUM
- **Dimension**: 7 (project builder buildability) / 1
- **Location**: `mappers/mmc3.py:26-35` (`generate_header_asm` opens `.segment "HEADER"`); `nes/project_builder.py:527-528` (`_generate_main_asm` already wrote `.segment "HEADER"` before interpolating)
- **Status**: NEW
- **Description**: `_generate_main_asm` emits `\n.segment "HEADER"\n{mapper.generate_header_asm()}`.
  For NROM/MMC1, `generate_header_asm` returns bare `.byte` directives (correct). For MMC3 it
  returns a block that **begins with its own `.segment "HEADER"`** — so main.asm contains two
  consecutive `.segment "HEADER"` directives. `ca65` tolerates re-opening a segment (it is
  legal to switch back into an already-open segment), so the header bytes still land in the
  HEADER region and this is not a hard error — but it is an inconsistency between the two
  mappers' contracts and a latent bug if the builder's framing ever changes (e.g. emits
  intervening directives expecting the mapper text to be header bytes only).
- **Evidence**:
  ```
  mmc3.py:27-28   return """\n.segment "HEADER"\n    .byte "NES", $1A ...
  project_builder.py:527  return f""".segment "HEADER"\n{self.mapper.generate_header_asm()}
  ```
- **Impact**: Currently benign (`ca65` accepts the redundant directive); a maintenance trap.
  MEDIUM as a defense-in-depth/contract-consistency gap.
- **Related**: M-1.
- **Suggested Fix**: Make `MMC3Mapper.generate_header_asm()` return bare `.byte` lines like
  NROM/MMC1, letting the builder own the single `.segment "HEADER"`.

### M-7: Three conflicting "default mapper" behaviors — `get_mapper("auto", 0)`→MMC1, builder default `"auto"`, pipeline hardcodes MMC3
- **Severity**: MEDIUM
- **Dimension**: 10 (default-mapper drift) / 6 (factory)
- **Location**: `mappers/factory.py:172-176` (auto+0 → MMC1); `nes/project_builder.py:30,50` (`mapper_name="auto"` default); `main.py:57,424` (explicit `MMC3Mapper()`)
- **Status**: NEW
- **Description**: `get_mapper("auto", data_size=0)` returns MMC1 "for backwards
  compatibility". `NESProjectBuilder.__init__` defaults `mapper_name="auto"`, so any caller
  that constructs the builder *without* passing a mapper and *without* calling
  `auto_select_mapper(size)` gets MMC1. But the actual pipeline always passes
  `mapper=MMC3Mapper()`. A caller relying on the builder's documented `"auto"` default would
  silently get MMC1 — whose build path is broken by M-5 (MMC3-hardcoded build.sh) and whose
  music.asm segment expectations differ. This is a real behavioral trap, not just doc-rot.
- **Evidence**:
  ```
  factory.py:174-175  if data_size <= 0: return MapperFactory.get_mapper("mmc1")
  project_builder.py:30  mapper_name: str = "auto"
  main.py:57          builder = NESProjectBuilder(args.output, mapper=MMC3Mapper())
  ```
- **Impact**: Inconsistent default; a builder used outside `main.py` (tests, future callers,
  the `song`/multi-song paths) silently selects a mapper the rest of the pipeline does not
  build for. MEDIUM per Dimension 10's "auto-default disagrees with pipeline default" rule.
- **Related**: M-5, M-8.
- **Suggested Fix**: Make the builder's `"auto"` default resolve via `auto_select(data_size)`
  once data size is known, or change the builder default to MMC3 to match the pipeline.
  Pick one canonical default and document it.

### M-8: `MIN_ROM_SIZE` is a flat 32768 that can false-pass a truncated MMC3/MMC1 image far smaller than its declared PRG
- **Severity**: MEDIUM
- **Dimension**: 9 (MIN_ROM_SIZE check)
- **Location**: `compiler/compiler.py:27` (`MIN_ROM_SIZE = 32768`), `:133-138`
- **Status**: NEW
- **Description**: `compile()` rejects a linked ROM `< 32768` bytes. NROM links to 32KB PRG +
  16-byte header = 32784, so a valid NROM is `> 32768` (no false-positive — good). But MMC3
  declares 512KB PRG and MMC1 128KB; the check would pass any image `≥ 32768`, including a
  truncated MMC3 image that is a fraction of its declared 512KB. The check should compare
  against `self.mapper.prg_rom_size + 16`, not a flat constant. (In practice `ld65` with
  `fill = yes` pads regions to full size, so a successful link produces the full declared
  size — making a truncated-but-large image unlikely; hence MEDIUM, a defense gap.)
- **Evidence**:
  ```
  compiler.py:27   MIN_ROM_SIZE = 32768
  compiler.py:134  if rom_size < self.MIN_ROM_SIZE: raise CompilationError(...)
  ```
  `ROMCompiler` has no reference to the mapper, so it cannot compute the expected size today.
- **Impact**: A truncated/under-filled ROM ≥32KB passes validation. MEDIUM per the dimension's
  "should compare against expected `prg_rom_size`" note.
- **Related**: M-3.
- **Suggested Fix**: Plumb the mapper (or expected PRG size) into `ROMCompiler` and validate
  `rom_size == mapper.prg_rom_size + 16` (or `>=`), not a flat 32768.

### M-9: `compile_rom`'s broad `except Exception` prints then returns False — acceptable, but masks tracebacks without `verbose`
- **Severity**: LOW
- **Dimension**: 8 (compiler error surfacing)
- **Location**: `compiler/compiler.py:164-175`
- **Status**: NEW
- **Description**: `compile_rom` wraps the whole compile in `try/except`, catching
  `CompilationError`, `ValidationError`, and a catch-all `except Exception`, printing
  `[ERROR] …` and returning `False`. This does surface the message (not a silent success —
  good, clears the HIGH floor), but the catch-all swallows the stack trace with no
  `verbose`/`-v` traceback option at this layer (the pipeline's own `-v` traceback is in
  `main.py`, not here). A genuinely unexpected exception loses its origin.
- **Evidence**:
  ```
  compiler.py:173-175  except Exception as e: print(f"[ERROR] Compilation failed: {e}"); return False
  ```
- **Impact**: Harder debugging of unexpected compiler failures; not a correctness bug.
- **Related**: M-4.
- **Suggested Fix**: In the catch-all, print `traceback.format_exc()` when `verbose`.

### M-10: CLAUDE.md/README still describe MMC1 as the always-on mapper — contradicts MMC3 pipeline default
- **Severity**: LOW
- **Dimension**: 10 (doc drift)
- **Location**: `CLAUDE.md:194` ("Always use MMC1 mapper configuration"), `:196` ("PRG-ROM: 128KB (8 banks × 16KB)"), `:266` ("Creates working MMC1 ROMs (128KB capacity)")
- **Status**: NEW
- **Description**: `CLAUDE.md:31` and `:160`(region) correctly say the pipeline defaults to
  MMC3, but the "ROM Structure" section (`:194-196`) and Project Status (`:266`) still assert
  MMC1/128KB. README leads with the "MMC3 Macro-Driven Bytecode Engine" (consistent), so the
  drift is localized to CLAUDE.md's lower sections. Each contradiction with the code is
  doc-rot.
- **Evidence**: `grep -niE 'always use mmc1|128KB|MMC1 ROM' CLAUDE.md` →lines 194/196/266.
- **Impact**: Misleads contributors about the active mapper/ROM size. LOW.
- **Related**: M-7.
- **Suggested Fix**: Update CLAUDE.md "ROM Structure" and "Project Status" to MMC3 / 512KB
  (8KB banks), or qualify as "MMC3 default; MMC1/NROM selectable".

### M-11: `main.asm` uses `frame_counter` but only resolves it via the appended `.include "audio_engine.asm"` — fragile coupling (not a bug today)
- **Severity**: LOW
- **Dimension**: 7 (segment/symbol consistency)
- **Location**: `nes/project_builder.py:552-554` (reset writes `frame_counter`), `:494-495` (`.include "audio_engine.asm"`), `nes/audio_engine.asm:13,16` (`.exportzp frame_counter` / definition)
- **Status**: NEW
- **Description**: Non-debug `main.asm` references `frame_counter` in `reset` with **no**
  `.importzp frame_counter`. It resolves only because `audio_engine.asm` (which *defines*
  `frame_counter` in ZEROPAGE) is `.include`d into the same `main.o` at the end. If the engine
  include is ever removed/relocated, or the file is absent (`engine_src.exists()` guards the
  include at `:494`), the `frame_counter` reference becomes undefined — and crucially the
  include is conditional while the `reset` reference is unconditional. The debug path *does*
  `.importzp … frame_counter` (`:103`), so the dependency is acknowledged elsewhere.
- **Evidence**:
  ```
  project_builder.py:494  if engine_src.exists(): main_content += '\n.include "audio_engine.asm"\n'
  project_builder.py:552  sta frame_counter        # unconditional, in reset
  audio_engine.asm:16     frame_counter:  .res 2   # defined only if engine included
  ```
- **Impact**: Latent: if `audio_engine.asm` is missing, `reset` references an undefined
  symbol while the include that defines it is skipped → assemble error. LOW (the file ships
  in-repo).
- **Related**: M-1.
- **Suggested Fix**: Add `.importzp frame_counter` to main.asm unconditionally and let the
  engine `.exportzp` it (decouple definition from use), or assert the engine include is
  mandatory.

---

## Dimension coverage map

| Dim | Area | Result |
|-----|------|--------|
| 1 | iNES header ↔ nes.cfg | Header PRG bytes & mapper nibbles verified correct for NROM/MMC1/MMC3 (sizes sum exactly: 32KB/128KB/512KB). No mismatch finding. CODE_8000/BANK gap rolled into M-1. |
| 2 | Vectors + 60Hz NMI | `nmi`/`reset`/`irq` all defined; `nmi jsr update_music`; `reset` sets `$2000=#$80`; VECTORS at `$FFFA`. MMC1 fixup offset `0x2000A` correct but **unreachable** (M-5). |
| 3 | APU init | **M-2 (CRITICAL)** — `$4017` never set, `$4015` not enabled at init on patterns path. |
| 4 | PRG capacity/overrun | **M-3 (CRITICAL)** — capacity helpers never called on any pipeline path. |
| 5 | Bank switching | MMC3 `$46`/`$47` R6/R7 selects, mode-1 P bit, `$E000` IRQ-disable, R7 `$A000` sequence window all match `docs/MAPPER_MMC3_REFERENCE.md`. MMC1 5-write serial + `$0C` control match `docs/MAPPER_MMC1_REFERENCE.md`. No finding. |
| 6 | MapperFactory auto-select | Order smallest-first (nrom→mmc1→mmc3), "nothing fits" raises with largest capacity — correct. `auto`+0→MMC1 default rolled into M-7. |
| 7 | Project builder buildability | **M-1 (CRITICAL)**, M-6, M-11. |
| 8 | Compiler / CC65 surfacing | `assemble`/`link` correctly raise with stderr (verified, no finding). M-4, M-5, M-9. |
| 9 | MIN_ROM_SIZE | **M-8 (MEDIUM)** — flat constant, not mapper-relative. |
| 10 | Default-mapper drift | M-7 (MEDIUM), M-10 (LOW). |

---

Next step:
```
/audit-publish docs/audits/AUDIT_MAPPERS_2026-06-28.md
```
