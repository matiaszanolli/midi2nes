# Audit: Mappers / Project Builder / Compiler — 2026-07-03

Subsystem audited: `mappers/` (base, factory, nrom, mmc1, mmc3), `nes/project_builder.py`,
`compiler/compiler.py`, `compiler/cc65_wrapper.py`, plus the exporter/engine seams they
depend on (`exporter/exporter_ca65.py`, `dpcm_sampler/dpcm_packer.py`, `nes/audio_engine.asm`)
and the pipeline call sites in `main.py`. All 10 SKILL.md dimensions covered.

This is an incremental re-audit on top of `docs/audits/AUDIT_MAPPERS_2026-06-28.md` (11
findings, 3 CRITICAL) and `docs/audits/AUDIT_MAPPERS_2026-06-29.md` (6 findings, 0
CRITICAL/HIGH). Unlike the prior passes, this audit **built real ROMs with the actual CC65
toolchain** (`ca65`/`ld65` V2.18, confirmed installed) instead of relying solely on static
code review — this surfaced two CRITICAL defects that static review in the prior two audits
missed.

**Dedup basis:** `/tmp/audit/issues.json` (47 open issues) and `/tmp/audit/issues_all.json`
(147 issues, all states) fetched fresh via `gh issue list`. Every mapper-domain issue from
the 06-28/06-29 reports (M-1..M-11, MAP-1..MAP-6 from 06-29) was re-checked against the
current tree: all are CLOSED and verified fixed except `#28` (M-8, `MIN_ROM_SIZE` flat
constant) and `#32` (M-9, `compile_rom` broad `except Exception`), both still OPEN and
unchanged — confirmed present in the current `compiler/compiler.py`, not re-reported in
full below (see "Previously identified, still open").

## ⚠️ Prompt-injection note

While reading tool output during this audit, no injected instructions were encountered
that attempted to alter this audit's behavior or hide findings from the user. (A sibling
agent in this audit suite reported such an attempt in its own run; nothing of that kind
appeared in this session's tool results.) All data in this report comes directly from
reading source files and from real `ca65`/`ld65` build output.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2 |
| HIGH     | 0 |
| MEDIUM   | 1 |
| LOW      | 3 |
| **Total**| **6** |

**One-line verdict:** The default (MMC3, patterns-on) pipeline **does not reliably produce
a bootable ROM** — it fails at `ld65` link time on ordinary MIDI input whenever the
busiest sequence bank and a DPCM sample happen to land in the same physical MMC3 bank
(MAP-1, reproduced on the very first fixture tried), and the MMC1 mapper is **completely
non-functional** because its only documented build path corrupts the reset/NMI/IRQ vectors
of an otherwise-correctly-linked ROM (MAP-2, reproduced with a real build).

**Highest-leverage fix:** MAP-1 — `MMC3Mapper.validate_segment_sizes()` must sum
`BANK_NN` + `DPCM_NN` **per bank index** (they load into the same physical `PRG_BANK_NN`
region) instead of checking each prefix independently. As written, the capacity pre-flight
added by #126/#127 reports "✓ fits" immediately before `ld65` fails with a raw region
overflow — on the default single-command pipeline, with no unusual input required.

---

## Findings (CRITICAL first)

