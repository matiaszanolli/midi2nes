# Safety & Robustness Audit — 2026-08-05

Scope: the **Python layer** — error handling, malformed-input resilience, subprocess/CC65
safety, unsafe deserialization, inter-stage JSON guards, file/resource handling, exception-type
discipline, and partial-output-on-failure. This is not a NES-hardware audit.

Base commit: `3b16c5a`. Dedup source: `/tmp/audit/issues.json` (`gh issue list --repo
matiaszanolli/midi2nes --limit 200`) + scan of `docs/audits/`.

## Summary

The safety/robustness surface remains in **excellent** shape and is essentially unchanged
since the 2026-07-19 safety audit. Every dimension the skill enumerates was re-verified
against the current `main.py` (line numbers have shifted since 07-19 but the code paths are
behaviorally identical):

- **D1 Swallowed-Error Handling**: `run_full_pipeline`'s 8-step `try` (`main.py:805`) /
  broad `except Exception as e` (`main.py:1124`) is unchanged — still relays specific typed
  exceptions with a clean message, still LOW (testability only). The parallel→sequential
  pattern-detector fallback (`main.py:870-895`) and its lossy-resample warning are intact
  and still the documented fallback. The DPCM-pack blocks in both `run_export`
  (`main.py:588-625`) and `run_full_pipeline` (`main.py:993-1044`) still build a loud
  `⚠️ NO DRUMS` / `⚠️ Warning` banner for the "index exists but resolves 0 samples" and
  "packing raised" cases — but the pre-existing **asymmetry** flagged in `#380` (both copies
  are duplicated and have already drifted) is confirmed still present: when
  `dpcm_index.json` is entirely absent, `run_full_pipeline` prints an info line
  (`"ℹ️ No dpcm_index.json found, skipping DPCM packing."`, `main.py:1035`) but `run_export`
  prints **nothing at all** for the same case (`main.py:597-616` has no `else:` branch).
  Tracked as Existing (see Findings).
- **D2 Malformed-Input Resilience**: both `mido.MidiFile` call sites
  (`tracker/parser_fast.py:17`, `tracker/parser.py:12`) remain guarded, converting
  `(EOFError, OSError, ValueError)` to `InvalidMIDIError`; `FileNotFoundError` still passes
  through unchanged. No unguarded `mido.MidiFile` anywhere else in the repo (grep-verified).
  The per-event drop counter/warning in `parser_fast.py:157-171` (`dropped_note_events`,
  `last_drop_reason`) is intact and unfired in this review (no evidence of a live drop).
- **D3 Subprocess/CC65 Safety**: all `ca65`/`ld65` invocations remain argv lists;
  `check_toolchain()` gates both `ROMCompiler.compile()` (`compiler/compiler.py:182`) and
  `CC65Wrapper.build()` (`compiler/cc65_wrapper.py:260`); returncode+stderr are checked and
  raised as `CompilationError`/`ToolchainError` at every call site; `10s`/`120s`/`60s`
  timeouts are all present and wrapped in `except subprocess.TimeoutExpired`. The sole
  `shell=True` (`compiler/compiler.py:120`) remains provably fed only by
  `BaseMapper.generate_post_process_commands`, which returns a static `""` in every mapper
  — `mmc1.py`, `mmc3.py`, and `nrom.py` were re-checked and **none** define an override
  (grep for `def generate_post_process_commands` returns exactly one hit, in `base.py`).
- **D4 Unsafe Deserialization**: repo-wide grep (excluding `venv/`) for
  `eval(`/`exec(`/`yaml.load(`/`pickle.load`/`os.system`/`shell=True` finds only the one
  documented, guarded `shell=True` above. `config/config_manager.py:127` still uses
  `yaml.safe_load`.
- **D5 JSON-Intermediate Guards**: `load_json_stage` (`main.py:75-104`) still guards all
  four inter-stage subcommand reads — `run_map` (`:117`), `run_frames` (`:137`), `run_export`
  (`:522`/`:530`), `run_detect_patterns` (`:630`) — confirmed by re-reading each call site
  and its downstream key access.
