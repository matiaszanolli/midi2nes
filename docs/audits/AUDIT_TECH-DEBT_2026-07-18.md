# Tech-Debt Audit — MIDI2NES — 2026-07-18

Scope: maintainability debt across the Python codebase (duplication, dead code, stale docs,
stale markers, stubs, magic numbers, error-handling debt, module/function size). Correctness
is out of scope (owned by the subsystem audits).

This run supersedes the earlier 2026-07-18 report whose findings (TD-23/#319, TD-24/#320,
TD-25/#321) have since been fixed on the current branch (commit `8a2457a`). Those three are
re-verified as resolved below and are **not** re-reported.

Repo state at audit: `master`, HEAD `308d712`, version `0.5.0-dev`.

---

## Summary

### New findings by dimension

| Dimension | New | IDs |
|-----------|-----|-----|
| 1 — Logic Duplication | 0 | — |
| 2 — Dead Code & Cruft | 2 | TD-26, TD-27 |
| 3 — Stale Documentation | 0 | — |
| 4 — Stale Markers | 0 | — |
| 5 — Stubs & Placeholders | 0 | — |
| 6 — Magic Numbers | 0 | — |
| 7 — Error-Handling Debt | 0 | — |
| 8 — Module/Function Size | 1 (update) | TD-11 growth (Existing #136) |

**Severity totals (new findings):** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 3.

The tree is heavily audited; most standing tech debt is already tracked as open issues
(TD-07/#134, TD-08/#137, TD-10/#135, TD-11/#136, TD-19/#229, TD-22/#266, P-04/#112,
NH-28/#203). This run confirms those, records two tree-state changes that make open issues
partially stale (P-04/#112 and TD-10/#135 are now resolved-in-tree), and adds two genuinely
new LOW dead-code findings plus a size-growth flag on the existing monolith issue.

### Three highest-leverage cleanups

1. **Retire or wire up the dead assembly scaffolding** (`src/*.s`, `tracker/parser.py`) —
   TD-26 + TD-27. Two independent chunks of code are alive only in tests or in nothing at
   all, both tied to abandoned/future paths (old parser; unimplemented NSF). They are prime
   drift/rot candidates and confuse newcomers about what the real pipeline uses.
2. **Split the two growing monoliths** — `main.py` (1535 lines) and
   `exporter/exporter_ca65.py` (1321 lines), TD-11/#136. Both have grown since the issue was
   filed; the debt is compounding.
3. **Close the now-stale open issues** — P-04/#112 and TD-10/#135 are already fixed in the
   tree but still open with descriptions that no longer match the code; they should be closed
   or their descriptions corrected so the backlog stays trustworthy.

---

## Verification of just-fixed items (no regression)

- **#319 / TD-23** (velocity→volume dedup): `velocity_to_volume` is now a single helper at
  `nes/envelope_processor.py:4`, imported and used at all sites in `nes/emulator_core.py`
  (lines 4, 112, 118, 161). No second copy of the power curve remains. **Confirmed fixed.**
- **#320 / TD-24** (dead locals in drum mapper): `pattern_instances` and `velocity_ratio`
  are gone from `dpcm_sampler/enhanced_drum_mapper.py`; the unused `defaultdict` import was
  also removed. **Confirmed fixed.**
- **#321 / TD-25** (redundant `tempfile` import): `benchmarks/performance_suite.py` now
  imports `tempfile` only once (line 11); `main.py` imports it once (line 4). No shadowed
  re-import remains. **Confirmed fixed.**

Prior-fixed dedup checks from the skill also re-verified clean: the copy-pasted
`_find_pattern_matches` (TD-03/#131) has not reappeared; the duplicate MIDI-note→note-name
converter (TD-07/#134) has a single home at `exporter/exporter_famistudio.py:164`
(`exporter/exporter_ca65.py` only has the unrelated `midi_note_to_timer_value` at line 42);
the repo root holds only `main.py`, `constants.py`, `validate_rom.py` (TD-04/#132, TD-05/#133
stay fixed); no checked-in `.nes`/`.log` build artifacts.

---

## Findings

### TD-26: `tracker/parser.py` (old full parser) is production-dead — imported only by tests
- **Severity**: LOW
- **Dimension**: 2 — Dead Code & Cruft (overlaps 1 — the "two parsers drifting" hot spot)
- **Location**: `tracker/parser.py` (whole module; `parse_midi_to_frames` at line 10)
- **Status**: NEW (related to Existing: #112 / P-04, which is now resolved-in-tree)
- **Description**: No production code path imports `tracker.parser` anymore. `main.py` only
  imports `from tracker.parser_fast import parse_midi_to_frames` (lines 97, 810). The old
  full parser's `parse_midi_to_frames` is referenced exclusively by three tests
  (`tests/test_midi_parser_integration.py:5`, `tests/test_integration.py:6`,
  `tests/test_pattern_integration.py:6`). It is not dead-dead (tests keep it importable) but
  it is dead to the shipping pipeline, so it silently drifts from `parser_fast.py` with
  nothing but those tests guarding parity. `_audit-common.md` and CLAUDE.md still describe it
  as "the older full parser," implying it may be a live alternative — it is not.
- **Evidence**:
  ```
  $ grep -rn "tracker.parser import" --include='*.py' . | grep -v parser_fast | grep -v tests/
  (no production hits)
  $ grep -rn "from tracker.parser import" tests/
  tests/test_midi_parser_integration.py:5
  tests/test_integration.py:6
  tests/test_pattern_integration.py:6
  ```
- **Impact**: Two parsers to maintain; the test-only one can rot or diverge without affecting
  any ROM, and its continued presence in docs misleads readers about the real front-end. No
  runtime risk. Blast radius: developer time / test suite only.
- **Related**: P-04/#112 (unused top-level import of the old parser — see Notes: resolved in
  tree). Dimension 1 "two parsers drifting" hot spot.
- **Suggested Fix**: Decide the module's fate explicitly. Either (a) delete `tracker/parser.py`
  and migrate its three tests to `parser_fast` (if `parser_fast` covers their assertions), or
  (b) keep it but add a module docstring stating it is a test-only reference implementation
  and update the CLAUDE.md / `_audit-common.md` descriptions to say it is not on any pipeline
  path.

### TD-27: `src/` assembly driver directory is unreferenced dead scaffolding
- **Severity**: LOW
- **Dimension**: 2 — Dead Code & Cruft
- **Location**: `src/music_driver.s`, `src/nsf_main_driver.s`, `src/nes.inc`
- **Status**: NEW (related to unimplemented NSF exporter #81; sibling to NH-28/#203 dead ASM)
- **Description**: The `src/` directory holds hand-written NSF-oriented player assembly
  (`music_driver.s` header: "NSF-compatible music player logic") plus a shared `nes.inc`.
  Nothing in the codebase references them: no Python module, no `.cfg`/`.sh` build script, and
  `NESProjectBuilder` emits its own inline templates (`audio_engine.asm`, `mmc3_init.asm`) via
  `nes/project_builder.py` rather than copying from `src/`. The NSF export path these files
  target is itself unimplemented — `exporter/exporter_nsf.py` raises `NotImplementedError`
  (#81). Last touched 2025-08-10; effectively orphaned scaffolding.
- **Evidence**:
  ```
  $ git ls-files src/
  src/music_driver.s
  src/nes.inc
  src/nsf_main_driver.s
  $ grep -rn "music_driver\|nsf_main_driver" --include='*.py' .   # no hits
  $ git log -1 --format='%h %ad' --date=short -- src/
  149a95f 2025-08-10
  ```
- **Impact**: Dead weight that reads as if it were part of the build. A newcomer editing the
  audio engine may waste time in `src/*.s` believing it is live. No runtime risk. Blast
  radius: developer confusion only.
- **Related**: #81 (NSF export not implemented), NH-28/#203 (`nes/mmc3_init.asm` dead ASM —
  same "orphaned assembly file" category).
- **Suggested Fix**: Either delete `src/` (git history preserves it), or if it is intended as
  the seed for the future real NSF engine, move it under a clearly-marked location (e.g.
  `docs/` or a `future/`/`scaffolding/` prefix) and reference it from the #81 tracking issue so
  its purpose is discoverable.

### TD-11 (update): the two monoliths have grown further since #136 was filed
- **Severity**: LOW
- **Dimension**: 8 — Module/Function Size & Structure
- **Location**: `main.py` (1535 lines); `exporter/exporter_ca65.py` (1321 lines)
- **Status**: Existing: #136 — reported here because the skill's Dimension 8 directs flagging
  further growth.
- **Description**: `main.py` was ~1480 lines when #136 was filed and is now **1535** (+55);
  `exporter/exporter_ca65.py` was ~1290 and is now **1321** (+31). The structural debt #136
  describes — argparse dispatch layered with hand-rolled pre-subcommand argv scanning, the
  ~330-line inline `run_full_pipeline`, and the ~700-line inline `export_direct_frames` —
  remains and is accreting rather than shrinking.
- **Evidence**:
  ```
  $ wc -l main.py exporter/exporter_ca65.py
  1535 main.py
  1321 exporter/exporter_ca65.py
  ```
- **Impact**: Compounding change-cost in the two most central modules. No runtime effect.
- **Related**: TD-11/#136 (open).
- **Suggested Fix**: Prioritize the #136 split. Concretely: lift per-subcommand handlers and
  the global-flag pre-scan out of `main.py` into a `cli/` package, and extract the per-channel
  playback-routine emitters (pulse/triangle/noise/DPCM) out of `export_direct_frames` into
  helper methods.

---

## Notes — open issues that are now stale (recommend closing / correcting)

These are not new findings; they are backlog-hygiene observations from re-reading the tree.

- **P-04 / #112 — resolved in tree.** The issue reports an unused top-level import of the old
  full parser in `main.py`. `main.py` no longer imports `tracker.parser` at all (only
  `parser_fast`, lines 97 & 810). The specific import is gone; the deeper module-level state
  is captured as TD-26 above. Recommend closing #112 and tracking the residue via TD-26.
- **TD-10 / #135 — partially resolved in tree.** The issue reports a **bare** `except:` at
  `utils/profiling.py:120` that swallows `KeyboardInterrupt`/`SystemExit`. The clause is now
  `except Exception:` (narrowed by commit `ed5900d`), so it no longer swallows
  `KeyboardInterrupt`/`SystemExit`. A broad `except Exception: break` that silently drops the
  real profiling error still remains, but the specific hazard the issue names is fixed.
  Recommend updating or closing #135.
- **TD-08 / #137 — still open, unchanged.** The stale DPCM `.incbin` TODO is still the sole
  TODO/FIXME/HACK/XXX in non-test source, now at `exporter/exporter_ca65.py:991` (line drift
  from the 988 the skill cites). Real work is done by `dpcm_sampler/dpcm_packer.py`. Still
  stale, still LOW.
- **TD-07/#134, TD-19/#229, TD-22/#266, NH-28/#203** — re-verified still open and accurate.

One additional broad-catch site worth noting (not filed as a finding — it is defensible as a
health-check wrapper that must not crash): `debug/__init__.py:54` uses `except Exception:
return False`. Acceptable design, mentioned only for completeness of the error-handling scan.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_TECH-DEBT_2026-07-18.md
```
