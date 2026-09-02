# NES Hardware Correctness Audit — 2026-08-24

Scope: the boundary where Python/asm numbers become APU register writes —
`nes/emulator_core.py`, `nes/pitch_table.py`, `nes/envelope_processor.py`,
`nes/audio_engine.asm`, `exporter/exporter_ca65.py` (plus the `main.asm`
template in `nes/project_builder.py` where its reset/NMI sequencing gates
whether any of the above ever executes). Re-derived from the working tree at
`1803fa7`, two days after `AUDIT_NES_HARDWARE_2026-08-22.md` (audited at
`59b8a45`).

**Priority investigation for this pass**: a live, currently-unresolved bug
report — a freshly-built MMC3 `canyon.mid` ROM produces **no audio at all**
in Nestopia, even though a static byte-pattern scan of the ROM finds APU
register-write instructions ($4000/$4004/$4008/$400C/$4015) present. This
report traces that symptom to a specific, deterministic root cause (below)
and confirms it independently duplicates a same-day finding already filed
by `/audit-mappers` (`docs/audits/AUDIT_MAPPERS_2026-08-24.md`,
MAP-2026-08-24-1) — reported here as **Existing**, not re-filed, but
described in full because it is this pass's single highest-value finding
and sits squarely on this audit's territory (whether audio ever reaches the
APU at runtime, not just whether the write bytes are correct).

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 (Existing — cross-filed by `/audit-mappers` today) |
| HIGH     | 0 |
| MEDIUM   | 0 |
| LOW      | 1 |
| **Total**| **2** |