- **D6 File/Resource Handling**: every `open()` call in `main.py`, `config/`, `exporter/`,
  `compiler/`, `tracker/`, `nes/`, `dpcm_sampler/` uses a `with` block (grep-verified, no bare
  `open()`). `tempfile.TemporaryDirectory` (`main.py:802`) auto-cleans. Backup
  create/delete/restore contract re-verified in both `run_full_pipeline`
  (`main.py:790`, `:1121-1122`, `:1132-1136`) and `run_compile` (`main.py:462`, `:477-481`) —
  backup is deleted on success, restored only when `build_succeeded` is `False`.
- **D7 Exception-Type Discipline**: `config/config_manager.py`'s `_load_from_file` still
  narrows to `(OSError, yaml.YAMLError)` → `ConfigurationError` (`:126-134`); `save()`
  (`:251`) and `validate()` (`:299`) both raise typed `ConfigurationError`/`ValidationError`,
  not bare `ValueError` — the 07-19 audit's confirmation still holds. No bare `except:`
  anywhere in the repo (grep-verified).
- **D8 Partial-Output-on-Failure**: `run_full_pipeline` still builds inside the
  auto-cleaned temp dir and only reaches the final path via `ROMCompiler.compile()`'s
  `shutil.copy`. `run_export`'s direct `.asm` write (`exporter/exporter_ca65.py:928,1357`)
  remains non-atomic (Existing: `#385`). The backup/restore `finally` block is single and
  centralized (D6, above).

No CRITICAL / HIGH / MEDIUM findings. Three items carried forward as **Existing** (all
already filed and OPEN from the 07-19 audit / tech-debt audit); no regressions and no new
findings this cycle.

### Counts

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 0 |
| LOW | 0 (3 Existing, not re-filed) |
| **Total new findings** | **0** |

By dimension: D1 (Existing ×2: `#381`, `#380`-cross-ref), D8 (Existing ×1: `#385`). D2, D3,
D4, D5, D6, D7 confirmed clean with no findings, new or existing.

### Three highest-leverage robustness items (still open, unchanged priority order)

1. **`#381`** — guard the full pipeline's legacy-mode `dpcm_index.json` dependency the same
   way `run_map` already does, so a missing index degrades/reports cleanly instead of
   aborting the whole run at step 2.
2. **`#380`** — de-duplicate the two DPCM-packing blocks (`run_export` /
   `run_full_pipeline`) into one helper; this is also what's silently letting `run_export`
   give zero feedback when `dpcm_index.json` is missing while `run_full_pipeline` at least
   prints an info line (see Finding below).
3. **`#384`** — optionally narrow `run_full_pipeline`'s catch-all to distinguish
   `MIDI2NESError` from a truly unexpected defect, for testability (no functional impact
   today).

---

## Findings

### SAFE-2026-08-05-1: `run_export`'s DPCM-pack block gives zero feedback when `dpcm_index.json` is missing (unlike its `run_full_pipeline` twin)
- **Severity**: LOW (tracked at LOW per Existing `#380`; see Impact for why a safety-lens
  read pushes toward MEDIUM if the two copies drift further)
