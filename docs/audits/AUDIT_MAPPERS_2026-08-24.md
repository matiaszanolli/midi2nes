# Audit: Mappers / Project Builder / Compiler — 2026-08-24

Subsystem audited: `mappers/` (base, factory, nrom, mmc1, mmc3, capacity),
`nes/project_builder.py`, `nes/audio_engine.asm` (boot/NMI/jukebox paths),
`compiler/compiler.py`, `compiler/cc65_wrapper.py`, and the `main.py`
`--mapper` resolution / capacity pre-flight / `run_prepare` / `run_compile` /
`run_full_pipeline` / `run_song_build` call sites. All 10 SKILL.md dimensions
covered; no `--focus` restriction. Audited tree: `master` at HEAD `1803fa7`.

**Delta since the last mapper audit (2026-08-21, HEAD `949f0c6`):**
`mappers/{nrom,mmc1,mmc3,factory,base}.py` are byte-for-byte unchanged
(`git diff --stat` empty). Changed audit-relevant files: `compiler/cc65_wrapper.py`
(+16), `compiler/compiler.py` (+10), `mappers/capacity.py` (+4/-3), `main.py`
(+250/-151 net, mostly typed-exception threading), `nes/project_builder.py`
(+94/-9, jukebox auto-detect + `--visualizer` mode), `nes/audio_engine.asm`
(+70/-6, all `.ifdef VISUALIZER_BUILD`-gated or the already-audited #433
jukebox-transition fix). Both 2026-08-21 findings are confirmed **FIXED**
(see below). One new, unaudited feature landed yesterday (`1803fa7`, DPCM
dynamic start-bank packing, #519) — reviewed fresh, no defect found.

**Special focus this pass:** the session's live investigation into a
freshly-built MMC3 ROM (and an independent hand-written NROM test ROM,
bypassing all midi2nes code) producing **no audio and no visual effect** in
Nestopia. Re-reading `_generate_main_asm()`'s `reset` routine byte-for-byte
against documented NES power-on/reset PPU timing surfaced a genuine, previously
unreported defect in the generated boot code (finding MAP-2026-08-24-1,
below) that independently explains total audio+visual silence on real
hardware and PPU-accurate emulators, and closely matches the still-open
`Output seems silent` report (**#3**).

**Method:** every claim re-derived from live source; register/bank claims
cite `docs/MAPPER_MMC1_REFERENCE.md` / `docs/MAPPER_MMC3_REFERENCE.md`.
Empirically instantiated `NESProjectBuilder(mapper=MMC3Mapper())._generate_main_asm()`
and inspected the literal generated `reset`/`nmi` assembly (reproduced in the
finding below) rather than reasoning from the template source alone.
`ca65`/`ld65` confirmed present at `/usr/bin`.

**Dedup basis:** `/tmp/audit/issues.json` (`gh issue list`, 5 open issues:
#2, #3, #468, #469, #470 — only #3 is mapper/boot-relevant), all prior
`docs/audits/AUDIT_MAPPERS_*.md` (most recently 2026-08-21), and a full-text
search of `docs/audits/*.md` for vblank/warm-up/power-up terminology (no
prior audit — of any subsystem — raised this).

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 0 |
| MEDIUM   | 0 |
| LOW      | 0 |
| **Total** | **1** |

**Highest-leverage fix:** MAP-2026-08-24-1 — insert a standard two-vblank PPU
warm-up wait (`bit $2002 / bpl` ×2) at the top of the generated `reset`
routine in `nes/project_builder.py`, *before* `lda #$80 / sta $2000` enables
NMI. This is a ~10-instruction, zero-risk change that plausibly fixes every
"ROM compiles and links but plays no sound" report this project has ever
received, including the open #3.

**One-line verdict:** the default single-song pipeline (MMC3, patterns-on)
still assembles and links to an exact-size, structurally correct ROM with
correct vectors and correct APU register content — but the generated `reset`
code enables NMI by writing `$2000` only ~100-150 CPU cycles after reset,
long before the PPU's mandatory ~29,658-cycle (2-vblank) post-reset warm-up
window closes, so on real hardware and PPU-accurate emulators that write is
silently ignored, NMI never actually turns on, and the ROM is functionally
dead (no audio past the first frame, no visual effects) despite every static
byte in the ROM being correct — the boot path is **not** currently bootable
in the sense that matters (music actually playing), even though it links and
"validates".

---

## Findings

### MAP-2026-08-24-1: Generated `reset` enables NMI (`sta $2000`) immediately after reset, before the PPU's mandatory ~2-vblank warm-up window closes — the write is silently ignored on real hardware/accurate emulators, permanently disabling NMI (and therefore all audio after the first frame)

- **Severity**: CRITICAL
- **Dimension**: 2 (reset/NMI/IRQ vectors and the 60Hz NMI music call) — extends
  it to the PPU power-on/reset timing contract the dimension's own checklist
  doesn't ask about ("does `reset` enable NMI" — yes; but *when*, relative to
  PPU readiness, is what actually determines whether that enable takes effect)
- **Location**: `nes/project_builder.py:538-561` (`_generate_main_asm`'s
  `reset:` label through the `mainloop:` label) — applies to **every** mapper
  (NROM/MMC1/MMC3), since `{self.mapper.generate_init_code()}` (line 544) is
  interpolated into the same template and none of `mappers/nrom.py:63-65`,
  `mappers/mmc1.py:108-131`, `mappers/mmc3.py:111-131` `generate_init_code()`
  contain a PPU wait either — this is a single, unconditional gap in the
  shared reset template, not a per-mapper issue.
- **Status**: NEW. No `docs/audits/*.md` (of any subsystem, any date) mentions
  vblank/PPU-warm-up/power-up-state. `#7`/M-2 (closed) fixed APU init content
  ($4015/$4017); `#291` (closed) fixed `CODE_8000` bank placement; `#213`
  (closed) fixed MMC1's vector-clobbering post-process step; `#6`/F-02
  (closed) fixed the ROM-validation gate's ERROR-only blocking. None of those
  touch PPU reset timing — this is a distinct defect that survives all of
  them. **Directly relevant to and likely explains open issue #3** ("Output
  seems silent" — reporter's own words, from the maintainer's comment on that
  issue: "the code compiles properly, everything gets linked into a valid
  ROM, but I'm not getting audio... I assume the issue lies in the current
  assembly logic (the player may not be trigger[ed] for some obscure
  reason)"). `docs/DEBUG_ROM.md:174-181` already lists "VBLANK not enabled"
  as a known troubleshooting cause of a silent/blank ROM, but only as
  end-user guidance ("Check: Make sure main.asm enables NMI and sets $2000
  correctly") — nothing in the generator itself implements the wait this
  advice presupposes.
- **Description**: NES hardware (documented on the NESdev wiki as "PPU
  power-up state", no equivalent doc currently exists in this repo's
  `docs/`) ignores writes to `$2000` (PPUCTRL), `$2001` (PPUMASK), `$2005`
  (PPUSCROLL), and `$2006` (PPUADDR) for approximately 29,658 CPU cycles
  (roughly two full video frames / two vblanks) after reset, while the PPU's
  internal analog circuitry stabilizes. The universally-used NES boot
  idiom is therefore: disable interrupts, set up the stack, then spin on
  `bit $2002 / bpl` twice (once per vblank) *before* touching any of those
  four registers. The generated `reset` routine does the opposite: it runs
  mapper init, zeroes `frame_counter`, calls `init_music` (APU-only writes —
  fine), and then immediately writes `$80` to `$2000` to turn NMI on — all of
  this totaling on the order of 100-150 CPU cycles, roughly 0.3% of the
  required warm-up window. On real hardware and any PPU-accurate emulator
  (Nestopia is specifically known for strict, cycle-accurate PPU power-up
  emulation — consistent with the session's independent hand-rolled NROM
  blink test also showing no NMI-driven behavior there), this `$2000` write
  is discarded: NMI is never actually enabled. The CPU falls into
  `mainloop: jmp mainloop` and spins forever. Since **all** per-frame note/
  volume/pitch APU writes happen inside `update_music`, which is only ever
  called from the `nmi:` handler (never from `reset`), the practical result
  is: `init_music`'s one-time setup writes ($4015/$4017/etc.) land correctly,
  but no note is ever actually triggered or changed after that — total,
  silent, no-workaround failure. This matches "compiles, links, plays
  nothing" precisely, and is orthogonal to (and survives) every previously
  fixed bug in this subsystem, none of which touch reset-time PPU sequencing.
- **Evidence**: Live-generated `main.asm` reset routine (via
  `NESProjectBuilder(mapper=MMC3Mapper())._generate_main_asm()` at HEAD),
  reproduced verbatim:
  ```
  reset:
      sei                   ; Disable interrupts
      cld                   ; Clear decimal mode
      ldx #$FF
      txs                   ; Set up stack

      ; MMC3 Init for Audio Engine (PRG Mode 1)
      sta $E000       ; Disable MMC3 IRQs
      lda #$46
      sta $8000
      lda #$00
      sta $8001
      lda #$47
      sta $8000
      lda #$01
      sta $8001

      ; Initialize frame counter
      lda #$00
      sta frame_counter
      sta frame_counter+1

      ; Initialize APU and music
      jsr init_music

      ; CRITICAL: Enable NMI for 60Hz timing
      lda #$80
      sta $2000          ; Enable NMI, this makes music timing work!

  mainloop:
      jmp mainloop
  ```
  No `bit $2002` / `bpl` pair appears anywhere before the `sta $2000`, for
  any mapper — confirmed by grepping `mappers/{nrom,mmc1,mmc3}.py`'s
  `generate_init_code()` bodies for `$2002` (no hits). By contrast, the
  repo's own `--visualizer` mode (`nes/visualizer.py:114-121`,
  `generate_visualizer_init`) *does* implement exactly this wait —
  `"Wait for two VBlanks so the PPU is warmed up before we touch it."`
  followed by two `bit $2002 / bpl` loops — and, because
  `visualizer_init_call` is spliced in before `jsr init_music` /
  `sta $2000` (`nes/project_builder.py:550-551`), a `--visualizer` build
  incidentally gets the correct warm-up for free. The default build
  (no `--debug`, no `--visualizer` — the path every "freshly built ROM"
  report, including #3 and the session's own canyon.mid ROM, actually
  takes) gets none of it.
- **Impact**: Every ROM built by the default pipeline (`main.py input.mid
  out.nes`), `prepare`+`compile`, and `song build` — i.e. the entire product
  — is at risk of total audio and visual silence on real hardware and
  PPU-accurate emulators, with no CLI flag or user-facing workaround (only
  `--visualizer` accidentally sidesteps it, as a side effect of unrelated
  PPU setup code, not because anyone intended it to fix boot timing). Blast
  radius: every mapper (NROM/MMC1/MMC3), every export mode (direct/bytecode/
  jukebox), every existing ROM built by this tool to date. This is very
  plausibly the root cause of open issue #3 (reported against three
  different emulators/players including Nestopia and FCEUX) and is fully
  consistent with the session's own live repro (a from-scratch, non-midi2nes
  NROM NMI-blink test also showing no NMI-driven visual behavior in the same
  Nestopia environment) — though that hand-rolled test is not midi2nes code
  and could have its own, independent cause; this finding stands on its own
  merits from the generated-code inspection alone, regardless of the
  hand-rolled test's outcome.
