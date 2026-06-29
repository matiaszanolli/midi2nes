# Pipeline Integrity Audit — 2026-06-29

Scope: end-to-end conversion chain (parse → map/arrange → frames → detect-patterns →
export → prepare → compile → validate) audited as a contract-bound system, per
`.claude/commands/audit-pipeline/SKILL.md`. Focus: all dimensions.

## Summary

This audit follows the 2026-06-28 pipeline audit and the hardening commit `7b57028`
("fix: harden pipeline safety gates — vectors, capacity, truncation (#6, #10, #11)")
plus the dispatch/flag fixes in `#8`. Most CRITICAL/HIGH findings from the prior audit
are **fixed and verified** in the live tree (see "Verified-fixed" below). The remaining
live issues are MEDIUM/LOW interface and safety gaps.

### Most dangerous live contract break
None CRITICAL or HIGH remain open. The previously-CRITICAL items (silent unbootable
ROM ship, swallowed typo flags, unwarned 2000-event truncation) are fixed. The most
notable live gap is a pair of **declared-but-ignored `--config` flags** on
`detect-patterns` and `song add` (a misleading interface, MEDIUM), and the
already-tracked backup-restore gap (#26).

### Does the step-by-step path produce the same ROM as the default path?

**Yes, materially** — for the same input both paths now:
- use the **fast parser** (`parser_fast.parse_midi_to_frames`) — confirmed at
  `main.py:41` (run_parse) and `main.py:421` (run_full_pipeline). The top-level
  `from tracker.parser import parse_midi_to_frames` at `main.py:16` is imported but
  **never called** on any live path (LOW dead-import, noted below).
- share pattern-detection bounds via module constants `PATTERN_MIN_LENGTH=3` /
  `PATTERN_MAX_LENGTH=12` (`main.py:36-37`), used by both `run_detect_patterns`
  (`main.py:278-279`) and the default path (`main.py:476`, `:482`). The prior
  parameter divergence (closed #19 / F-08) is gone.
- apply the **same large-file sampling policy** (`sample_events_for_detection`,
  `MAX_PATTERN_EVENTS=15000`) — `run_detect_patterns` samples explicitly
  (`main.py:298`); the default path samples inside `ParallelPatternDetector`
  (`pattern_detector_parallel.py:49`). The prior asymmetry (F-09) is resolved.

Residual non-ROM-affecting divergence: `references` is computed by the detector but
**not consumed** by the exporter on either path (documented at
`exporter/exporter_ca65.py:839-841`), so the prior "references-format gap" the SKILL
warns about (Dimension 1) is **moot** — the exporter ignores `references` entirely and
derives every output byte from `frames`. This is no longer a contract corruption.

### Findings per dimension
- Dimension 1 (Stage JSON contract): 1 LOW (unguarded `events` key in `run_map`).
- Dimension 2 (full vs step parity): 0 new (prior divergences fixed).
- Dimension 3 (flag routing): 2 MEDIUM (ignored `--config` on `detect-patterns` and
  `song add`).
- Dimension 4 (error propagation): 0 new (validate_rom gate verified).
- Dimension 5 (temp files): 0 new (output written outside temp dir, verified).
- Dimension 6 (backup/overwrite): 1 Existing (#26), 1 Existing (#23).
- Dimension 7 (large-file fallback): 0 new (truncation now warned + sampled).
- Dimension 8 (song bank): 1 Existing (#33).
- Cosmetic stats: 1 Existing (#17).

Severity totals (this report): CRITICAL 0, HIGH 0, MEDIUM 2, LOW 3.

## Contract Map

| Stage boundary | Producer (fn / key) | Consumer (fn) | Verified |
|---|---|---|---|
| parse → map | `parse_fast` → `{"events", "metadata"}` | `run_map` reads `midi_data["events"]` | ✓ (key matches; unguarded — P-02) |
| map → frames | `assign_tracks_to_nes_channels(events, dpcm_index)` | `NESEmulatorCore.process_all_tracks` | ✓ |
| arrange → export | `arrange_for_nes(events,…)` → `{channel:{frame:{…}}}` | exporter / detector loops | ✓ (int frame keys; `.get('note',0)` tolerant) |
| frames → detect | `{channel:{frame:{note,volume,…}}}` | detector event loop | ✓ |
| detect → export | `{patterns, references, stats(, variations)}` | `run_export` reads `patterns`,`references` | ✓ (`references` ignored by exporter — by design) |
| export → prepare | `export_tables_with_patterns(frames,patterns,refs,out)` → music.asm | `NESProjectBuilder.prepare_project` | ✓ |
| prepare → compile | `NESProjectBuilder` (MMC3) → project dir | `compile_rom(project_dir, output_rom)` | ✓ |
| compile → validate | `compile_rom` → bool | `validate_rom` (vectors/APU fatal gate) | ✓ |

## Verified-fixed since 2026-06-28 (no regression)

- **F-02 (CRITICAL)** unbootable-ROM-ships-as-SUCCESS → `validate_rom`
  (`main.py:115-157`) now treats invalid `$FFFA-$FFFF` vectors and zero APU init as
  **fatal**, restores backup, returns False. Verified.
- **F-03 / #8 (CRITICAL)** swallowed typo flags → unknown `-`-prefixed args now
  `sys.exit(2)` with an error (`main.py:826-831`). Verified.
- **F-04 / #10 (CRITICAL)** unwarned 2000-event truncation → fallback now
  uniformly **samples** (not head-truncates) via `sample_events_for_detection`, sets
  `pattern_loss_warning`, and prints an INCOMPLETE-OUTPUT banner (`main.py:485-494`,
  `:628-629`). Verified.
- **F-05 / #13 (MEDIUM)** `map --config`/`--dpcm-index` ignored → `--config` dropped,
  `--dpcm-index` honored (`main.py:49`, `:670`). Verified.
- **F-06 (MEDIUM)** no compile parity / `run_prepare` exits 0 on failure → new
  `compile` subcommand (`main.py:160-182`) and `run_prepare` now exits nonzero on
  failure (`main.py:202-204`). Verified.
- **F-08 / #19 (MEDIUM)** detector param divergence → shared `PATTERN_MAX_LENGTH`. Fixed.
- **F-09 (MEDIUM)** asymmetric large-file handling → shared sampling policy. Fixed.
- **F-11 / #11 capacity** → `check_mapper_capacity` pre-flight on both `prepare`
  (`main.py:189`) and default path (`main.py:587`). Verified.
- **F-12 (LOW)** `.nes.backup` never cleaned → now `backup_path.unlink(missing_ok=True)`
  on success (`main.py:634-635`). Verified.

## Findings

### P-01: `detect-patterns --config` is declared but silently ignored
- **Severity**: MEDIUM
- **Dimension**: 3 — Flag Routing
- **Both paths?**: Step-by-step only (`detect-patterns` subcommand).
- **Location**: `main.py:699` (declaration) vs `main.py:273-314` (`run_detect_patterns`)
- **Status**: NEW
- **Description**: `p_patterns.add_argument('--config', help='Path to pattern detection configuration')`
  declares a config flag, but `run_detect_patterns` never reads `args.config` — it
  hardcodes `EnhancedTempoMap(initial_tempo=500000)` and the module-level
  `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH`. A user passing `--config my.yaml` gets the
  defaults with no error. This is the same class of defect as the closed #13
  (`map --config`), which was fixed for `map` but not for `detect-patterns`.
- **Evidence**: `grep "args.config" main.py` returns only `run_config_validate`; the
  `detect-patterns` handler body contains no `config` reference.
- **Impact**: Misleading CLI — the user believes pattern-detection bounds/tempo are
  configurable per-run but they are silently ignored, yielding a different (default)
  compression than requested. No ROM corruption; metrics/compression only.
- **Related**: Closed #13 (F-05, the `map` sibling). New regression-class sibling.
- **Suggested Fix**: Either wire `--config` into `ConfigManager` to source
  `min_length`/`max_length`/tempo, or drop the flag (as #13 did for `map --config`).

### P-02: `run_map` reads `midi_data["events"]` with no guard → bare `KeyError` on malformed parse JSON
- **Severity**: LOW
- **Dimension**: 1 — Stage JSON Contract Integrity
- **Both paths?**: Step-by-step only (default path catches it in the outer `try`).
- **Location**: `main.py:51` (`run_map`); same pattern at `main.py:432`, `:440`
- **Status**: NEW
- **Description**: `run_map` does `assign_tracks_to_nes_channels(midi_data["events"], …)`
  directly on a user-supplied JSON. If the parse output is hand-edited or produced by a
  drifted/older tool without an `events` key, this throws an uncaught
  `KeyError: 'events'` with a raw traceback instead of a clean
  `[ERROR] parse output missing 'events'` message. In `run_full_pipeline` the same
  access is wrapped by the top-level `except Exception` (`main.py:637`) so it degrades
  gracefully; the step-by-step `run_map` has no such guard.
- **Evidence**: `main.py:47-51` — `midi_data = json.loads(...)` then
  `midi_data["events"]` with no `if "events" not in midi_data` check.
- **Impact**: Poor UX on a malformed intermediate; not reachable under the normal
  parser (which always writes `events`). No data corruption.
- **Related**: SKILL Dimension 1 ("a parse output with no `events` key fails loudly,
  not with a bare `KeyError`").
- **Suggested Fix**: Guard with a clear message: `if "events" not in midi_data: print("[ERROR] Parse output missing 'events' key"); sys.exit(1)`.

### P-03: `song add --config` is declared but silently ignored
- **Severity**: MEDIUM
- **Dimension**: 3 — Flag Routing / 8 — Song-Bank Path
- **Both paths?**: Song-bank path only (disjoint from main pipeline).
- **Location**: `main.py:739` (declaration) vs `main.py:316-338` (`run_song_add`)
- **Status**: NEW
- **Description**: `p_song_add.add_argument('--config', help='Path to drum mapper configuration')`
  is declared, but `run_song_add` builds `metadata` from the other CLI args and calls
  `bank.add_song_from_midi(args.input, args.name, metadata)` without ever reading
  `args.config`. The drum-mapper config the help text promises is never loaded
  (`load_config` at `main.py:380` exists but is unused). Same misleading-interface
  class as #13/P-01.
- **Evidence**: `run_song_add` body (`main.py:317-338`) has no `args.config` /
  `load_config(...)` reference; `load_config` is defined but never called anywhere.
- **Impact**: Misleading CLI on the song-bank path; the user's drum-mapper config is
  silently dropped. Song-bank is JSON-only and not compiled to ROM, so no ROM impact.
- **Related**: P-01, closed #13. Also touches the disjoint song-bank path (#30 closed).
- **Suggested Fix**: Drop `--config` from `song add`, or wire `load_config(args.config)`
  into `add_song_from_midi`.

### P-04: Unused top-level import of the old full parser (`tracker.parser.parse_midi_to_frames`)
- **Severity**: LOW
- **Dimension**: 2 — full vs step parity (parser selection)
- **Both paths?**: Neither uses it; import only.
- **Location**: `main.py:16`
- **Status**: NEW
- **Description**: `from tracker.parser import parse_midi_to_frames` is imported at
  module top but **never called** — every live path imports the fast parser locally as
  `parse_fast` (`main.py:41`, `:421`). The dangling import of the *older full parser*
  is a foot-gun: a future edit that calls the module-level `parse_midi_to_frames`
  (e.g. by deleting a local `parse_fast` import) would silently switch a path to the
  slower, behaviorally-different parser with no error.
- **Evidence**: `grep -n parse_midi_to_frames main.py` — line 16 import; all call sites
  use the locally-imported `parse_fast`.
- **Impact**: No current behavior change; latent parser-drift risk. Code-quality/LOW.
- **Related**: SKILL Dimension 2 (parser-selection drift); F-14/#33 (third-parser drift
  in song-bank).
- **Suggested Fix**: Remove the unused top-level import so the only way to parse is the
  fast parser.

## Existing (open) — re-confirmed present, not re-filed

### P-E1: Backup restore does not fire on prepare-failure or top-level exception exits
- **Severity**: MEDIUM — **Status**: Existing: #26 (F-11)
- **Location**: `main.py:596-598` (prepare failure `sys.exit(1)` with no restore),
  `main.py:637-643` (top-level `except` `sys.exit(1)` with no restore).
- **Note**: The capacity-overflow exit (`main.py:590-592`) added by the #11 fix is a
  **new** restore-less exit on the same class — it occurs after the backup is made
  (`main.py:401-404`) and before compile, so an oversized re-run leaves the user's good
  ROM overwritten by nothing (the original is untouched at that point, so harmless) —
  but the prepare-failure and top-level-except exits remain the real gap. Still #26.

### P-E2: `export` appends the DPCM block in `'a'` mode — re-running clobbers/doubles
- **Severity**: MEDIUM — **Status**: Existing: #23 (F-10)
- **Location**: `main.py:266` (`open(args.output, 'a')`). The default path is safe
  (writes into a fresh temp `music.asm`); only the step-by-step `export` re-run doubles.

### P-E3: `compression_ratio` is a percentage but printed as `…x`
- **Severity**: LOW — **Status**: Existing: #17 (F-07)
- **Location**: `tracker/pattern_detector.py:771` (computes `…*100`, a percentage);
  printed as `{…:.2f}x` at `main.py:626` and as a bare percentage at `main.py:314`.
  Cosmetic/misleading stat; no output impact.

### P-E4: `SongBank.add_song_from_midi` uses the old full parser (third-parser drift)
- **Severity**: LOW — **Status**: Existing: #33 (F-14)
- **Location**: `nes/song_bank.py` (uses `tracker/parser.py`, not `parser_fast`).
  Song-bank path is disjoint from ROM build, so no ROM impact; note-handling can drift
  from the pipeline. Related to P-04 (same old-parser foot-gun).

## Suggested next step

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-06-29.md
```