- **Dimension**: D1 (Swallowed-Error Handling) / D8 (Partial-Output-on-Failure)
- **Location**: `main.py:588-625` (`run_export`'s DPCM block) vs. `main.py:993-1044`
  (`run_full_pipeline`'s DPCM block, specifically the `else:` at `:1034-1035`)
- **Status**: Existing: #380 (OPEN, tech-debt/LOW; this audit re-confirms the exact
  behavior #380's own Evidence section already describes, from the safety-domain angle)
- **Description**: Both DPCM-packing blocks branch on `Path('dpcm_index.json').exists()`.
  `run_full_pipeline`'s block has an explicit `else:` that prints an info line
  (`"ℹ️ No dpcm_index.json found, skipping DPCM packing."`, `main.py:1035`) when the index
  is absent. `run_export`'s block has **no `else:` branch at all** (`main.py:597-616`) — if
  `dpcm_index_path.exists()` is `False`, the `try` body simply does nothing, `
  dpcm_pack_warning` stays `None`, and the subcommand prints only its generic
  `" Exported CA65 ASM -> {args.output}"` success line with no indication the song's drums
  (if any) were never packed. This is strictly worse than the loud `⚠️  NO DRUMS` banner the
  same file already prints for the "index exists but 0 samples resolved" and "packing
  raised" cases two branches away — an entirely-missing index is treated more quietly than
  a partially-broken one.
- **Evidence**:
  ```python
  # main.py:597-616 (run_export) — no else branch
  if dpcm_index_path.exists():
      ...
      with open(args.output, 'a') as f:
          f.write("\n\n" + packer.generate_assembly())
  # (nothing here if the index is missing — dpcm_pack_warning stays None)

  # main.py:1034-1035 (run_full_pipeline) — has an else branch
  else:
      print("  ℹ️ No dpcm_index.json found, skipping DPCM packing.")
  ```
- **Impact**: Confined to the step-by-step `export` subcommand's `.asm` output (the
  documented `parse → map → frames → detect-patterns → export → prepare → compile`
  workflow from CLAUDE.md). The shipped `dpcm_index.json` normally lives at the repo root,
  so a user running `export` from that directory is unaffected; the gap bites when `export`
  is run from a different working directory, in a fresh checkout missing the index, or from
  a script/CI job with a different cwd — in which case a song with percussion silently loses
  its drums in the exported ASM with **no warning of any kind**, not even the info-level
  line the pipeline path gives. Because this only affects messaging (not the ROM byte
  content itself — the ASM genuinely has no DPCM data either way once the index is absent)
  it stays LOW/tech-debt as `#380` already classifies it, not a data-corruption bug; the
  escalation risk is that any future divergence between the two copies (already demonstrated
  once, per `#380`'s own evidence) could next drift into an actual behavioral difference,
  not just a messaging one.
- **Related**: `#380` (TD-28, tracks the duplication root cause and this exact print-line
  asymmetry); `#123` (loud DPCM warnings for the two adjacent branches, already fixed);
  `#381` (the sibling legacy-mapping guard gap in the same function).
- **Suggested Fix**: As `#380` already recommends — extract a single
  `pack_dpcm_into_asm(frames, asm_path, *, verbose=False) -> Optional[str]` helper used by
  both `run_export` and `run_full_pipeline`, including the missing-index `else:` info print,
  so the two call sites can no longer disagree on what gets reported.

---

## Dimensions confirmed clean (no findings, new or existing)

- **D2 Malformed-Input Resilience**: both `mido.MidiFile` sites guarded → `InvalidMIDIError`;
  no other unguarded `mido.MidiFile`/`open()`/`read_text()` on a user-supplied path found.
- **D3 Subprocess/CC65 Safety**: argv lists throughout; `check_toolchain()` gates every
  build entry point; returncode+stderr checked; timeouts present at every `subprocess.run`
  call in `compiler/cc65_wrapper.py` and `compiler/compiler.py`; the one `shell=True` is
  fed only by a verified static constant (no mapper overrides it).
- **D4 Unsafe Deserialization**: no `eval`/`exec`/`yaml.load`/`pickle.load`/`os.system`
  anywhere in the repo outside `venv/`; config loading uses `yaml.safe_load`.
- **D5 JSON-Intermediate Guards**: `load_json_stage` covers all four inter-stage
  subcommand reads; no bare `json.loads(...).read_text()` remains on a user-supplied path.
- **D6 File/Resource Handling & Temp Cleanup**: no bare `open()` without `with` in any
  in-scope module; `TemporaryDirectory` auto-cleans; backup create/delete/restore contract
  correct and centralized in one `finally` block per entry point.
- **D7 Exception-Type Discipline**: typed hierarchy (`core/exceptions.py`) used
  consistently; `config_manager.py`'s `save()`/`validate()`/`_load_from_file()` all raise
  typed exceptions, no bare `ValueError`; no bare `except:` anywhere.
- **D8 Partial-Output-on-Failure**: ROM is only ever copied to the final path after a
  successful in-temp-dir build; the one known non-atomic write (`export`'s `.asm`) is
  already tracked as `#385`.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_SAFETY_2026-08-05.md
```