**Highest-risk finding — total, permanent audio silence on every default-flag
ROM (NH-HW-2026-08-24-1 / MAP-2026-08-24-1, CRITICAL, Existing):**
`nes/project_builder.py`'s generated `reset:` routine enables NMI
(`lda #$80 / sta $2000`) roughly 100-150 CPU cycles after reset — deep
inside the PPU's mandatory ~2-vblank (~29,658-cycle) power-on warm-up
window, with **no** `bit $2002 / bpl` wait loop beforehand, for **any**
mapper (NROM/MMC1/MMC3) and on every build that doesn't pass `--visualizer`
(the one code path that happens to include a correct wait, for an unrelated
reason). On real hardware and on PPU-accurate emulators — Nestopia among
them — a $2000 write issued during this window does not reliably take
effect, so the NMI-enable bit never actually latches. Since **every**
per-frame note/pitch/volume register write in this engine lives inside
`update_music`/`audio_update`, and that code is *only* ever reached from the
`nmi:` handler — never from `reset` — the practical effect is: `init_music`'s
one-time setup writes (`$4015`, `$4017`, sweep-disable, DMC-DAC-zero) land
correctly, the CPU falls into `mainloop: jmp mainloop` forever, and no note
is ever triggered. This is fully consistent with the reported symptom (write
*instructions* present in the compiled bytes, but nothing audible at
runtime), and is very likely the root cause of the long-standing **open**
issue **#3** ("Output seems silent") — whose only comment, from the
maintainer, describes exactly this shape of bug ("compiles properly...
linked into a valid ROM, but I'm not getting audio... the player may not be
trigger[ed] for some obscure reason").

**Verified still clean (light-touch verify-the-fix pass — no relevant code
changed in `nes/pitch_table.py`, `nes/envelope_processor.py`'s core curve,
or the tone-channel/noise/DPCM register-write call sites since
`AUDIT_NES_HARDWARE_2026-08-22.md`; see that report for the full per-
dimension derivation, re-confirmed here by diffing `59b8a45..1803fa7`):**
- **D1**: #481/NH-HW-2026-08-22-1 (same-pitch retrigger silently absorbed)
  is fixed — `nes/emulator_core.py:71-128` now borrows one frame from the
  front of a genuine same-pitch retrigger to force an explicit rest
  (`note=0`) between the two attacks, confirmed to round-trip correctly
  through **both** consumers: `exporter/exporter_ca65.py:1341-1343`
  (bytecode path) and `:258-270` (direct-export path) both render a frame
  absent from the `frames` dict as an explicit `$00`/rest, not a
  carry-forward of the previous value — so the intervening zero really does
  produce a note-value change both exporters' retrigger logic keys on. See
  new Finding 2 below for one small latent gap this fix's frame-offset
  bookkeeping introduces.
- **D1**: #482/NH-HW-2026-08-22-2 (`last_dpcm_note` `$FF` sentinel collision)
  is fixed — `exporter/exporter_ca65.py:1111-1116` seeds `last_dpcm_note`
  with `$00` (DPCM's actual rest sentinel), not `$FF`, distinct from the
  three tone-channel `last_*_note` vars which correctly keep `$FF` (never a
  legal MIDI note 0-127).
- **D1**: control byte `0x30` (constant-volume + length-halt) unchanged at
  `nes/envelope_processor.py:174`; duty 2-bit / volume 4-bit masking
  unchanged.
- **D2**: triangle invariant holds — no `control`/duty key reaches
  `$4008-$400B` on either front-end; `arranger/pipeline_integration.py`'s
  triangle conversion still emits no `control` key (#434 fix, unchanged
  since 08-22).
- **D3**: noise period/mode plumbing unchanged since 08-22 (no relevant
  file touched by `59b8a45..1803fa7`).
- **D4**: DPCM DAC-zero-before-enable ordering holds at all three
  `init_music`/`reset` sites (`exporter/exporter_ca65.py:1089`,
  `:1988` via `audio_init_hw_and_state:196-197`, `:902` in the standalone
  `reset` proc) — `sta $4011` still precedes `sta $4015`. The new DPCM
  dynamic-start-bank feature landed since the last pass (`1803fa7`, #519)
  was reviewed fresh: `DpcmPacker.__init__(start_bank=...)` /
  `_place_sample` correctly offset `bank_id` by `start_bank` before it's
  recorded in `dpcm_bank_table`, and the `self.start_bank + len(self.banks)
  >= 60` overflow guard (`dpcm_sampler/dpcm_packer.py:112`) still bounds
  every newly-allocated bank below the mapper's 60-bank swap pool
  regardless of `start_bank`'s value, so a DPCM bank index can't silently
  exceed the physical pool. `CA65Exporter.next_bank` (the producer of
  `start_bank`) is `current_bank + 1` from `_build_song_bytecode`'s own
  bank-jump accounting (`exporter/exporter_ca65.py:1628`), tracked as one
  shared counter across all 5 channels — no discrepancy found between it
  and the banks the bytecode serializer actually emits.
- **D5**: pitch-table / 11-bit clamp code unchanged since 08-22; no new
  producer found for the previously-flagged unclamped pitch-macro add site.
- **D6**: `velocity_to_volume` unchanged, still clamped 0-15 at every site.
- **D7**: `envelope_type` still has no real-pipeline producer (`grep -rn
  "envelope_type" --include=*.py .` outside `tests/` shows only the one
  dead-parameter read in `nes/emulator_core.py`) — ADSR/effects plumbing
  remains inert scaffolding as documented (#166). See Finding 2 below for a
  small addition to this dimension's watch list.
- **D8/D9**: `$4017=$40` (4-step mode, frame IRQ disabled) and `$4015=$0F`
  channel-enable writes are correct and unchanged in content; but see the
  CRITICAL finding above — the correctness of *what* gets written to these
  registers is moot if the code path that writes the *per-frame* registers
  never runs at all. The new `--visualizer` feature (`a63d2c9`, reviewed
  fresh) only touches PPU registers ($2000-$2007) and a new BSS byte
  (`channel_vis_vol`), gated entirely behind `.ifdef VISUALIZER_BUILD` in
  `nes/audio_engine.asm` — confirmed zero bytes of `$40xx` APU-register
  behavior change when `visualizer_mode` is off (the default), by reading
  every `.ifdef VISUALIZER_BUILD` block introduced in the `59b8a45..1803fa7`
  diff.
- **D10**: no new unclamped numeric path found; the DPCM dynamic-bank
  feature's only new numeric value (`start_bank`) is bounds-checked as
  above.
- **D11**: jukebox paths unchanged since 08-22 (no commits touched the
  `.ifdef JUKEBOX_BUILD` blocks in this window); the new DPCM dynamic-bank
  feature is single-song-only (`pack_dpcm_into_asm` is never called from
  `run_song_build`, confirmed by grep — matches `docs/ROADMAP.md`'s
  documented v1 scope of "DPCM rejected per-song" for jukebox builds), so
  it does not interact with the jukebox `song_table`/bank-stride contracts.

---

## Findings

### NH-HW-2026-08-24-1: Generated `reset` enables NMI before the PPU's ~2-vblank warm-up window closes — NMI (and therefore all per-frame audio) may never actually start
- **Severity**: CRITICAL
- **Dimension**: 8 (60Hz frame timing & frame counter init) / 9 (register
  enable correctness) extended to the PPU power-on/reset timing contract
  that gates whether *any* of this audit's other dimensions ever execute at
  runtime — explicitly outside the skill's normal per-register checklist,
  flagged here per this session's investigation priority
- **Location**: `nes/project_builder.py:538-561` (`_generate_main_asm`'s
  `reset:` label through `mainloop:`); the gap is shared by
  `mappers/nrom.py:63-65`, `mappers/mmc1.py:108-131`,
  `mappers/mmc3.py:111-131` (`generate_init_code()`, none of which contain a
  PPU wait either — this is one template gap, not a per-mapper issue); and
  by `exporter/exporter_ca65.py:1086-1117` (`init_music`) /
  `nes/audio_engine.asm:193-244` (`audio_init_hw_and_state`), both of which
  confirm the actual per-frame register writes live exclusively in
  `update_music`/`audio_update`, never in `reset`/`init_music` itself
- **Status**: **Existing** — filed today, independently, as
  `MAP-2026-08-24-1` in `docs/audits/AUDIT_MAPPERS_2026-08-24.md` (same HEAD
  commit, `1803fa7`), which covers the mapper/reset-template side of this
  same defect in full. Reported here (not re-filed as a second GitHub issue)
  because it is squarely this audit's territory too — this pass adds the
  APU-engine-side confirmation that `init_music`/`audio_init_hw_and_state`
  never call `update_music`/`audio_update` even once outside the NMI path,
  which is what turns "NMI might not enable" into "therefore literally zero
  notes ever play." Directly relevant to open issue **#3** ("Output seems
  silent") and distinct from the fixed #291 (`CODE_8000` bank placement) and
  #348/NH-HW-2026-07-18-1 ($4011 DAC zero) — neither of those touches
  reset-time PPU sequencing.
- **Hardware ref**: No `docs/APU_*.md` covers PPU power-on/reset timing (out
  of this doc set's APU-only scope — this is a PPU, not APU, hazard). The
  underlying fact is the standard, universally-documented NES init
  contract (nesdev.org "PPU power up state" / "Init code": writes to
  PPUCTRL/PPUMASK/PPUSCROLL/PPUADDR before the PPU's ~29,658-cycle,
  2-vblank warm-up completes are unreliable and commonly dropped by
  accurate PPU emulation and real hardware). The codebase already
  demonstrates first-party awareness of this exact contract in two other
  places: `exporter/exporter_ca65.py:887-894` (`standalone` reset proc's own
  `; PPU warmup` comment + `@wait_vbl1`/`@wait_vbl2` loop — dead code in
  practice, since `main.py` never passes `standalone=True`, confirmed by
  grep) and `nes/visualizer.py:114-121` (`generate_visualizer_init`'s
  `"Wait for two VBlanks so the PPU is warmed up before we touch it."` +
  `@vis_vblankwait1`/`@vis_vblankwait2`) — the correct pattern is written
  twice elsewhere in this repo, just never in the one reset routine every
  real ROM actually ships.
- **Description**: `NESProjectBuilder._generate_main_asm`'s `reset:` label
  runs, in order: `sei`/`cld`/stack setup (~8 cycles) → the selected
  mapper's `generate_init_code()` (~10-30 instructions depending on mapper,
  well under a hundred cycles) → zero `frame_counter` → (optionally,
  `--debug`/`--visualizer` init, both off by default) → `jsr init_music`
  (a short, fixed-size APU-register setup routine — confirmed via
  `exporter/exporter_ca65.py:1086-1117` and
  `nes/audio_engine.asm:133-244`, neither of which loops over anything
  bigger than 5 channels' worth of pointer stores) → `lda #$80 / sta $2000`.
  None of this totals more than a few hundred CPU cycles — roughly 0.5-1% of
  the ~29,658-cycle warm-up window the PPU needs after reset. On real
  hardware and PPU-accurate emulation, the `sta $2000` write this early is
  not guaranteed to take effect, meaning the NMI-enable bit (bit 7) never
  actually latches. The CPU then falls into `mainloop: jmp mainloop` and
  spins there permanently — there is no other trigger for `update_music`
  anywhere in the generated ROM (`$4017` is explicitly programmed to disable
  the frame IRQ in the very `init_music` call that just ran, and `irq: rti`
  is a no-op), so if NMI doesn't start, **nothing** ever calls
  `update_music`/`audio_update` — not once, not ever. `init_music`'s own
  writes (`$4015=$0F` enabling channels, `$4017=$40`, sweep-disable,
  DMC-DAC-zero, sentinel-note seeding) all still execute and leave real
  `sta $40xx` opcodes in the compiled ROM — exactly what a static
  byte-pattern scan of the binary would find — but none of them ever write
  an actual pitch, volume, or duty for any note, because that logic lives
  exclusively in the NMI-gated `update_music`/`play_music_frame` (direct-
  export) or `audio_update` (bytecode) procs.
- **Evidence**: `nes/project_builder.py:538-561` — the generated template,
  reproduced in full order:
  ```
  reset:
      sei
      cld
      ldx #$FF
      txs
  {mapper.generate_init_code()}      ; no $2002 poll in any mapper
      lda #$00
      sta frame_counter
      sta frame_counter+1
  {debug_init_call}                  ; off by default, no $2002 poll either
  {visualizer_init_call}             ; off by default -- the ONE call site
                                      ; that *would* add the correct wait
      jsr init_music                 ; APU-only setup, no note data written
      lda #$80
      sta $2000                      ; <-- NMI-enable write, ~100-150 cycles
                                      ;     after reset, no wait beforehand
  mainloop:
      jmp mainloop
  ```
  Contrast with the dead `standalone` reset proc
  (`exporter/exporter_ca65.py:880-894`) and the live but opt-in
  `visualizer_init` (`nes/visualizer.py:114-121`), both of which correctly
  poll `$2002` twice before touching any PPU/APU register. `init_music`
  (`exporter/exporter_ca65.py:1086-1117`) and `audio_init_hw_and_state`
  (`nes/audio_engine.asm:193-244`) both confirmed to `rts` without ever
  calling `update_music`/`audio_update`/`play_music_frame`.
- **Impact**: Every ROM built via the default pipeline (`main.py
  input.mid output.nes`) or the `prepare`/`compile` subcommands, on every
  mapper (NROM/MMC1/MMC3), **unless** `--visualizer` happens to be passed
  (which incidentally adds the wait for an unrelated reason). No workaround
  at the CLI level — CRITICAL per `_audit-severity.md`'s "Produces a
  broken/unplayable ROM... with no workaround" / "Bad reset/NMI/IRQ vector
  ... in generated ROM" floor: the vectors themselves are correct, but the
  runtime effect (NMI never engaging) is the same class of catastrophic,
  no-workaround failure. This is very likely the root cause of the reported
  `canyon.mid` MMC3/Nestopia total-silence bug this session is
  investigating, and of the long-standing open issue #3.
- **Related**: `MAP-2026-08-24-1` (the primary, first-filed report of this
  defect — see `docs/audits/AUDIT_MAPPERS_2026-08-24.md` for its suggested
  fix, a shared `bit $2002 / bpl` ×2 wait loop inserted right after the
  stack setup and before `generate_init_code()`, plus a regression test
  asserting `"bit $2002"` precedes `"sta $2000"` in generated `main.asm` for
  a plain build of every mapper). Cross-refs: #291 (fixed — a different,
  already-closed total-silence MMC3 bug, `CODE_8000` bank placement);
  #348/NH-HW-2026-07-18-1 (fixed — DMC DAC zero); open issue #3.
- **Suggested Fix**: Same as `MAP-2026-08-24-1` — insert the standard
  double `bit $2002 / bpl` wait loop into `nes/project_builder.py`'s
  `reset:` template immediately after `ldx #$FF / txs`, before
  `{self.mapper.generate_init_code()}`, matching the pattern already
  correctly implemented in `nes/visualizer.py:114-121`. Consider factoring
  it into one shared snippet both call so the two copies (and the dead
  standalone-exporter copy) can't drift again. Add a regression test
  asserting `"bit $2002"` appears in generated `main.asm` before the
  `"sta $2000"` NMI-enable write, for a plain (no `--debug`, no
  `--visualizer`) build of every mapper — this gap currently has zero test
  coverage of any kind.

### NH-HW-2026-08-24-2: #481's same-pitch-retrigger fix starts the borrowed note's envelope one frame_offset late, silently skipping the attack sample the moment a real envelope producer exists
- **Severity**: LOW
- **Dimension**: 1 (retrigger correctness) / 7 (envelope/ADSR — currently
  inert scaffolding)
- **Location**: `nes/emulator_core.py:125-148` — `frame_offset = f -
  start_frame` is still computed against the un-borrowed `start_frame`, but
  the loop that calls `get_envelope_control_byte(..., frame_offset, ...)`
  now iterates `range(render_start_frame, end_frame)`, where
  `render_start_frame = start_frame + 1` on a detected retrigger
  (`:126-128`) — so `frame_offset` starts at `1`, never `0`, for exactly the
  notes this fix targets
- **Status**: NEW (not covered by `AUDIT_NES_HARDWARE_2026-08-22.md`, which
  predates #481's fix; not present in `docs/audits/AUDIT_ARRANGER_*.md` or
  any GitHub issue title searched)
- **Hardware ref**: `docs/APU_ENVELOPE_REFERENCE.md` §4/§5 (constant-volume
  output, engine-driven envelope) — the envelope curve's attack phase is
  defined relative to `frame_offset == 0` being the note's first frame;
  `nes/envelope_processor.py:get_envelope_value`'s percussion/ADSR branches
  index from `frame_offset` directly
- **Description**: #481's fix (verified correct above) intentionally skips
  writing the note's own would-be frame 0 to force a rest boundary for
  retrigger detection, but does so by shifting the render loop's start
  (`render_start_frame`) without also shifting the `frame_offset` base used
  inside that loop. Today this is inert: `envelope_type` is always
  `"default"` (flat `attack=0, decay=0, sustain=15, release=0"`, #166 —
  confirmed still the only reachable value across the whole pipeline), so
  no envelope curve currently reads `frame_offset` in a way that produces
  audible output differences. The moment any future envelope producer sets
  a real `envelope_type` (the "piano"/"pad"/"pluck"/"percussion" catalog
  this same file already defines but nothing wires up), every retriggered
  note that borrowed a frame under #481 would begin its envelope one frame
  into its own attack ramp instead of at the ramp's actual start — a small,
  silent truncation of the attack transient specifically correlated with
  the repeated-note material #481 was written to fix, i.e. exactly the
  material most likely to expose it.
- **Evidence**: `nes/emulator_core.py:131-148`:
  ```python
  pitch = self.midi_to_nes_pitch(event['note'], channel_type)
  envelope_type = event.get('envelope_type', 'default')
  for f in range(render_start_frame, end_frame):
      frame_offset = f - start_frame   # starts at 1, not 0, when render_start_frame == start_frame + 1
      if channel_type.startswith('pulse'):
          control_byte = self.envelope_processor.get_envelope_control_byte(
              envelope_type, frame_offset, end_frame - start_frame, default_duty, None, velocity
          )
  ```
- **Impact**: None under current production behavior (envelope scaffolding
  is unreachable, per D7 above). Becomes a real, silent one-frame
  attack-truncation bug on retriggered notes the instant a real
  `envelope_type` producer is wired up — a latent trap of the same shape
  this skill's Dimension 5 notes were already retired for elsewhere in this
  codebase (unclamped adds left behind by a since-removed feature).
- **Related**: #481/NH-HW-2026-08-22-1 (the fix this narrows), #166/NH-24
  (why this is inert today).
- **Suggested Fix**: When `render_start_frame != start_frame`, either
  compute `frame_offset = f - render_start_frame` (re-basing the envelope
  clock to the note's actually-rendered first frame, matching what the
  hardware/ear perceives as the attack) or explicitly pass a synthetic
  `frame_offset` of `0` for the loop's first iteration. Cheapest fix: rebase
  to `render_start_frame` — one line, no change to #481's rest-boundary
  behavior.

---

## Notes on scope boundaries

- The CRITICAL finding above is a PPU (not APU) reset-timing hazard and sits
  formally outside every one of this skill's eleven APU-register
  dimensions; it is included per this session's explicit investigation
  priority and because its consequence — zero APU register writes from
  `update_music`/`audio_update` ever executing — is the single largest
  possible "hardware correctness" defect this audit could report: every
  other finding in this and prior `AUDIT_NES_HARDWARE_*.md` reports is moot
  for any ROM where this bug fires, since none of those per-register writes
  ever run.
- This report deliberately does not re-derive Dimensions 2/3/5/6/7/9/10/11
  from scratch; `git diff --stat 59b8a45..1803fa7` shows no changes to
  `nes/pitch_table.py`, and the `nes/envelope_processor.py`/
  `nes/emulator_core.py`/`exporter/exporter_ca65.py` changes in that window
  are limited to the #481/#482 fixes (re-verified above) and the
  `.ifdef VISUALIZER_BUILD`-gated additions (reviewed and confirmed inert
  when visualizer mode is off). `AUDIT_NES_HARDWARE_2026-08-22.md` remains
  the fuller from-scratch derivation for those dimensions.

## Suggested next step

```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_2026-08-24.md
```

Note for `/audit-publish`: NH-HW-2026-08-24-1 is a duplicate of
`MAP-2026-08-24-1` (already pending publication from
`docs/audits/AUDIT_MAPPERS_2026-08-24.md`) — file it once, cross-link both
report sections in the issue body, do not create two GitHub issues for the
same defect.
