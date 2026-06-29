# Audit: Mappers / Project Builder / Compiler — 2026-06-29

Subsystem audited: `mappers/` (base, factory, nrom, mmc1, mmc3), `nes/project_builder.py`,
`compiler/compiler.py`, `compiler/cc65_wrapper.py`, plus the exporter/engine seams they
depend on (`exporter/exporter_ca65.py`, `nes/audio_engine.asm`) and the pipeline call
sites in `main.py`. All 10 SKILL.md dimensions covered. This is an incremental re-audit
on top of `docs/audits/AUDIT_MAPPERS_2026-06-28.md`, which found 11 issues (3 CRITICAL).

**Dedup basis:** `/tmp/audit/issues.json` (22 open issues — not re-fetched). Prior report
`AUDIT_MAPPERS_2026-06-28.md` reviewed line-by-line; each of its M-1…M-11 re-verified
against the current tree to classify as Fixed / Still-open / Regression.

## State of the three prior CRITICALs (now resolved — verified, no regression)

| Prior | Subject | Current state | Evidence |
|-------|---------|---------------|----------|
| M-1 | Default (patterns-on) `music.asm` references `CODE_8000`/`BANK_NN` segments MMC3 `nes.cfg` never defined → link fails | **FIXED** | `mappers/mmc3.py:68` defines `CODE_8000`, `:77` defines `BANK_00..59`; exporter segments (`exporter_ca65.py:863,1063,1107`) now all resolve. |
| M-2 | APU `$4017` never set; `$4015` not enabled at init on patterns path | **FIXED** | `nes/audio_engine.asm:128-133` now writes `$4017=$40` then `$4015=$0F`; direct path `exporter_ca65.py:724-727` writes both. |
| M-3 | Music data never size-checked against mapper PRG capacity on any pipeline path | **FIXED (with a new gap, see MAP-1)** | `main.py:94 check_mapper_capacity` is now called at `:189` (`run_prepare`) and `:587` (`run_full_pipeline`). |

Also resolved since 2026-06-28: M-4 (`cc65_wrapper.py` now probes via `self._ca65_path`,
`:58`), M-10 (CLAUDE.md:197 now states MMC3/512KB default). M-5 is **no longer valid** —
`_create_build_script()` (`project_builder.py:638`) delegates to
`self.mapper.generate_build_script(is_windows)`, so the MMC3-hardcoded `_create_build_script_mmc3`
the SKILL/prior report referenced does not exist in the current tree; the MMC1 vector
fixup is reachable via `build.sh`.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 3 |
| LOW      | 3 |
| **Total**| **6** |

**One-line verdict:** The default (MMC3, patterns-on) pipeline now produces a **bootable**
ROM — segments link, vectors land at `$FFFA`, and the APU (`$4015`/`$4017`) is initialized
in the boot path. The remaining findings are a capacity-gate that measures the wrong
budget (MAP-1, NEW) and previously-filed open issues.