- **Related**: Extends Dimension 2's "reset enables NMI" checklist item, which
  every prior mapper audit (including 2026-08-21, `AUDIT_MAPPERS_2026-08-21.md`
  dimension 2) verified only as "does `sta $2000` execute", not "is `sta
  $2000` executed after the PPU is actually ready to accept it" — a gap in
  the audit's own checklist as much as in the code, worth folding into
  `.claude/commands/audit-mappers/SKILL.md` Dimension 2 for future passes.
  Likely explains/duplicates the open **#3** "Output seems silent" report at
  the root-cause level (that issue itself does not diagnose this mechanism,
  so this is filed as a new, more specific technical finding rather than a
  literal duplicate — recommend cross-linking and closing #3 once this is
  fixed and verified against real hardware/Nestopia).
- **Hardware ref**: No `docs/PPU_*.md` currently exists in this repository to
  cite. This is standard, extensively documented NES/2A03+2C02 hardware
  behavior (NESdev wiki, "PPU power-up state": writes to $2000/$2001/$2005/
  $2006 are ignored for ~29,658 CPU cycles / ~2 vblanks following reset).
  Recommend adding a `docs/PPU_REFERENCE.md` (or extending
  `docs/2A03_CPU_REFERENCE.md`, which currently has no reset/power-on
  section at all) to give future audits and fixes something authoritative
  to cite in this repo, matching the pattern of every other `docs/APU_*.md`/
  `docs/MAPPER_*.md`.
- **Suggested Fix**: In `nes/project_builder.py`'s `_generate_main_asm()`,
  insert the standard two-vblank wait immediately after `txs` (stack setup)
  and before `{self.mapper.generate_init_code()}` (mapper register writes are
  not PPU registers, so ordering relative to them doesn't matter, but doing
  it first is the conventional idiom and costs nothing):
  ```asm
      ldx #$FF
      txs                   ; Set up stack

  @vblankwait1:
      bit $2002
      bpl @vblankwait1
  @vblankwait2:
      bit $2002
      bpl @vblankwait2
  ```
  This is exactly the pattern `nes/visualizer.py:116-121` already implements
  correctly — consider factoring it into one shared helper both call, so the
  two copies can't drift. Add a regression test asserting `"bit $2002"`
  appears in the generated `main.asm` *before* the `"sta $2000"` that enables
  NMI, for a plain (no `--debug`, no `--visualizer`) build of every mapper.
  This should be treated as release-blocking: it is the single highest-value
  fix available in this codebase right now.

---

## Fix verification (2026-08-21 findings — both CLOSED, verified live)

- **MAP-2026-08-21-1 (MEDIUM, split prepare/compile on jukebox music.asm):
  FIXED**, tracked as **#453**. `nes/project_builder.py:141-155` now
  auto-detects the jukebox marker (`"multi-song jukebox build" in
  music_content`) and sets `song_count = 1` when the caller passed `None`,
  so `python main.py prepare <jukebox-music.asm> <dir>` followed by `compile`
  now defines `JUKEBOX_BUILD` and links, matching the behavior the original
  finding asked for (option (a), auto-detect rather than a hard error).
- **MAP-2026-08-21-2 (LOW, `cc65_wrapper.py` bare `ca65`/`ld65` + missing
  `FileNotFoundError` guard): FIXED**, tracked as **#454**.
  `compiler/cc65_wrapper.py:141` and `:210` now build `cmd` from
  `self._ca65_path or "ca65"` / `self._ld65_path or "ld65"` (the paths
  `check_toolchain()` resolved), and both `assemble()`/`link()` now catch
  `FileNotFoundError` alongside `subprocess.TimeoutExpired`, raising
  `ToolchainError` — verified by reading the live diff against `949f0c6`.
  `compiler/compiler.py`'s `compile_rom()` also grew a third
  `except ToolchainError` clause (tracked separately as **#457**,
  `SAFE-2026-08-21-3`) so a toolchain that vanishes between `check_toolchain()`
  and the real assemble/link now surfaces a clean one-line `[ERROR]` message
  instead of falling through to the generic `except Exception` branch.

## New feature reviewed fresh (not in any prior audit): DPCM dynamic start-bank packing (#519, commit `1803fa7`)

`DpcmPacker.__init__` now accepts `start_bank` (default 0); `main.py`'s
`pack_dpcm_into_asm()` forwards `start_bank=getattr(exporter, 'next_bank', 0)`
from both `run_export` and `export_frames_and_resolve_mapper`, so DPCM
sample banks (`DPCM_NN`) are now packed starting immediately after the
bytecode exporter's own `BANK_NN` sequence banks instead of always starting
at bank 0 (previously risking squeezing both into a nearly-full `BANK_00`
even when dozens of the 60 swap banks sat empty). Verified:
- `CA65Exporter.next_bank` is initialized to `0` in `__init__` (line 83) and
  only reassigned by the bytecode path (`export_tables_with_patterns` ->
  `_build_song_bytecode`, line 1709) — so `getattr(exporter, 'next_bank', 0)`
  correctly stays `0` for a direct (`--no-patterns`) export, which never
  creates `BANK_NN` segments in the first place.
- Call ordering is correct in both call sites: `export_tables_with_patterns`
  (which sets `next_bank`) runs before `pack_dpcm_into_asm` reads it, in both
  `run_export` and `export_frames_and_resolve_mapper`.
- `DpcmPacker._pack_all_samples`'s overflow guard changed from
  `len(self.banks) >= 60` to `self.start_bank + len(self.banks) >= 60` —
  correctly rejects the moment the *physical* bank index (not the local
  packer-relative index) would reach 60, and correctly raises immediately
  (0 samples placed) if `start_bank` itself is already `>= 60`.
  `DPCM_{self.start_bank + local_bank_id:02d}` never exceeds two digits
  since the cap keeps the physical index `<= 59`.
- `MMC3Mapper.validate_segment_sizes()`'s shared-bank summing (`#212`,
  groups `BANK_NN`/`DPCM_NN` by the numeric suffix parsed out of the segment
  name and sums them against the 8KB window) is index-generic — it doesn't
  assume DPCM starts at bank 0, so it continues to correctly catch an
  overflow whether or not `BANK_NN` and `DPCM_NN` for a given index actually
  collide (now rarer, since they mostly land in disjoint index ranges, but
  still handled correctly if a future caller passes `start_bank=0` with a
  non-empty existing bank 0).
