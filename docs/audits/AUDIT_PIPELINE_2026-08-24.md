# Pipeline Integrity Audit — 2026-08-24

Scope: end-to-end conversion chain (parse → map/arrange → frames → detect-patterns →
export → prepare → compile → validate) as a contract-bound system, per
`.claude/commands/audit-pipeline/SKILL.md`. This is primarily a **verify-the-fix** pass
over a large prior batch of pipeline fixes (F-01..F-13, SAFE-01, SAFE-04, PL-01..PL-06),
except **Dimension 8** (`song build` jukebox path), which is audited as new code per the
skill's explicit instruction.

Special focus per this session's request: a freshly-built MMC3 `canyon.mid` ROM produces
**no audio at all** in Nestopia despite building successfully with valid-looking reset
vectors and APU register writes in the assembled binary, even after an unrelated DPCM
bank-numbering fix (commit `1803fa7`, already applied/committed) resolved a separate
build-time capacity error. See **Finding PIPE-2026-08-24-1** below — a gap in the
pipeline's own ROM-validation gate that is squarely in this audit's territory and is
flagged CRITICAL.

**This is not a new/isolated symptom.** The mandatory dedup pass against
`gh issue list` turned up **GitHub issue #3, "Output seems silent," still OPEN**, filed by
an external user reporting the identical failure mode (a ROM that "compiles" and links but
plays no sound in jsnes.org, FCEUX, *and* Nestopia) against a different input file
(`outrun.mid`). The repo owner's own comment on that issue, dated 2025-10-13, reads almost
like a description of this exact audit's trigger: *"the code compiles properly, everything
gets linked into a valid ROM, but I'm not getting audio from it... I assume the issue lies
in the current assembly logic (the player may not be trigger[ed] for some obscure
reason)."* Finding PIPE-2026-08-24-1 below does not claim to be the specific root cause of
either `canyon.mid`'s or `outrun.mid`'s silence — it identifies why the pipeline's *own*
safety net (`validate_rom`) has never caught (and structurally cannot catch) any ROM in
this class of failure, which is exactly why #3 has stood open, unreproduced-by-tooling,
since October. Recommend `/audit-publish` link the new finding to #3 rather than filing a
disconnected issue.

---

## 1. Summary

*(finding counts and cross-dimension synthesis — finalized after all dimensions were
collected; see per-dimension sections below for detail)*

| Dimension | NEW findings | Existing/Regression | Verified-OK (no finding) |
|---|---|---|---|
| 1. Stage JSON Contract Integrity | 0 | 0 | Confirmed, incl. by full test-suite re-run — see Dim. 1 |
| 2. run_full_pipeline vs step-by-step parity | 1 NEW (HIGH) | 0 | Mostly confirmed — see finding PIPE-2026-08-24-5 |
| 3. Flag routing | 1 NEW (LOW) | 1 regression (LOW) | Mostly confirmed — see findings PIPE-2026-08-24-3/4 |
| 4. Error propagation / fail-fast | 1 NEW (CRITICAL) | 0 | Confirmed otherwise — see Dim. 4 |
| 5. Temp-file / intermediate handling | 1 NEW (LOW) | 0 | Confirmed otherwise — see finding PIPE-2026-08-24-2 |
| 6. Backup & overwrite safety | 0 | 0 | Confirmed — see Dim. 6 |
| 7. Large-file threshold & fallback | 0 | 0 | Confirmed — see Dim. 7 |
| 8. Song-bank path (`song build`) | 0 | 0 | Confirmed, hardened further than skill describes — see Dim. 8 |

**Total: 5 findings — 1 CRITICAL, 1 HIGH, 3 LOW** (0 MEDIUM).

**Most dangerous contract break**: **PIPE-2026-08-24-1** (Dimension 4, CRITICAL) — the
shared `validate_rom` gate (`main.py`) that every ROM-build entry point
(`run_full_pipeline`, `run_compile`, `run_song_build`) relies on to catch an unbootable/
non-functional ROM is built entirely on **static byte-pattern matching** over the whole
ROM file (`debug/rom_diagnostics.py`) — not execution/emulation of the CPU from the reset
vector. It cannot distinguish "this ROM correctly plays audio" from "this ROM contains the
right opcodes *somewhere* in its 512 KB, reachable or not." This is very likely why the
`canyon.mid` MMC3 ROM in this session passed validation as healthy while being completely
silent on real playback — see the full write-up below.

**Does the step-by-step path produce the same ROM as the default path?** **No — not always.**
Dimension 2 surfaced a genuine, previously-unreported divergence (**PIPE-2026-08-24-5**,
HIGH): `run_full_pipeline` can spuriously **reject** an MMC1 build (`--mapper mmc1` or
`--mapper auto` landing on MMC1) that the identical `export --mapper mmc1` step-by-step
command builds successfully, whenever pattern detection legitimately finds zero patterns
for a song (patterns mode left on, the default). Every other dimension audited (JSON
contracts, flag routing, error propagation, temp-file handling, backup safety,
pattern-detector fallback) found no divergence that would produce a functionally different
ROM between the two paths, beyond the already-known/accepted mechanism difference in the
rest of Dimension 2 (bool-return vs. typed-exception error signaling, which reaches the
same fail-closed outcome). `song build` is its own contract chain (Dimension 8), not a
variant of the single-song path, and is internally consistent between its jukebox export
and the shared `build_and_validate_rom`/backup helpers the other two entry points also use.