**Highest-leverage fix:** Make `check_mapper_capacity` (`main.py:94`) measure against the
*binding per-segment region* — the 8 KB fixed window the direct export's tables land in
(`PRG_FIX`), and the 8 KB per `BANK_NN` / `CODE_8000` for the bytecode export — instead of
the mapper's full 510 KB PRG. As written the gate passes data `ld65` will reject with a
raw region-overflow, defeating the purpose it was added for (#11).

---

## Findings (CRITICAL first)

### MAP-1: Capacity pre-flight measures total bytes against full 510 KB PRG, but the binding limit is the 8 KB fixed segment the tables land in
- **Severity**: MEDIUM
- **Dimension**: 4 (PRG capacity / overrun detection) / 9
- **Location**: `main.py:62-104` (`estimate_music_data_size` / `check_mapper_capacity`); `mappers/mmc3.py:56` (`PRG_FIX size = $1FFA`), `:80-81` (`CODE`/`RODATA` load into `PRG_FIX`); `mappers/base.py:140-159` (`get_data_capacity = prg_rom_size - 2048`)
- **Status**: NEW
- **Description**: The `#11` capacity gate sums every `.byte`/`.word`/`.incbin` byte in
  `music.asm` and compares the total to `mapper.can_fit_data()` →
  `get_data_capacity()` = `512*1024 - 2048` = **522 240 bytes** for MMC3. But the MMC3
  linker config loads the **direct-export** frame tables into `RODATA`, and `RODATA`
  loads into `PRG_FIX`, whose `MEMORY` region is only **`$1FFA` = 8 186 bytes**
  (`mappers/mmc3.py:56,81`) — shared with `CODE`. The direct export
  (`exporter/exporter_ca65.py:122-249`) emits dense, frame-indexed tables of `max_frame+1`
  bytes each: 4 tables × 3 tone channels + 3 noise + 1 DPCM ≈ 13–16 × `(frames)` bytes.
  At 60 FPS even a ~12-second song (~720 frames × ~16 tables ≈ 11.5 KB) overflows the
  8 KB `PRG_FIX` region — yet `check_mapper_capacity` reports it "fits MMC3 (510 KB)" and
  lets it through, so `ld65` aborts with a raw `PRG_FIX` region-overflow instead of the
  friendly budget message the gate was added to provide.
- **Evidence**:
  ```
  main.py:97-98     data_size = estimate_music_data_size(...)   # sums ALL .byte/.word
                    if not mapper.can_fit_data(data_size): raise ValueError(...)
  base.py:147       return self.prg_rom_size - 2048             # 522240 for MMC3
  mmc3.py:56        'PRG_FIX: start = $E000, size = $1FFA, ...'  # only 8186 bytes
  mmc3.py:80-81     'CODE: load = PRG_FIX' / 'RODATA: load = PRG_FIX'
  exporter_ca65.py:122  lines.append('.segment "RODATA"')       # direct tables go here
  ```
  Worked example: 60 s song → ~3 600 frames → ~57 KB of RODATA tables; gate says
  "11 % of 510 KB, fits"; `ld65` errors `PRG_FIX overflow by ...`.
- **Impact**: The capacity gate gives false reassurance and does not prevent the raw
  `ld65` error it was meant to replace, for the `--no-patterns` (direct) path on the
  default MMC3 mapper. Blast radius: any direct export longer than a few seconds. Not
  CRITICAL because `ld65` *does* catch the overflow and the compiler surfaces it
  (`cc65_wrapper.py:205-211`) and the pre-build backup is restored — so the ROM is never
  silently corrupted; the defect is a wrong/misleading budget, not silent truncation.
- **Related**: prior M-3 (the gate that was just added), MAP-2, #28 (M-8 flat MIN_ROM_SIZE).
- **Hardware ref**: `docs/MAPPER_MMC3_REFERENCE.md` §6 (memory map: `$E000-$FFFF` fixed
  last 8 KB holds driver + note lookup tables).
- **Suggested Fix**: Have `check_mapper_capacity` size against the *segment the data
  actually lands in*: for the direct export, compare RODATA+CODE bytes to the `PRG_FIX`
  region size (8 186 − engine size); for the bytecode export, validate each `BANK_NN`
  ≤ 8 KB and bank count ≤ 60 and `CODE_8000` ≤ 8 KB. A single 510 KB ceiling is only
  correct if the data is actually distributed across the 60 swap banks (which only the
  bytecode path does).

### MAP-2: Bytecode export has no cap on bank count — a song needing >60 banks emits `.segment "BANK_60"+` that MMC3 `nes.cfg` never defines
- **Severity**: MEDIUM
- **Dimension**: 4 / 7 (project builder buildability)
- **Location**: `exporter/exporter_ca65.py:1056-1108` (bank rollover loop); `mappers/mmc3.py:48-49,75-77` (`PRG_BANK_00..59` / `BANK_00..59` — only 60 banks defined)
- **Status**: NEW
- **Description**: The macro-bytecode serializer rolls to a new bank whenever
  `bytes_in_current_bank + event_bytes + 4 > BANK_SIZE_LIMIT` (8192−256), emitting
  `.segment "BANK_{current_bank:02d}"` for the incremented `current_bank`
  (`exporter_ca65.py:1099-1107`). There is **no upper bound** on `current_bank`. The MMC3
  linker config defines `BANK_00`…`BANK_59` only (`mmc3.py:75-77`, `range(60)`). A song
  whose total sequence bytecode exceeds ~60×8 KB ≈ 480 KB produces `.segment "BANK_60"`
  (and beyond), which `ld65` rejects as an undefined segment. The MAP-1 capacity gate
  does not catch this either (it counts total bytes, not bank index). Likewise the
  per-instrument `CODE_8000` block (`:863`) and the `instrument_table`/macros can overflow
  the 8 KB `PRG_80` window independently of the 510 KB total.
- **Evidence**:
  ```
  exporter_ca65.py:1100-1107
      next_bank = current_bank + 1
      ... '.byte $FE, ${next_bank:02X}, ...'      # CMD_BANK_JUMP, unbounded
      lines.append(f'.segment "BANK_{current_bank:02d}"')
  mmc3.py:75   for i in range(60):                # only BANK_00..BANK_59 defined
  ```
- **Impact**: Very large songs (or large DPCM-heavy projects) fail to link with a raw
  `ld65` "undefined segment BANK_60" rather than a clear "song too large for MMC3" message.
  Edge case (requires ~480 KB of sequence bytecode), hence MEDIUM, not CRITICAL — and the
  error is surfaced, not silent.
- **Related**: MAP-1.
- **Hardware ref**: `docs/MAPPER_MMC3_REFERENCE.md` §1 (512 KB max PRG = 64×8 KB banks; the
  cfg reserves the top 4 for fixed windows, leaving 60 swappable).
- **Suggested Fix**: When `current_bank` would exceed 59, raise a clear exporter-level
  error ("sequence data exceeds MMC3 60-bank budget"); plumb the same bank/region check
  into `check_mapper_capacity` so it fails pre-link with a budget message.

### MAP-3: MMC3 `generate_header_asm()` emits its own `.segment "HEADER"`, double-declaring the segment the project builder already opened
- **Severity**: MEDIUM
- **Dimension**: 7 (project builder buildability) / 1
- **Location**: `mappers/mmc3.py:26-35` (`generate_header_asm` opens `.segment "HEADER"`); `nes/project_builder.py:567-568` (`_generate_main_asm` already wrote `.segment "HEADER"` before interpolating the header)
- **Status**: Existing: #22 (M-6 in `AUDIT_MAPPERS_2026-06-28.md`)
- **Description**: `_generate_main_asm` emits `.segment "HEADER"\n{mapper.generate_header_asm()}`.
  NROM/MMC1 return bare `.byte` lines (correct); MMC3 returns a block that *begins with its
  own* `.segment "HEADER"`, so `main.asm` contains two consecutive `.segment "HEADER"`
  directives for the default mapper. `ca65` tolerates re-opening an already-open segment,
  so the header bytes still land correctly and this is not a hard error today — but it is an
  inconsistency in the mapper contract and a latent trap if the builder's framing changes.
  Still present, unchanged, and tracked.
- **Evidence**:
  ```
  mmc3.py:27-28          return """\n.segment "HEADER"\n    .byte "NES", $1A ...
  project_builder.py:567 return f""".segment "HEADER"\n{self.mapper.generate_header_asm()}
  ```
- **Impact**: Currently benign; maintenance trap. MEDIUM per the dimension's
  contract-consistency axis.
- **Related**: #22.
- **Hardware ref**: n/a (assembler framing).
- **Suggested Fix**: Make `MMC3Mapper.generate_header_asm()` return bare `.byte` lines like
  NROM/MMC1, letting the builder own the single `.segment "HEADER"`.

### MAP-4: `MIN_ROM_SIZE` is a flat 32768 that can false-pass a truncated MMC3/MMC1 image far smaller than its declared PRG
- **Severity**: LOW
- **Dimension**: 9 (MIN_ROM_SIZE check)
- **Location**: `compiler/compiler.py:27` (`MIN_ROM_SIZE = 32768`), `:133-138`
- **Status**: Existing: #28 (M-8 in `AUDIT_MAPPERS_2026-06-28.md`)
- **Description**: `compile()` rejects a linked ROM `< 32768` bytes. NROM links to 32 KB
  PRG + 16-byte header = 32 784, so a valid NROM is `> 32768` (no false-positive). But MMC3
  declares 512 KB and MMC1 128 KB; any image `≥ 32768` passes, including a truncated MMC3
  image far below 512 KB. The check has no reference to the active mapper, so it cannot
  compare against the expected `prg_rom_size`. In practice `ld65` with `fill = yes` pads
  every region to full size, so a successful link yields the full declared size — making a
  truncated-but-large image unlikely; hence LOW/defense-gap, unchanged and tracked.
- **Evidence**:
  ```
  compiler.py:27   MIN_ROM_SIZE = 32768
  compiler.py:134  if rom_size < self.MIN_ROM_SIZE: raise CompilationError(...)
  ```
- **Impact**: A truncated/under-filled ROM ≥ 32 KB passes validation. LOW.
- **Related**: #28, MAP-1.
- **Hardware ref**: n/a.
- **Suggested Fix**: Plumb the mapper (or expected PRG size) into `ROMCompiler` and validate
  `rom_size >= mapper.prg_rom_size + 16`.

### MAP-5: Conflicting default-mapper behaviors — `get_mapper("auto", 0)`→MMC1, builder default `"auto"`, pipeline hardcodes MMC3
- **Severity**: LOW
- **Dimension**: 10 (default-mapper drift) / 6 (factory)
- **Location**: `mappers/factory.py:172-176` (auto+0 → MMC1); `nes/project_builder.py:30,49-51` (`mapper_name="auto"` default → MMC1); `main.py:186-187,581-582` (explicit `MMC3Mapper()`)
- **Status**: Existing: #25 (M-7 in `AUDIT_MAPPERS_2026-06-28.md`)
- **Description**: `get_mapper("auto", data_size=0)` returns MMC1 "for backwards
  compatibility" (`factory.py:174-175`). `NESProjectBuilder.__init__` defaults
  `mapper_name="auto"`, so any caller that constructs the builder *without* passing a
  mapper and *without* calling `auto_select_mapper(size)` gets MMC1 — whereas the actual
  pipeline always passes `mapper=MMC3Mapper()` (`main.py:187,582`). A caller relying on the
  builder's documented `"auto"` default silently gets MMC1, a different mapper from the rest
  of the pipeline. Unchanged and tracked.
- **Evidence**:
  ```
  factory.py:174-175    if data_size <= 0: return MapperFactory.get_mapper("mmc1")
  project_builder.py:30 mapper_name: str = "auto"
  main.py:187           mapper = MMC3Mapper()
  ```
- **Impact**: Inconsistent default; a builder used outside `main.py` (tests, future callers)
  silently selects a mapper the rest of the pipeline does not build for. LOW (the live
  pipeline always passes MMC3 explicitly).
- **Related**: #25, MAP-3.
- **Hardware ref**: n/a.
- **Suggested Fix**: Make the builder's `"auto"` default resolve via `auto_select(data_size)`
  once data size is known, or change the builder default to MMC3 to match the pipeline.

### MAP-6: `compile_rom`'s broad `except Exception` prints then returns False — masks tracebacks without a verbose path
- **Severity**: LOW
- **Dimension**: 8 (compiler error surfacing)
- **Location**: `compiler/compiler.py:164-175`
- **Status**: Existing: #32 (M-9 in `AUDIT_MAPPERS_2026-06-28.md`)
- **Description**: `compile_rom` wraps the whole compile in `try/except`, catching
  `CompilationError`, `ValidationError`, and a catch-all `except Exception`, printing
  `[ERROR] …` and returning `False`. This surfaces the message (clears the HIGH "silent
  success" floor — `assemble`/`link` correctly raise with stderr at
  `cc65_wrapper.py:150-156,205-211`), but the catch-all swallows the stack trace with no
  `verbose`/`-v` traceback at this layer, so a genuinely unexpected exception loses its
  origin. Unchanged and tracked.
- **Evidence**:
  ```
  compiler.py:173-175  except Exception as e: print(f"[ERROR] Compilation failed: {e}"); return False
  ```
- **Impact**: Harder debugging of unexpected compiler failures; not a correctness bug. LOW.
- **Related**: #32.
- **Hardware ref**: n/a.
- **Suggested Fix**: In the catch-all, print `traceback.format_exc()` when `verbose=True`
  (the flag is already passed into `ROMCompiler`).

---

## Dimension coverage map

| Dim | Area | Result |
|-----|------|--------|
| 1 | iNES header ↔ nes.cfg | Re-verified: NROM `$02`/PRG `$8000`=32 KB; MMC1 `$08` / PRGSWAP `$1C000`+PRGFIXED `$4000`=128 KB; MMC3 `32` / 60×`$2000`+4 fixed+VECTORS = 512 KB exactly. Mapper nibbles (`$00`/`$10`/`$40`) match `mapper_number` 0/1/4. No mismatch. (MMC3 double-HEADER → MAP-3.) |
| 2 | Vectors + 60Hz NMI | `nmi`/`reset`/`irq` all defined (`project_builder.py:583,607,626`); `nmi jsr update_music` (`:616`); `reset` sets `$2000=#$80` (`:600-601`); VECTORS `.word nmi/reset/irq` at `$FFFA` (`:629-632`). MMC1 fixup offset `0x2000A` correct and reachable via `build.sh`. No finding. |
| 3 | APU init | **FIXED** (prior M-2): `audio_engine.asm:128-133` writes `$4017=$40`+`$4015=$0F`; direct `init_music` `exporter_ca65.py:724-727` writes both. No finding. |
| 4 | PRG capacity/overrun | **MAP-1 (MEDIUM, NEW)** wrong budget; **MAP-2 (MEDIUM, NEW)** unbounded bank count. Capacity helpers now wired (prior M-3 fixed) but measure the wrong region. |
| 5 | Bank switching | MMC3 `$46`/`$47` R6/R7, mode-1 P bit, `$E000` IRQ-disable, R7 `$A000` sequence window match `docs/MAPPER_MMC3_REFERENCE.md` §1-2,6. MMC1 5-write serial + `$0C` control match `docs/MAPPER_MMC1_REFERENCE.md`. No finding. |
| 6 | MapperFactory auto-select | Order smallest-first (nrom→mmc1→mmc3); "nothing fits" raises with largest capacity — correct. `auto`+0→MMC1 default → MAP-5. |
| 7 | Project builder buildability | Segments now consistent (prior M-1 fixed). MAP-3 (double HEADER). |
| 8 | Compiler / CC65 surfacing | `assemble`/`link` raise with stderr (verified); `check_toolchain`/`get_version` now probe via resolved paths (prior M-4 fixed). MAP-6 (catch-all traceback). |
| 9 | MIN_ROM_SIZE | MAP-4 (LOW) — flat constant, not mapper-relative. |
| 10 | Default-mapper drift | MAP-5 (LOW). CLAUDE.md MMC3/512 KB drift (prior M-10) now corrected (`CLAUDE.md:197`). |

---

Next step:
```
/audit-publish docs/audits/AUDIT_MAPPERS_2026-06-29.md
```