- `run_song_build`'s v1 jukebox path (documented DPCM-free scope,
  `docs/ROADMAP.md`) never calls `pack_dpcm_into_asm` — confirmed by grep —
  so this change has no jukebox-path interaction to verify.

No defect found in this feature.

## Dimensions re-verified, no new findings (mapper source files unchanged since 2026-08-21)

| # | Dimension | Result |
|---|-----------|--------|
| 1 | iNES header ↔ nes.cfg | `mappers/{nrom,mmc1,mmc3}.py` byte-identical to the 2026-08-21 pass (`git diff` empty) — prior pass's live-verified region sums (NROM 32KB, MMC1 128KB, MMC3 512KB exact) and mapper-number nibbles stand. |
| 3 | APU init | Unchanged; re-confirmed via the live-generated `main.asm` above that `jsr init_music` (writing $4015/$4017 etc.) still executes unconditionally in `reset`, before the NMI-enable write covered by MAP-2026-08-24-1 — the APU-init *content* is correct, it is only the *NMI-enable* write immediately after it whose timing is broken. |
| 4 | PRG capacity pre-flight | `mappers/capacity.py`'s only change is `raise MapperError(...)` instead of `raise ValueError(...)` (`MapperError(MIDI2NESError, ValueError)` per `core/exceptions.py:119`, still a `ValueError` for every existing `except ValueError` call site) — confirmed no call site broke: `main.py:643,678,758,1105` (`except ValueError`) and `main.py:912,1121,1565` (`except (MIDI2NESError, ...)` / `except MIDI2NESError`) all still catch it. All four prior verify-the-fix items (#390, #363, #389, bank-count cap) untouched and still hold. |
| 5 | Bank switching | `generate_init_code()`/`generate_bank_switch_code()` byte-identical for all three mappers; re-confirmed no PPU register appears in any of them (relevant to MAP-2026-08-24-1: the mapper-init code itself is not the problem, it's what runs after it). |
| 6 | MapperFactory auto-selection | `mappers/factory.py` unchanged; #361/#362 fixes untouched. |
| 7 | Buildable project | Beyond the confirmed #453 fix above: segment set (`HEADER`/`ZEROPAGE`/`BSS`/`CODE`/`RODATA`/`VECTORS`/`CODE_8000`/`DPCM_*`/`BANK_*`) unchanged; new `--visualizer` mode's `visualizer_bss`/`visualizer_imports` are additive and consistently gated (`self.visualizer_mode`) on both the music.asm and main.asm sides — no orphaned segment or unresolved symbol introduced. |
| 8 | Compiler validation / CC65 error surfacing | Beyond the confirmed #454/#457 fixes above: `validate_project`, `assemble`/`link` nonzero-rc handling, build-script routing (#18), and post-process invocation (#214) all unchanged and still correct. |
| 9 | ROM size check | `compiler/compiler.py`'s exact-size check (`mapper.prg_rom_size + 16`) unchanged. |
| 10 | Default-mapper doc drift | `grep -niE 'always use mmc1|default.*mapper' README.md CLAUDE.md docs/*.md` — still consistently MMC3-as-default; no drift. |

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_MAPPERS_2026-08-24.md
```