---

## 2. Contract Map

| Stage boundary | Producer → key(s) | Consumer | Verified matching? |
|---|---|---|---|
| parse → map | `run_parse` writes `{"events":[...], "metadata":...}` | `run_map` via `load_json_stage(path, ['events'], 'parse')` | ✓ |
| map → frames | `assign_tracks_to_nes_channels` (legacy) / `arrange_for_nes` (arranger) → per-channel mapped events | `run_frames` → `NESEmulatorCore.process_all_tracks` | ✓ |
| frames → detect-patterns | `process_all_tracks` → `{channel: {frame: {...}}}` | `run_detect_patterns` / `detect_patterns_or_direct_export`, gated by `load_json_stage(..., channel_shape=True)` | ✓ |
| detect-patterns → export | detector → `{patterns, references, stats, variations}` (4 keys, including on-disk) | `run_export` / `export_frames_and_resolve_mapper` → `CA65Exporter.export_tables_with_patterns` | ✓ |
| export → prepare | `music.asm` (+ DPCM append via shared `pack_dpcm_into_asm`, atomic-replace then append) | `run_prepare` / `NESProjectBuilder.prepare_project` | ✓ |
| prepare → compile | `nes.cfg` (mapper-marker-stamped) + `main.asm`/`music.asm` | `run_compile` / `compile_rom` (mapper recovered via `_prepared_mapper_name_from_cfg`) | ✓ |
| compile → validate | assembled `.nes` | `validate_rom` → `ROMDiagnostics.diagnose_rom` (static byte-pattern + vector-range checks only — **see PIPE-2026-08-24-1**) | ✗ (gate exists and fires on the checks it performs, but those checks cannot detect a functionally-silent-but-structurally-valid ROM) |
| bank load → export (song build) | `SongBank.import_bank` → songs sorted by `metadata['order']`, re-parsed from `midi_path` (not `segments`) | `run_song_build` / `midi_to_frames_for_song` → `CA65Exporter.export_song_bank_bytecode` | ✓ |

---

## 3. Findings

### PIPE-2026-08-24-1: ROM validation gate is static byte-pattern matching, not execution-based — cannot detect a structurally-valid-but-silent ROM
- **Severity**: CRITICAL
- **Dimension**: 4 (Error Propagation & Fail-Fast) — flagged additionally per this
  session's explicit request, as it directly explains the live "canyon.mid builds but is
  totally silent" symptom.
- **Both paths?**: Both — `validate_rom` (`main.py:552-595`) is the single shared gate
  called from `build_and_validate_rom` (`main.py:1382-1426`, used by both
  `run_full_pipeline` and `run_song_build`) and independently from `run_compile`
  (`main.py:613-666`ish). All three ROM-build entry points share the exact same blind spot.
- **Location**: `main.py:552-595` (`validate_rom`); `debug/rom_diagnostics.py:53-64`
  (`APU_PATTERNS`), `:224-243` (`_check_reset_vectors`), `:245-260`
  (`_check_apu_patterns`).
- **Status**: NEW
- **Description**: `validate_rom` is the *only* runtime-behavior gate anywhere in the
  pipeline — the sole thing standing between "ld65 linked successfully" and "ship this ROM
  to the user." It delegates entirely to `ROMDiagnostics.diagnose_rom`, whose two
  boot-fatal checks are both purely static:
  - `_check_reset_vectors` (`debug/rom_diagnostics.py:224-243`) reads the last 6 bytes of
    PRG data as NMI/RESET/IRQ vectors and considers them "valid" iff each is a 16-bit value
    in `0x8000..0xFFFF`. It does **not** check that the RESET vector actually equals the
    address of the assembled `reset:` label, that the target bank is mapped/reachable at
    power-on, or that the code there does anything sensible — any value in that huge range
    (including one that happens to land inside a swappable bank never selected at boot, or
    inside padding/`fillval=$FF` bytes) passes.
  - `_check_apu_patterns` (`debug/rom_diagnostics.py:245-260`) does
    `rom_data.count(pattern)` for fixed opcode byte sequences (e.g. `A9 0F 8D 15 40` for
    "`LDA #$0F : STA $4015`") **over the entire 512 KB ROM file**, not scoped to code
    reachable from the reset vector, not scoped to the bank that's actually selected when
    that code runs, and with no execution/emulation at all. `validate_rom`
    (`main.py:575-576`) only requires this count to be nonzero to avoid the fatal-defect
    branch.

  Combined, these checks answer "does the byte sequence `8D 15 40` appear somewhere in this
  512 KB file, and are the six vector bytes numerically in range" — not "does this ROM,
  when actually run from its RESET vector on real hardware/an accurate emulator, initialize
  the APU and produce audio." A ROM can pass both checks with flying colors (`HEALTHY`,
  nonzero `apu_pattern_count`, in-range vectors) while being **completely silent**, if:
  - a bank-switch register write is wrong so the CPU reads/executes stale/`$FF`-filled
    bank content instead of the real `update_music`/`fetch_sequence_byte` routines (this
    codebase's own comments in `mappers/mmc3.py:71-74` document a near-identical historical
    bug — a memory-area ordering mistake that put `CODE_8000`'s content in the wrong
    physical bank so "every note played garbage/silence (green screen, no crash)" — that
    class of bug is exactly what this gate cannot catch, before or after that particular
    instance was fixed);
  - `sequence_bank`/`stream_bank`/a DPCM bank register end up pointing at the wrong
    `PRG_BANK_NN` (e.g. from any future regression in the `channel_start_banks`/`next_bank`
    bookkeeping this session already touched via the DPCM start-bank fix);
  - the RESET vector is technically in-range but does not match the actual `reset:` label
    (e.g. a future linker-config edit that reorders segments);
  - the APU-init byte sequence exists in the ROM's static data (note/period tables, DPCM
    sample payload, or dead/unreachable code) by coincidence, without ever being executed.

  This is not a hypothetical: the pipeline audit's own `_audit-severity.md` special rule
  says "Bad reset/NMI/IRQ vector or APU never initialized in generated ROM → CRITICAL," and
  the entire purpose of `validate_rom` is to be the automated backstop for exactly that
  rule — but the backstop cannot see the one thing that actually matters (whether the
  vector's *target* runs correctly and whether the counted patterns are the ones actually
  *executed*).