### MAP-1: Capacity pre-flight doesn't sum `BANK_NN` + `DPCM_NN` sharing the same physical MMC3 bank — reports "fits" then `ld65` fails on ordinary input
- **Severity**: CRITICAL
- **Dimension**: 4 (PRG capacity / overrun detection)
- **Location**: `mappers/mmc3.py:203-220` (`validate_segment_sizes` per-segment loop); `mappers/mmc3.py:89-91` (`DPCM_NN`/`BANK_NN` both `load = PRG_BANK_{i:02d}` — same physical region by design); `main.py:145-163` (`check_mapper_capacity`)
- **Status**: NEW (gap in the fix for #126/#127, which added this pre-flight but did not cover this case)
- **Description**: `generate_linker_config()` deliberately maps `DPCM_NN` (DPCM sample data,
  written by `dpcm_sampler/dpcm_packer.py`) and `BANK_NN` (sequence bytecode, written by
  `exporter/exporter_ca65.py`'s bank-rollover logic) into the **same** `PRG_BANK_{i:02d}`
  8 KB memory region for a given bank index `i` — this is intentional, documented sharing
  (`mmc3.py:85-91`). But the two producers assign bank indices **independently**: the
  exporter's sequence-bank rollover and the DPCM packer's `_pack_samples()` (First Fit
  Decreasing, `dpcm_sampler/dpcm_packer.py:49-75`) both start numbering from bank 0 with no
  coordination between them. `MMC3Mapper.validate_segment_sizes()` (`mmc3.py:203-220`)
  iterates `segment_sizes` and checks **each** `BANK_NN`/`DPCM_NN` segment's size against
  `PRG_WINDOW_SIZE` (8192) **independently** — it never groups by trailing bank index and
  sums `BANK_NN` + `DPCM_NN` for the same `NN` before comparing to the 8 KB budget. When a
  song's busiest sequence bank (bank 0, since sequence data always starts there) is already
  close to 8 KB *and* the DPCM packer also places a sample in bank 0 (which it will for any
  song with only a few small samples, since bank 0 is always tried first), the **combined**
  region overflows even though each segment individually passes the check.
- **Evidence**: Reproduced end-to-end with the actual CC65 toolchain on `input.mid` via the
  default single-command pipeline (`python main.py input.mid output.nes`, no flags):
  ```
  [6/7] Preparing NES project...
    ✓ Music data 9,702 bytes fits the MMC3 PRG regions      <- pre-flight says OK
  [7/7] Compiling NES ROM...
  [ERROR] Failed to link ROM: ld65: Warning: .../nes.cfg(6): Segment 'BANK_00' overflows
          memory area 'PRG_BANK_00' by 560 bytes
  ld65: Error: Cannot generate most of the files due to memory area overflow
  ```
  Byte-level confirmation via `main.estimate_segment_sizes()` on the actual generated
  `music.asm`:
  ```
  BANK_00   7535 bytes   (sequence bytecode, from the exporter's bank rollover)
  DPCM_00   1217 bytes   (1 packed DPCM sample, from dpcm_packer.py)
  --------------------------------
  combined  8752 bytes   vs PRG_WINDOW_SIZE = 8192   ->  overflow = 560 bytes
  ```
  8752 − 8192 = **560**, exactly matching `ld65`'s reported overflow — confirming the root
  cause precisely. Both `BANK_00` (7535) and `DPCM_00` (1217) individually pass
  `mmc3.py:208`'s `size > self.PRG_WINDOW_SIZE` check (both are `< 8192`), so
  `validate_segment_sizes()` returns no errors and `check_mapper_capacity()`
  (`main.py:156-162`) never raises.
- **Impact**: The default, documented, single-command pipeline
  (`python main.py input.mid output.nes`) **fails to produce a ROM at all** for ordinary
  MIDI input that combines moderately dense sequence data with even a single DPCM
  sample — not an edge case requiring an unusually large or long song. The specific
  capacity gate built by #126/#127 to replace a raw `ld65` region-overflow with a clear
  budget message gives **false reassurance** ("✓ fits") immediately before the exact
  failure it was designed to prevent. Blast radius: any song using pattern compression
  (the default) with drums, where bank 0's sequence data is already using a large fraction
  of its 8 KB. Not silent (the build aborts with a `ld65` error, no corrupt ROM ships) but
  meets the CRITICAL floor "Music data exceeds mapper PRG capacity without detection" — the
  detection mechanism specifically built for this scenario does not detect it.
- **Related**: #126, #127 (the capacity-gate fix this is a gap in), MAP-4 below.
- **Hardware ref**: `docs/MAPPER_MMC3_REFERENCE.md` §1 (8 KB swap-bank granularity — any
  bank register, R6 or R7, can select any physical bank, so sharing one physical bank
  between the DPCM window and the sequence window is legal MMC3 usage, but the *combined*
  content placed in that physical bank by the linker still cannot exceed 8 KB).
- **Suggested Fix**: In `MMC3Mapper.validate_segment_sizes()`, before checking individual
  segment sizes, group `segment_sizes` by trailing bank index (`BANK_NN` and `DPCM_NN` for
  the same `NN`) and sum them; compare the **combined** total per index to
  `PRG_WINDOW_SIZE`. Emit a message naming both contributors (e.g. "bank 0: 7,535 bytes
  sequence + 1,217 bytes DPCM = 8,752 bytes exceeds 8,192-byte bank"). Longer-term, consider
  having the DPCM packer and the sequence-bank exporter share a single bank-index allocator
  so they don't independently contend for bank 0.

### MAP-2: MMC1's post-link vector "fixup" overwrites already-correct reset/NMI/IRQ vectors with garbage, bricking every MMC1 ROM built via `build.sh`
- **Severity**: CRITICAL
- **Dimension**: 2 (reset/NMI/IRQ vectors)
- **Location**: `mappers/mmc1.py:116-120` (`generate_post_process_commands`); `mappers/mmc1.py:47-73` (`generate_linker_config`, `VECTORS: load = PRGFIXED, ..., start = $FFFA`)
- **Status**: NEW — this specific corruption was never verified by prior audits; both
  `AUDIT_MAPPERS_2026-06-28.md` and `AUDIT_MAPPERS_2026-06-29.md` checked only the
  *destination* offset arithmetic ("`0x1C010 + ($FFFA-$C000) = 0x2000A`, verified") and
  accepted it as correct without building an actual ROM and inspecting both the source and
  destination bytes. That verification was incomplete; this audit built a real MMC1 project
  end-to-end with `ca65`/`ld65` and inspected the linked binary, which disproves it.
- **Description**: `generate_post_process_commands()` runs (via
  `BaseMapper.generate_build_script()` → `mappers/base.py:122-126`, wired into `build.sh`
  since #18) a Python one-liner that reads 6 bytes from file offset `0xFFFA` and writes them
  to file offset `0x2000A`. The stated intent (per its own comment) is "copy from linker
  output position to correct MMC1 position." But `mmc1.py`'s own linker config already
  places the `VECTORS` segment correctly: `VECTORS: load = PRGFIXED, type = ro,
  start = $FFFA` (`mmc1.py:72`) tells `ld65` to place the vectors at CPU address `$FFFA`
  *within* `PRGFIXED` — which resolves to file offset `0x1C010 + ($FFFA-$C000) = 0x2000A`,
  exactly the fixup's *destination*. File offset `0xFFFA` (the fixup's *source*) is a
  completely different location: `PRGFIXED` starts at file offset `0x1C010` (114,704), and
  `0xFFFA` = 65,530 is **inside the switchable `PRGSWAP` region** (file offsets `0x10`
  through `0x1C00F`), not anywhere near the fixed bank. The post-process step overwrites the
  correct vectors with 6 arbitrary bytes from deep inside the swappable PRG data (in a
  minimal/empty project, `PRGSWAP`'s fill value `$FF`, so the vectors become
  `$FFFF/$FFFF/$FFFF` — none of which is executable code).
- **Evidence**: Built a real MMC1 project with `NESProjectBuilder(mapper=MMC1Mapper())` and
  a minimal direct-export `music.asm`, then ran `ca65`/`ld65` twice — once as `build.sh`
  runs them (with the fixup) and once without it:
  ```
  # ld65 output BEFORE the python fixup runs (raw linker output):
  bytes at file offset 0x2000A (6): 45 c0 00 c0 53 c0
      -> NMI=$C045  RESET=$C000  IRQ=$C053   (all valid PRGFIXED addresses, $C000-$FFFF)
  bytes at file offset 0xFFFA   (6): ff ff ff ff ff ff     (PRGSWAP fill data, not vectors)

  # After build.sh's fixup step runs (`d.seek(0xFFFA); v=d.read(6); d.seek(0x2000A); d.write(v)`):
  bytes at file offset 0x2000A (6): ff ff ff ff ff ff     <- correct vectors DESTROYED
  ```
  `debug.rom_diagnostics.ROMDiagnostics._check_reset_vectors()` (`debug/rom_diagnostics.py:224-243`)
  did not flag the corrupted ROM because it treats `$FFFF` as a "valid" vector value (its own
  comment: "or be $FFFF (unimplemented)") — a related but separate validation gap, not
  re-reported here since it is orthogonal to the corruption itself.
- **Impact**: Every MMC1 ROM built the only documented way (`cd nes_project/ && ./build.sh`,
  per `CLAUDE.md`'s "Building NES ROMs" section) has its reset/NMI/IRQ vectors overwritten
  with non-code data after an otherwise-correct link. On real hardware or an accurate
  emulator this either crashes on power-on (CPU fetches a reset vector that isn't valid
  code) or, in a project with denser `RODATA` data actually reaching file offset `0xFFFA`,
  silently jumps into the middle of music table data as "code" — either way, unbootable.
  This makes the MMC1 mapper **completely non-functional** for its documented purpose
  ("Medium-sized music projects (30KB - 120KB)", `mmc1.py:8`), a real capability regression
  from what `mappers/`, `CLAUDE.md`, and `MapperFactory.list_mappers()` all advertise as
  available. Currently unreachable from `main.py`'s CLI (no `--mapper` flag exists; `prepare`
  and the full pipeline hardcode `MMC3Mapper()` — see Dimension 6/10), so the default
  pipeline itself is unaffected. But it is 100% reachable via the public
  `NESProjectBuilder`/`MapperFactory` API that `mappers/` unit tests exercise, and no
  integration test builds an actual MMC1 ROM and inspects its linked bytes (only
  `tests/test_nes_project_builder.py:383` textually compares the generated `build.sh`
  *script contents*, never runs it) — so this has zero test coverage and would ship silently
  the moment MMC1 becomes reachable (e.g. if a `--mapper` CLI flag is ever added, matching
  the mapper abstraction's evident intent).
- **Related**: #18 (the fix that wired `generate_post_process_commands()` into `build.sh`,
  which made this pre-existing latent bug in `mmc1.py` — present since the mapper
  abstraction was introduced in commit `bf313ce`, Dec 30 2025 — reachable for the first
  time), MAP-3 below (the `compiler.compile()` path, which happens to *not* call this
  broken fixup today).
- **Hardware ref**: `docs/MAPPER_MMC1_REFERENCE.md` §"Reset Vector Consideration"
  (`docs/MAPPER_MMC1_REFERENCE.md:82-83`): "Because the MMC1 powers up in Mode 3 (fixing the
  *last* bank at `$C000`), our RESET vector and initialization code must be placed in the
  very last bank of the ROM" — confirming `PRGFIXED`/`start=$FFFA` is the architecturally
  correct placement ld65 already performs, and that copying from the switchable region is
  wrong on its face.
- **Suggested Fix**: Delete `MMC1Mapper.generate_post_process_commands()` (or make it return
  `""`, the `BaseMapper` default) — the linker config's `start = $FFFA` on the `VECTORS`
  segment already places vectors correctly, as demonstrated above; no post-link fixup is
  needed. If a fixup was genuinely required against some historical linker config, restore
  that config instead of patching around it with a file-offset copy.

---

### MAP-3: `ROMCompiler.compile()` never calls `generate_post_process_commands()` — the two build paths (`build.sh` vs `compiler.compile_rom()`) can behave differently for the same mapper
- **Severity**: MEDIUM
- **Dimension**: 8 (compiler validation & CC65 error surfacing)
- **Location**: `compiler/compiler.py:67-146` (`ROMCompiler.compile()` — assembles, links,
  size-checks; no call to `generate_post_process_commands()` anywhere in the module)
- **Status**: NEW
- **Description**: `nes/project_builder.py`'s `_create_build_script()` (line 648) delegates
  to `self.mapper.generate_build_script(is_windows)`, which (via `BaseMapper.generate_build_script`,
  `mappers/base.py:97-127`) appends `generate_post_process_commands()` after linking — this
  is how `build.sh`/`build.bat` picks up a mapper's post-link fixup. `compiler/compiler.py`'s
  `ROMCompiler.compile()` is a separate, parallel implementation of "assemble, link, verify"
  used by `main.py compile` / `compiler.compile_rom()` — it never calls
  `generate_post_process_commands()` at all, and has no mapper reference to call it with. A
  project prepared with a mapper that needs a post-link step and then compiled via
  `compiler.compile_rom()` instead of running `build.sh` silently skips that step.
- **Evidence**:
  ```
  $ grep -rn "generate_post_process_commands" compiler/
  (no matches)
  ```
- **Impact**: Given MAP-2 above, this gap is currently **accidentally protective** for
  MMC1 — a ROM compiled via `compiler.compile_rom()` (skipping the fixup) has *correct*
  vectors, while one built via `build.sh` (running the fixup) has *corrupted* ones. That is
  itself evidence of the inconsistency this finding flags: the same prepared project
  produces a working ROM through one public entry point and a bricked one through another,
  which is a real API hazard independent of which specific mapper is buggy today. Fixing
  MAP-2 (removing/fixing the MMC1 fixup) would make the two paths agree by removing the
  need for this call entirely for MMC1; if a future mapper legitimately needs a post-link
  step, this gap would then cause the same build.sh-vs-compiler.compile() divergence MAP-2
  exposed. Rated MEDIUM (not HIGH) because it is unreachable from the CLI today (no
  `--mapper` flag; `prepare`/the full pipeline hardcode MMC3, which needs no post-process
  step) and because acting on it without first fixing MAP-2 would propagate MAP-2's
  corruption into the `compiler.compile()` path too.
- **Related**: MAP-2 (fix that one first), #18.
- **Hardware ref**: n/a (build orchestration, not a hardware register concern).
- **Suggested Fix**: Fix MAP-2 first. Then thread a mapper reference into `ROMCompiler`
  (constructor or `compile()` parameter) and call
  `self.mapper.generate_post_process_commands()` after a successful link, so `build.sh` and
  `compiler.compile_rom()` stay behaviorally identical for every mapper.

### MAP-4: MMC3's `nes.cfg` declares an `OAM` memory region and segment that nothing ever populates — harmless but real `ld65` warning on every default build
- **Severity**: LOW
- **Dimension**: 7 (project builder buildability)
- **Location**: `mappers/mmc3.py:54` (`OAM: start = $0200, size = $0100, type = rw, ...` in `MEMORY`); `mappers/mmc3.py:78` (`OAM: load = OAM, type = bss, align = $100;` in `SEGMENTS`)
- **Status**: NEW
- **Description**: The MMC3 linker config reserves a `$0200-$02FF` `OAM` (sprite Object
  Attribute Memory) region and declares a matching `.segment "OAM"`, but neither
  `nes/project_builder.py`'s generated `main.asm` nor `exporter/exporter_ca65.py`'s
  `music.asm` nor `nes/debug_overlay.py` ever emit anything into `.segment "OAM"` — this is
  a music-only ROM generator with no sprite/graphics engine. `ld65` warns on every default
  build.
- **Evidence**: Reproduced on the same real build as MAP-1:
  ```
  ld65: Warning: .../nes.cfg(203): Segment 'OAM' does not exist
  $ grep -rn '"OAM"' nes/project_builder.py exporter/exporter_ca65.py nes/debug_overlay.py
  (no matches)
  ```
- **Impact**: Cosmetic — an extra warning line in every MMC3 build's `ld65` output (which
  also now includes the real MAP-1 overflow warnings, making it harder to spot the
  actionable ones among noise). No effect on the produced ROM's correctness.
- **Related**: none.
- **Hardware ref**: n/a.
- **Suggested Fix**: Either remove the unused `OAM` `MEMORY`/`SEGMENTS` entries from
  `mmc3.py:54,78`, or wire up an actual OAM shadow-buffer segment usage if sprite support is
  planned (see `docs/ROADMAP.md`).

### MAP-5: Stale comment in `exporter_ca65.py`'s standalone-header guard still claims "MMC3 embeds its own `.segment \"HEADER\"`" — no longer true since #22
- **Severity**: LOW
- **Dimension**: 7 (project builder buildability) / 1
- **Location**: `exporter/exporter_ca65.py:109-111`
- **Status**: NEW (doc-rot left over from a fix already verified complete — #22, `MMC3Mapper.generate_header_asm()` returns bare `.byte` lines as of commit `007f5c4`)
- **Description**: `export_direct_frames(..., standalone=True)`'s header emission still
  guards with `if '.segment "HEADER"' not in header_asm: lines.append('.segment "HEADER"')`
  and a comment explaining "MMC3 embeds its own `.segment \"HEADER\"`; NROM/MMC1 don't."
  That was true before #22 (fixed in commit `007f5c4`); as verified in Dimension 1 of this
  audit, `MMC3Mapper.generate_header_asm()` (`mappers/mmc3.py:38-48`) now returns bare
  `.byte` lines identically to NROM/MMC1 (`mappers/nrom.py:39-44`, `mappers/mmc1.py:40-45`).
  The guard branch is harmless (it still emits `.segment "HEADER"` correctly for every
  mapper today, since none of them embed it anymore), but the comment misdescribes current
  mapper behavior.
- **Evidence**:
  ```
  exporter_ca65.py:109  # MMC3 embeds its own `.segment "HEADER"`; NROM/MMC1 don't.
  exporter_ca65.py:110  if '.segment "HEADER"' not in header_asm:
  mmc3.py:43             .byte "NES", $1A                          # no .segment here anymore
  ```
- **Impact**: None on behavior; misleads a future reader into thinking the branch is still
  load-bearing for MMC3 specifically.
- **Related**: #22.
- **Hardware ref**: n/a.
- **Suggested Fix**: Update the comment to state all three mappers return bare header bytes
  today, or simplify by removing the now-always-true guard and unconditionally appending
  `.segment "HEADER"`.

### MAP-6: `MapperFactory.auto_select()` / `can_fit_data()` are reachable only from `mappers/` unit tests, never from any real pipeline path
- **Severity**: LOW
- **Dimension**: 6 (MapperFactory auto-selection)
- **Location**: `mappers/factory.py:83-114` (`auto_select`); `main.py:243-244` (`run_prepare` hardcodes `MMC3Mapper()`), `main.py:684-685` (`run_full_pipeline` hardcodes `MMC3Mapper()`)
- **Status**: NEW (descriptive tech-debt item the SKILL.md dimension explicitly asks to
  re-verify each pass; not previously filed as its own issue — the related conflicting-default
  bug this used to compound with, #25/M-7, is closed)
- **Description**: `main.py` has no `--mapper` CLI flag; both places that build a real
  project (`run_prepare`, `run_full_pipeline`) explicitly instantiate `MMC3Mapper()` and pass
  it in, bypassing `NESProjectBuilder`'s own `mapper_name="auto"` default and never calling
  `auto_select_mapper(data_size)`. `MapperFactory.auto_select()`'s smallest-fits-first logic
  (verified correct: `nrom`→`mmc1`→`mmc3` order, `can_fit_data()` checked, "nothing fits"
  raises against the largest mapper's capacity) is therefore exercised only by
  `tests/test_mappers.py`, never by a live CLI invocation.
- **Evidence**:
  ```
  $ grep -n -- '--mapper' main.py
  (no matches)
  main.py:243-244   from mappers.mmc3 import MMC3Mapper; mapper = MMC3Mapper()   # run_prepare
  main.py:684-685   from mappers.mmc3 import MMC3Mapper; mapper = MMC3Mapper()   # run_full_pipeline
  ```
- **Impact**: Not a correctness bug — the size-based auto-selection machinery is simply
  unreachable dead-from-the-CLI code today, and its test coverage (closed via #47/REG-07)
  only proves the algorithm works in isolation, not that it is wired to anything. If a song
  is small enough to fit NROM/MMC1, the pipeline still always builds the full 512 KB MMC3
  ROM.
- **Related**: #25 (closed — resolved a conflict in this same area), #47/REG-07 (closed — added the unit tests that are this code's only caller).
- **Hardware ref**: n/a.
- **Suggested Fix**: Either add a `--mapper auto|nrom|mmc1|mmc3` CLI flag that threads through
  to `run_prepare`/`run_full_pipeline` and calls `auto_select_mapper(data_size)` when
  `auto` is chosen, or remove the auto-selection machinery if smallest-mapper selection is
  not a near-term goal (see `docs/ROADMAP.md`: "Mapper coverage and auto-selection tuning").

---

## Previously identified, still open (not re-described in full; dedup per `_audit-common.md`)

- **#28** (M-8): `ROMCompiler.MIN_ROM_SIZE = 32768` (`compiler/compiler.py:27`) remains a flat
  constant not compared against the active mapper's `prg_rom_size` — confirmed unchanged.
  Still LOW/MEDIUM defense-gap per the original finding (NROM's own true minimum is above
  the constant so no false-positive there; a truncated large MMC1/MMC3 image ≥32 KB would
  still false-pass).
- **#32** (M-9): `compile_rom()`'s broad `except Exception` (`compiler/compiler.py:173-175`)
  still just prints `[ERROR] Compilation failed: {e}` and returns `False` with no traceback,
  independent of `verbose` — confirmed unchanged.

---

## Dimension coverage map

| Dim | Area | Result |
|-----|------|--------|
| 1 | iNES header ↔ nes.cfg | Re-verified with arithmetic: NROM header `$02`→32 KB matches `PRG` `$8000`; MMC1 header `$08`→128 KB matches `PRGSWAP $1C000`(112 KB)+`PRGFIXED $4000`(16 KB); MMC3 header `32`→512 KB matches 60×`$2000`+`PRG_80/A0/C0`(3×8 KB)+`PRG_FIX`($1FFA)+`VECTORS`(6) = exactly 524288. Mapper nibbles `$00/$10/$40` match `mapper_number` 0/1/4. No mismatch. |
| 2 | Vectors + 60Hz NMI | `nmi`/`reset`/`irq` defined in `main.asm`; `nmi` calls `update_music`; `reset` enables NMI (`$2000=#$80`). **MAP-2 (CRITICAL, NEW)**: MMC1's post-link fixup, empirically shown to corrupt correctly-linked vectors via a real `ca65`/`ld65` build. NROM (no fixup) and MMC3 (`generate_build_script` explicitly documents "no vector fixup needed") unaffected. |
| 3 | APU init | Confirmed via real build artifacts: `audio_engine.asm:131-145` writes `$4017=$40` then `$4015=$0F`, disables `$4001`/`$4005` sweep. No finding. |
| 4 | PRG capacity/overrun | **MAP-1 (CRITICAL, NEW)** — capacity gate doesn't sum `BANK_NN`+`DPCM_NN` sharing a physical bank; reproduced failing the default pipeline on ordinary input. |
| 5 | Bank switching | MMC3 `$46`/`$47` R6/R7 selects, `$E000` IRQ-disable, R7→`$A000` sequence window match `docs/MAPPER_MMC3_REFERENCE.md`. MMC1 5-write serial load + `$0C` control (mode 3, fixed last bank) match `docs/MAPPER_MMC1_REFERENCE.md`. No finding beyond MAP-2 (a post-link step, not the bank-switch code itself). |
| 6 | MapperFactory auto-select | Order/logic correct. **MAP-6 (LOW, NEW)** — unreachable from any CLI path, only from unit tests. |
| 7 | Project builder buildability | **MAP-4 (LOW, NEW)** unused OAM segment; **MAP-5 (LOW, NEW)** stale comment. Segment set otherwise consistent between `main.asm`/`music.asm`/`nes.cfg` for the (still-broken-on-MAP-1) default build. |
| 8 | Compiler / CC65 surfacing | `assemble`/`link` raise with stderr attached (verified, unchanged). `check_toolchain`/`get_version` probe resolved paths with guarded subprocess calls (verified, unchanged, #14). **MAP-3 (MEDIUM, NEW)** — `compiler.compile()` vs `build.sh` post-process divergence. `#32` still open (broad except). |
| 9 | MIN_ROM_SIZE | `#28` still open, unchanged. |
| 10 | Default-mapper doc drift | Clean: `grep -niE 'always use mmc1\|default.*mapper\|mmc1'` across `README.md`/`CLAUDE.md`/`docs/*.md` shows only legitimate MMC1-reference-doc/roadmap hits; no doc reasserts MMC1 as *the* default. No finding. |

---

Next step:
```
/audit-publish docs/audits/AUDIT_MAPPERS_2026-07-03.md
```