- **Evidence**:
  ```python
  # debug/rom_diagnostics.py:240-241
  # Vectors should point to ROM space ($8000-$FFFF) or be $FFFF (unimplemented)
  valid = all(0x8000 <= vec <= 0xFFFF for vec in vectors.values())

  # debug/rom_diagnostics.py:252-254
  for pattern, description, priority in self.APU_PATTERNS:
      count = rom_data.count(pattern)   # substring search over the WHOLE ROM file
      total_count += count
  ```
  ```python
  # main.py:573-576
  if not rom_result.reset_vectors_valid:
      fatal_defects.append("invalid reset/NMI/IRQ vectors ($FFFA-$FFFF)")
  if rom_result.apu_pattern_count == 0:
      fatal_defects.append("no APU initialization code found")
  ```
- **Impact**: Every ROM-build entry point (`run_full_pipeline`, `run_compile`,
  `run_song_build`) reports a ROM as bootable/healthy under exactly the failure mode
  currently being chased in this session (structurally valid, silent on real hardware).
  Blast radius is the entire compile/validate stage boundary for every mapper and every
  song — this is not specific to DPCM, MMC3 bank count, or `canyon.mid`. Users get false
  confidence from `[ERROR]`-free, `✓ ROM Health: HEALTHY` output on a ROM that doesn't
  actually play.
- **Related**: **Existing: #3 ("Output seems silent," OPEN)** — an external user's
  `outrun.mid` build reproduces this exact symptom class (compiles, links, valid-looking
  ROM, silent in three different emulators), and the maintainer's own comment on that issue
  independently arrives at the same suspicion ("the player may not be trigger[ed] for some
  obscure reason") this finding gives a structural explanation for: the pipeline has no
  automated way to detect or reproduce that failure, so #3 has been undiagnosable by
  tooling since 2025-10-13. This finding does not resolve #3, but explains why #3's root
  cause was never caught before shipping and gives a concrete direction to close that gap.
  Also: historical precedent for this exact bug *class* is documented inline at
  `mappers/mmc3.py:71-74` (a PRG_80/PRG_FIX bank-ordering bug that silently made "every note
  played garbage/silence... no crash") — worth checking whether that historical bug was
  ever caught by `validate_rom`, or only found by manual/hardware testing (the latter is
  what both this session and issue #3's reporter had to resort to). Also relevant to
  Dimension 4's existing "ROM-validation gate only blocking on ERROR" fix (F-02/#6, closed)
  — that fix correctly promoted `reset_vectors_valid`/`apu_pattern_count==0` to fatal status
  ahead of `overall_health`, but did not (and could not, without deeper instrumentation)
  address that the underlying signals themselves are weak.
- **Suggested Fix**: This is the single highest-leverage investment available in this
  pipeline right now. Two complementary directions: (1) make `_check_reset_vectors`
  actually compare the RESET vector against the assembled address of the `reset` label
  (recoverable from the CC65 `.dbg`/map-file output `ld65 -Ln`/`-m` can emit, or by scanning
  for the label in a debug build) rather than just range-checking the raw bytes; (2) add a
  real (even minimal) 6502+APU emulation smoke-test to the validation pipeline —
  execute N frames from RESET on a lightweight in-repo or vendored NES core and assert at
  least one APU channel's volume/timer register is written with a non-degenerate
  (non-zero-period, non-zero-volume) value within the first few seconds of simulated
  playback. **Correction to a natural first instinct**: `debug/rom_tester.py`
  (`test_with_nestopia`, `debug/rom_tester.py:11-42`) is *not* an automated playback
  harness despite CLAUDE.md's "Full ROM build/playback test harness" description
  (doc-rot, LOW, worth a follow-up fix) — it only shells out to `open -a Nestopia
  <rom>` (macOS-only) and tells the human to "check the emulator window to verify audio
  playback"; it performs no verification of its own and cannot be wired into `validate_rom`
  as-is. A real fix needs an actual headless NES core (or APU-only simulator) driving
  execution from the RESET vector, not this subprocess launcher.

---

### Dimension 4 — other checks (verify-the-fix)

All other Dimension 4 items from the skill were re-traced against the current code and
confirmed still correct, no regressions found:

- `run_full_pipeline`'s single `try`/`except Exception`/`finally` (`main.py:1429` region)
  still wraps the whole build; no inner `except` was found that swallows a fatal error and
  lets a run reach ROM emission.
- DPCM-pack failure handling is shared via `pack_dpcm_into_asm` (`main.py:159-259`, broad
  `except Exception` at `:244`) and called identically from both `run_export`
  (`main.py:781-783`, `getattr(exporter, 'next_bank', 0)` as `start_bank`) and
  `export_frames_and_resolve_mapper` (`main.py:1354-1356`, same pattern) — confirmed both
  call sites now also correctly thread the DPCM start-bank fix's `start_bank=` parameter
  through (this session's own committed fix, `1803fa7`), so the two call sites did not
  drift apart the way #380/TD-28 originally worried about. The "NO DRUMS" vs. "PARTIAL DPCM
  MISS" warning labeling (`main.py:792-798` and `:1552-1556`) is confirmed identical between
  `run_export` and `run_full_pipeline`.
- `validate_rom`'s diagnostics-import guard (`main.py:565-570`) still returns `False` (not
  `True`) on any exception from `ROMDiagnostics(...).diagnose_rom(...)`, with an
  unconditional (not `--verbose`-gated) warning — confirmed fail-closed.
- CC65 failure surfacing: `compile_rom` (`compiler/compiler.py`) still converts
  `CompilationError`/`ValidationError`/any exception into a `False` return with a printed
  `[ERROR]`; `run_compile` still does a direct `sys.exit(1)` on that `False`, while
  `run_full_pipeline`/`run_song_build` go through `build_and_validate_rom`
  (`main.py:1382-1426`), which raises typed `MIDI2NESError` subclasses instead, caught by
  one `except MIDI2NESError` clause in each caller — confirmed both mechanisms are
  fail-closed and reach the same outcome (clean `[ERROR]` + exit 1 + backup restore).
- `run_prepare` (`main.py:669-703`) confirmed to wrap `prepare_project` in `try/except
  Exception: sys.exit(1)` AND separately check `if not prepared: sys.exit(1)` for a
  falsy-but-non-raising return — both branches present, no silent-exit-0 path found.

---

### Dimension 8 — Song-Bank Path (audited as new code, not verify-the-fix)

No functional defects found. This path is unusually well-hardened for code the skill
itself flags as "the youngest code in the pipeline" — several items exceed what the skill
describes:

- **`song_has_dpcm_events` is now enforced at two layers, not one.** The skill's prose
  describes a single check, `_song_has_dpcm_events` local to `main.py`. The current code has
  moved this to a shared `song_has_dpcm_events(frames)` in `exporter/exporter_ca65.py:51`
  (imported by `main.py:22`), checked both at `run_song_build`'s call site
  (`main.py:1071-1076`, before a song's frames are even yielded to the exporter) **and**
  defensively inside `CA65Exporter.export_song_bank_bytecode` itself
  (`exporter/exporter_ca65.py:1873-1880`, citing #509/EXP-2026-08-23-2) — closing exactly
  the gap the skill worried about ("a caller that skipped `main.py` entirely ... could feed
  a DPCM-bearing song straight through"). Verified: a library consumer calling
  `export_song_bank_bytecode` directly, bypassing `main.py`, is still protected.
- **Bank ordering** (`SongBank._next_order`, `nes/song_bank.py:57-71`): confirmed derives
  the next `order` from `max(existing) + 1`, not `len(self.songs)` — a remove-then-add
  cycle cannot collide two songs' `order` values (#488/PIPE-2026-08-22-4 confirmed fixed).
- **Re-parse contract**: confirmed `run_song_build` (`main.py:1052-1078`,
  `midi_to_frames_for_song`) rebuilds frames from each song's recorded `midi_path`, never
  reads the bank's stored `segments` (and `keep_segments=False` is passed to `import_bank`
  specifically because of this, `main.py:1020`) — matches the skill's described contract
  exactly. A missing/moved `midi_path` exits non-zero with a clear `[ERROR]`
  (`main.py:1054-1061`) before any partial ROM is built (whole build runs inside
  `tempfile.TemporaryDirectory`, `main.py:1097`).
- **Capacity pre-flight sharing**: confirmed `run_song_build` calls the same
  `build_and_validate_rom` helper (`main.py:1114-1117`) that `run_full_pipeline` uses, which
  runs `check_mapper_capacity` (`main.py:1406`) against the actual emitted `music.asm` — an
  N-song overrun is caught at the same pre-flight gate as a single-song overrun, not
  deferred to a raw CC65 link error.
- **`export_song_bank_bytecode` hardening beyond the skill's description**: found several
  defensive checks not called out in the skill prose, all correct: a 51-song ceiling
  derived from the engine's 8-bit `song_index*5+channel` indexing
  (`exporter/exporter_ca65.py:1805-1813`, #426); strict-equality consumption of the `songs`
  iterable in both directions — too few items raises (`:1908-1912`) and leftover items past
  `song_count` also raises (`:1920-1924`, #512/EXP-2026-08-23-5) rather than silently
  zip-truncating; and per-song error re-raising that names the offending song index/name
  (`:1884-1893`, #511/EXP-2026-08-23-4).
- **`run_song_build`'s backup/restore/typed-exception contract** (`main.py:1094-1137`)
  confirmed structurally identical to `run_full_pipeline`'s: `_backup_existing_rom` up
  front, `build_succeeded` flag, `except MIDI2NESError` / `except Exception` /
  `finally: _restore_backup(...) or backup_path.unlink(...)`.
- **Minor observation, not a finding (LOW-adjacent, informational only)**: within
  `run_song_build`, `exporter.export_song_bank_bytecode(...)`'s own `except ValueError as e:
  print(...); sys.exit(1)` (`main.py:1105-1107`) is a third error-signaling style
  (direct `sys.exit`) alongside the `MIDI2NESError`-raise style `build_and_validate_rom`
  uses later in the same function. This is harmless — `sys.exit()` raises `SystemExit`,
  which is not caught by the surrounding `except MIDI2NESError`/`except Exception` blocks
  but the enclosing `finally` (`main.py:1133-1137`) still executes and correctly restores
  the backup, since `SystemExit` is not an `Exception` subtype but `finally` runs
  regardless. No functional break; flagging only as a style inconsistency worth unifying if
  this function is touched again, matching the tone of the skill's own Dimension 2 note
  about `run_compile`'s bool-vs-exception split.
- `docs/ROADMAP.md`'s "Song banks → ROM" section (lines 57-77) checked word-for-word
  against the current code's v1 scope cuts (MMC3-only, DPCM rejected per-song, no `--debug`,
  no visual menu) — no doc-rot, all four cuts still accurate.

---

### PIPE-2026-08-24-2: DPCM-trailer append to `music.asm` is a non-atomic write, and its failure message mischaracterizes a mid-write corruption as "no drums"
- **Severity**: LOW
- **Dimension**: 5 (Temp-File / Intermediate Handling)
- **Both paths?**: Both — `pack_dpcm_into_asm` (`main.py:159-259`) is the single shared
  helper called identically from `run_export` (`main.py:779`) and
  `export_frames_and_resolve_mapper` (`main.py:1353`, used by `run_full_pipeline`).
- **Location**: `main.py:212-213` (the append), `main.py:244-258` (the except that reports
  it).
- **Status**: NEW
- **Description**: `export_tables_with_patterns`/`export_direct_frames` correctly do a full
  atomic replace of `music.asm` via `atomic_write_text` (`core/io_utils.py:13-39`, `mkstemp`
  + `os.replace`) *before* DPCM packing ever runs — the fix the audit skill's Dimension 5
  describes still holds. But the DPCM trailer append itself,
  `with open(asm_path, 'a') as f: f.write("\n\n" + packer.generate_assembly())`
  (`main.py:212-213`), is a single direct, non-atomic write. If interrupted partway (disk
  full, killed process), the already-atomically-replaced `music.asm` is left with a
  truncated DPCM assembly trailer — caught by the enclosing broad `except Exception`
  (`main.py:244`), but the resulting message, `"DPCM packing failed ({e}) — the exported ASM
  has NO drums even though dpcm_index.json may reference some"`, describes a clean
  "no drums" state, not the actual corrupted-file state.
- **Evidence**:
  ```python
  # main.py:212-213
  with open(asm_path, 'a') as f:
      f.write("\n\n" + packer.generate_assembly())
  ```
- **Impact**: Narrow trigger (OS-level write failure/process kill mid-append only), and
  self-detecting — a corrupted trailer produces a loud `ca65` assembly error at the next
  `prepare`/`compile` step rather than a silently broken ROM, so this cannot by itself reach
  a bootable-but-wrong ROM. Blast radius is a confusing error message.
- **Related**: Distinct from the already-fixed accumulation bug (#380/TD-28, re-verified
  still fine) — this is about the append call's atomicity, not about running export twice.
- **Suggested Fix**: Build the appended trailer into the same `atomic_write_text` call
  (append `packer.generate_assembly()` to the in-memory content before the one atomic
  write), or write the DPCM trailer to its own temp file and `os.replace` the concatenation.
  At minimum, reword the except-path message to not claim "no drums" when a partial write
  may have occurred.

### PIPE-2026-08-24-3: `--arranger` pre-subcommand rejection message wrongly directs `song add`/`song list`/`song remove` users toward `song build`
- **Severity**: LOW
- **Dimension**: 3 (Flag Routing)
- **Both paths?**: N/A (CLI diagnostic text only, all `song` sub-subcommands)
- **Location**: `main.py:1789-1799`
- **Status**: Regression of #487 (PIPE-2026-08-22-3)
- **Description**: The `--arranger`-before-subcommand guard branches only on
  `first_arg == 'song'`, not on which `song` sub-subcommand follows. #487 fixed the message
  for the real case where a step-by-step equivalent exists (`song build --arranger`), but
  the fix applies that wording to *every* `song ...` invocation, including `song add`,
  `song list`, and `song remove` — none of which declare `--arranger` at all (only
  `p_song_build` does, `main.py:1728`). For those three subcommands the message now
  incorrectly directs the user toward a flag placement (`song build ... --arranger`) that
  has nothing to do with the command they actually ran.
- **Evidence**: `python main.py --arranger song list bank.json` prints `Error: --arranger
  must come after 'song build', not before 'song' -- e.g. 'midi2nes song build bank.json
  out.nes --arranger'.` — confirmed live and by re-reading `main.py:1789-1799`.
- **Impact**: Diagnostic-only, no functional/ROM-output break — exit code 2 is still
  correct.
- **Related**: #487/PIPE-2026-08-22-3 (introduced this over-broad branch), #174/PL-01
  (original guard).
- **Suggested Fix**: Check the actual token after `'song'` (e.g.
  `sys.argv[sys.argv.index('song')+1]` if present) and only emit the `song build`-specific
  message when that token is `build`; fall through to the generic "no step-by-step
  equivalent" message otherwise.

### PIPE-2026-08-24-4: Default pipeline's missing-`dpcm_index.json` error suggests `--dpcm-index`, a flag the default pipeline doesn't accept
- **Severity**: LOW
- **Dimension**: 3 / 7 (Flag Routing / stage error messaging)
- **Both paths?**: Default pipeline only (`run_map`'s equivalent message is correct, since
  `map` genuinely has `--dpcm-index`)
- **Location**: `main.py:1492-1495` (message) vs. the global-flag whitelist
  (`main.py:1810-1862`, no `--dpcm-index` entry) and `SimpleArgs` (`main.py:1879-1893`, no
  `dpcm_index` attribute).
- **Status**: NEW (pre-existing since #381/SAFE-2026-07-19-1; a different class of bug than
  #13/F-05, which covers `--dpcm-index` being correctly wired into `map`)
- **Description**: `run_full_pipeline`'s legacy (non-arranger) mapping step hard-codes
  `dpcm_index_path = 'dpcm_index.json'` and, on missing file, prints the same actionable
  hint `run_map` prints — but `--dpcm-index` is never declared on the top-level parser, so
  the suggested remedy fails immediately with "Unknown option: --dpcm-index" if followed.
- **Evidence**: `python main.py --dpcm-index custom_index.json song.mid` → `Error: Unknown
  option: --dpcm-index`. Message source: `main.py:1492-1495`, copy-pasted from `run_map`'s
  guard at `main.py:280-282` where it's accurate.
- **Impact**: Diagnostic-only; sends a user down a dead end instead of "restore
  `dpcm_index.json`" or "use `midi2nes map ... --dpcm-index <path>`".
- **Related**: #381/SAFE-2026-07-19-1 (introduced the copy-pasted message), #256/D-18
  (original `run_map` guard).
- **Suggested Fix**: Either add a top-level `--dpcm-index` flag threaded through
  `SimpleArgs`/`run_full_pipeline`, or reword the default-pipeline message to not suggest a
  flag the default path doesn't accept.

---

### PIPE-2026-08-24-5: `export_frames_and_resolve_mapper` resolves the MMC1 bin-packing mapper on the wrong predicate — spurious build failure not reproducible via step-by-step subcommands
- **Severity**: HIGH
- **Dimension**: 2 (run_full_pipeline vs Step-by-Step Parity)
- **Both paths?**: **Divergence** — `run_full_pipeline` only. The step-by-step `export`
  subcommand (`run_export`) already handles this correctly.
- **Location**: `main.py:1316` (bug) vs. `main.py:746` (correct reference implementation
  in `run_export`); the dispatch predicate both must match is
  `exporter/exporter_ca65.py:1677` (`export_tables_with_patterns`: `if not patterns: return
  self.export_direct_frames(...)`) and `exporter/exporter_ca65.py:809`
  (`export_direct_frames`'s `bank_size = mapper.direct_export_bank_size() if mapper is not
  None else None`).
- **Status**: NEW
- **Description**: `CA65Exporter.export_tables_with_patterns` dispatches on the **actual
  truthiness of the `patterns` dict**, not on whether pattern mode is enabled:
  `if not patterns: return self.export_direct_frames(...)`. `export_direct_frames` only
  bin-packs MMC1 frame tables across its 16 KB switchable banks when handed a concrete
  `mapper` up front — with `mapper=None` everything lands in one flat `.segment "RODATA"`
  (bank 0 only, un-bin-packed).

  `run_export` (step-by-step) mirrors this exactly at `main.py:746`: `if not patterns:`
  — gated on the same actual dict the exporter branches on, so it resolves the mapper
  *before* export whenever the exporter is about to take the direct-export branch, for
  whatever reason (either `--no-patterns` or patterns mode legitimately finding nothing).

  `export_frames_and_resolve_mapper` (used only by `run_full_pipeline`) instead gates the
  same up-front resolution on `main.py:1316`: `if not use_patterns:` — the CLI **mode
  flag**, not the actual `pattern_result['patterns']` dict. When patterns mode is on
  (the default) but the detector legitimately finds **zero** patterns for a given song (any
  song with no repeated ≥`PATTERN_MIN_LENGTH`(3)-event sequence — short jingles, stingers,
  highly varied melodies), `export_tables_with_patterns` still takes the direct-export
  branch (`patterns == {}`), but `export_frames_and_resolve_mapper` still exports with
  `mapper=None` (since `not use_patterns` is `False`) and only resolves the mapper **after**
  export, from the already-written, never-bin-packed `music.asm`.

  With `--mapper mmc1` (explicit) or `--mapper auto` (which ranks NROM→MMC1→MMC3 by direct
  capacity and lands on MMC1 for any 30 KB–112 KB direct song), `resolve_mapper` returns a
  real MMC1 instance with no error (its only mismatch guards, `needs_mmc3`/`direct_dpcm`/
  `packed_for`, don't fire, since `packed_for` is `None` precisely because no bin-packing
  marker was ever stamped). `check_mapper_capacity` then sees one giant flat `RODATA`
  segment; `MMC1Mapper.validate_segment_sizes` buckets it into bank 0 and raises
  `MapperError` the instant it exceeds the 16 KB window — which any song in the 16 KB–112 KB
  range will, since it was never bank-packed. This is caught by `run_full_pipeline`'s
  `except MIDI2NESError`, printing a **false, misleading rejection**
  ("Music data does not fit the MMC1 PRG layout... Shorten the song or DPCM samples, or
  select a larger mapper.") — the song's real data would fit fine in MMC1's actual 112 KB
  bank-switched capacity if bin-packing had run, exactly as it would via
  `midi2nes export --mapper mmc1 ...` on the identical frames/patterns.
- **Evidence**:
  ```python
  # main.py:746 (run_export, correct)
  mapper = None
  if not patterns:
      ...

  # main.py:1316 (export_frames_and_resolve_mapper, buggy)
  mapper = None
  if not use_patterns:
      ...
  ```
  An existing test locks in the buggy behavior with an inaccurate premise:
  `tests/test_main_pipeline.py:1709-1745` (`test_patterns_path_resolves_mapper_after_export`)
  constructs `pattern_result = {'patterns': {}, 'references': {}}` (i.e. exactly the
  "detector found nothing" case) with `use_patterns=True`, and asserts
  `mock_exporter.export_tables_with_patterns.call_args.kwargs['mapper'] is None` — the class
  docstring's "patterned/bytecode resolves after" framing conflates "patterns mode is on"
  with "the bytecode path was actually taken," which is false whenever `patterns` is empty.
  No test exercises `export_frames_and_resolve_mapper` with a real (unmocked) `CA65Exporter`
  + real `MMC1Mapper` + real `check_mapper_capacity`, so the divergence was invisible to the
  suite.
- **Impact**: Any legitimate MIDI song with (a) patterns mode on (default, no
  `--no-patterns`), (b) no repeated ≥3-event sequence for the detector to find, and (c) a
  direct-export size in MMC1's 16 KB–112 KB "should fit via bank-switching" range fails the
  **entire default `midi2nes song.mid` / `--mapper auto` / `--mapper mmc1` build** with a
  misleading "shorten the song" error — even though `midi2nes export --mapper mmc1 ...`
  (step-by-step) on the exact same `frames`/`patterns` JSON succeeds. Blast radius: default
  pipeline only; `run_song_build` is unaffected (always forces MMC3, which has no
  `direct_export_bank_size`).
- **Related**: Shares the "mapper resolution timing differs by path" design introduced in
  #255/MAP-2026-07-05-1; adjacent to (but distinct from) the already-fixed
  #379/PIPE-2026-07-19-3 `references`-hardcoding divergence at the same call site.
- **Suggested Fix**: In `export_frames_and_resolve_mapper` (`main.py:1316`), gate the
  up-front mapper resolution on `if not pattern_result['patterns']:` (matching
  `run_export`'s `not patterns` and the exporter's own dispatch predicate) instead of
  `if not use_patterns:`. `pattern_result` is already computed and passed in before this
  function is called, so no additional plumbing is needed. Also correct
  `test_patterns_path_resolves_mapper_after_export`'s docstring/premise once fixed —
  construct that test's "resolves after" case with a genuinely non-empty
  `pattern_result['patterns']` instead of `{}`.

---

### Dimension 1 & 2 — other checks (verify-the-fix)

All other Dimension 1/2 items from the skill were re-traced against current code —
including a full `tests/test_main.py` + pattern/track-mapper/song-bank suite re-run — and
confirmed still correct, no regressions:

- `run_parse`/`run_map`/`load_json_stage` (with `channel_shape=True` for the frames-shaped
  consumers) still fail cleanly on missing/corrupt/wrong-stage input, confirmed by trace and
  by two dedicated regression tests (`tests/test_main.py:476-505`); `_PIPELINE_CHANNEL_KEYS`
  still mirrors `CA65Exporter.SEQUENCE_CHANNELS`, captured at import time.
- `assign_tracks_to_nes_channels` always returns all 5 channel keys (even for an all-rest
  song), matching `NESEmulatorCore.process_all_tracks`'s iteration and
  `CA65Exporter.SEQUENCE_CHANNELS` — shapes align end-to-end.
- `run_detect_patterns` persists all 4 keys (`patterns`/`references`/`stats`/`variations`)
  to disk; both detectors emit the same 4-key envelope, including their empty-input
  branches.
- `run_export` and `export_frames_and_resolve_mapper` both derive `patterns`/`references`
  from the same `pattern_result`/`pattern_data` source — no hardcoded-`{}` divergence
  reintroduced (#379/PIPE-2026-07-19-3 still holds).
- Only one parser (`tracker.parser_fast.parse_midi_to_frames`) is imported anywhere, used
  identically by `run_parse`, `midi_to_frames_for_song`, and `run_full_pipeline`;
  `tracker/parser.py` does not exist — regression-tested by
  `tests/test_main.py:3082-3109`.
- `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH` are shared module-level constants
  (`constants.py`), used identically at all three detector-construction call sites.
- The `--no-patterns` stats stub uses exactly the key set both detectors emit — no
  `original_events`/`patterns_found` mismatch anywhere in current code.
- `run_compile` shares `_backup_existing_rom`/`_restore_backup` with the other two ROM-build
  entry points; its bool-return-to-`sys.exit(1)` mechanism (confirmed: `sys.exit`'s
  `SystemExit` still propagates through the enclosing `finally`) and
  `run_full_pipeline`/`run_song_build`'s typed-`MIDI2NESError`-raise mechanism both reach
  the same fail-closed outcome.
- `--config` (pattern-detection cap overrides) reaches `args.config` identically for the
  `detect-patterns` subcommand and the default pipeline, both consumed via the single
  shared `get_pattern_detection_caps`.
- **Minor non-issue, not reported as a finding**: `tracker/parser_fast.py`'s
  `parse_midi_to_frames_with_analysis` — a separate, non-CLI-wired debug entry point never
  imported by `main.py` and never read by any downstream pipeline stage — stores
  pattern-analysis metadata under renamed keys `pattern_refs`/`compression_stats` instead of
  `references`/`stats`. Outside the audited `main.py`-orchestrated pipeline as scoped;
  noted only for completeness in case a future audit widens scope to include it.

Full test suite for these dimensions (`tests/test_main.py`, `tests/test_patterns.py`,
`tests/test_pattern_detector_parallel.py`, `tests/test_pattern_exact_gate.py`,
`tests/test_pattern_integration.py`, `tests/test_track_mapper.py`,
`tests/test_song_bank.py` — 168+168 tests across the two sub-audits) re-run and passing,
including every targeted regression test named in the prior audit's fix commits.

---

### Dimension 6 — Backup & Overwrite Safety (verify-the-fix)

No findings. Re-traced and confirmed, no regressions:

- `Path('my.song.nes').with_suffix('.nes.backup')` → `my.song.nes.backup` (confirmed live in
  a Python one-liner) — `with_suffix` only replaces text after the last dot, no dotted-stem
  clobber.
- `run_full_pipeline` has a single `finally` (no `return` anywhere in the function body)
  covering every internal failure path, `sys.exit(1)` included (`SystemExit` still runs
  `finally`).
- `run_song_build` and `run_compile` share the exact same backup-before /
  restore-in-`finally`-unless-succeeded contract as `run_full_pipeline` — confirmed
  structurally identical across all three, not just "matching."
- Backup cleanup (`backup_path.unlink(missing_ok=True)`) on success confirmed present in
  **all three** entry points (the audit skill only explicitly called out
  `run_full_pipeline` for double-checking) — `run_compile`, `run_song_build`, and
  `run_full_pipeline` all do it.
- First-time-build (no pre-existing ROM) validation failure: `_restore_backup`'s
  `backup_path is None` branch moves the just-written unbootable ROM to `<name>.nes.failed`
  rather than leaving it at the output path — traced end-to-end for `run_compile`.
- Step-by-step `export`/`prepare`/`frames` still silently overwrite `output` with no
  backup, by design, and do so safely (full in-memory content built before the one atomic
  write) — the only weaker link is the DPCM append step's non-atomicity (PIPE-2026-08-24-2
  above), which appends to a freshly-written export, not a hand-edited file.

---

## 4. Next Steps

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-08-24.md
```

When publishing, link **PIPE-2026-08-24-1** to **GitHub issue #3** ("Output seems silent,"
OPEN) rather than filing it as a fully disconnected new issue — they describe the same
underlying gap in the pipeline's ability to detect/prevent shipped-but-silent ROMs, from two
different angles (a user's real symptom vs. this audit's structural diagnosis of why the
pipeline never caught it).
