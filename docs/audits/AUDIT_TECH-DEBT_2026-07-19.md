# Tech-Debt Audit — MIDI2NES — 2026-07-19

Scope: maintainability debt across the Python codebase (duplication, dead code, stale docs,
stale markers, stubs, magic numbers, error-handling debt, module/function size). Correctness
is out of scope (owned by the subsystem audits).

Repo state at audit: `master`, HEAD `f30c420`, version `0.5.0-dev`.

This run follows the 2026-07-18 report (`AUDIT_TECH-DEBT_2026-07-18.md`). Since then a large
batch of fixes landed (commits through `f30c420`: #203, #229, #256, #262, #112, #115, #123,
#332–#345, and a docs cleanup). `nes/mmc3_init.asm` was deleted (NH-28/#203 fixed) and the
pattern detector was substantially refactored. This audit re-verifies the standing debt is
intact/unregressed and reports one genuinely new duplication finding plus the recurring
monolith-growth flag.

---

## Summary

### New findings by dimension

| Dimension | New | IDs |
|-----------|-----|-----|
| 1 — Logic Duplication | 1 | TD-28 |
| 2 — Dead Code & Cruft | 0 | — (TD-26/#346, TD-27/#347 remain open, unchanged) |
| 3 — Stale Documentation | 0 | — |
| 4 — Stale Markers | 0 | — (TD-08/#137 still the sole marker) |
| 5 — Stubs & Placeholders | 0 | — |
| 6 — Magic Numbers | 0 | — |
| 7 — Error-Handling Debt | 0 | — |
| 8 — Module/Function Size | 1 (update) | TD-11 growth (Existing #136) |

**Severity totals (findings in this report):** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 2
(1 NEW, 1 existing-update).

The tree remains heavily audited; nearly all standing tech debt is already tracked as open
issues (TD-08/#137, TD-11/#136, TD-26/#346, TD-27/#347, EXP-09/#302). The one new item is a
copy-pasted DPCM-packing block that has already begun to drift between main.py's two export
paths.

### Three highest-leverage cleanups

1. **De-duplicate the DPCM-packing block in `main.py`** (TD-28, NEW). The ~35-line
   "open dpcm_index.json → pack referenced samples → append to music.asm → warn on failure"
   sequence exists twice (`run_export` and `run_full_pipeline`) and the two copies have
   *already diverged* (the export copy omits `verbose=` and the success/info prints). Extract
   one `pack_dpcm_into_asm(...)` helper; this also directly shrinks the #136 monolith.
2. **Split the two growing monoliths** — `main.py` (now **1584** lines) and
   `exporter/exporter_ca65.py` (now **1341** lines), TD-11/#136. Both grew again since
   2026-07-18 (+49 / +20).
3. **Resolve the dead-scaffolding pair** — `tracker/parser.py` (TD-26/#346, test-only) and
   `src/*.s` (TD-27/#347, orphaned NSF assembly). Both are alive only in tests or in nothing;
   prime drift/rot candidates still open.

---

## Verification of prior-fixed items (no regression)

- **`_find_pattern_matches` split (TD-03/#131)** — intact. `tracker/pattern_detector.py`
  keeps the variation/transposition-aware `_find_pattern_matches` (line 324); the parallel
  module uses the O(n) `_collect_length_candidates` (line 437) now cleanly factored into
  `_collect_window_groups` + `_select_candidates_from_groups` (#332/PERF-12). Both detectors
  share `score_pattern` (`tracker/pattern_detector.py:41`). No copy-paste has reappeared. The
  heavy +233-line refactor of `pattern_detector_parallel.py` is well-documented and introduces
  no new duplication.
- **MIDI-note→note-name converter (TD-07/#134)** — single home confirmed:
  `exporter/exporter_famistudio.py:173` (`midi_note_to_famistudio`).
  `exporter/exporter_ca65.py` only has the unrelated `midi_note_to_timer_value` (line 42). No
  second copy.
- **Root scripts (TD-04/#132, TD-05/#133)** — repo root still holds only `main.py`,
  `constants.py`, `validate_rom.py`. No stray root script or duplicate `check_rom.py`
  reintroduced (the sole `check_rom.py` is the intended `debug/check_rom.py`).
- **`nes/mmc3_init.asm` (NH-28/#203)** — deleted. No live doc (`docs/*.md`, `CLAUDE.md`,
  `README.md`) references it; `nes/project_builder.py:98-103` even strips any stale
  `.include "mmc3_init.asm"` from hand-edited music.asm. No doc-rot introduced by the deletion.
- **Bare `except:` scan** — no bare `except:` in non-test source (only two remain, both in
  tests as documented regression fixtures). `utils/profiling.py` is now `except Exception:`
  (line 129), consistent with TD-10/#135's partial fix.

---

## Findings

### TD-28: Duplicated DPCM-packing block across main.py's two export paths (already drifting)
- **Severity**: LOW
- **Dimension**: 1 — Logic Duplication
- **Location**: `main.py:632-664` (`run_export`) and `main.py:1036-1088` (`run_full_pipeline`)
- **Status**: NEW
- **Description**: The DPCM sample-packing sequence is copy-pasted into both the `export`
  subcommand and the full pipeline. Both blocks do the same thing in the same order: import
  `DpcmPacker` + `load_dpcm_index_into_packer` + `get_dpcm_sample_ids_from_frames`, instantiate
  a `DpcmPacker`, check `Path('dpcm_index.json').exists()`, `json.load` it, compute
  `sample_ids = get_dpcm_sample_ids_from_frames(frames)`, call `load_dpcm_index_into_packer`,
  append `packer.generate_assembly()` to the ASM, and wrap the whole thing in a broad
  `except Exception` that sets the same `dpcm_pack_warning` "NO drums" message (both carry the
  identical #123 comment). This is exactly the "improve existing code, never duplicate" hot
  spot. It is also a live-path duplication (the default `main.py input.mid out.nes` run hits
  the pipeline copy; `export` hits the other).
- **Evidence**: The two blocks have **already diverged**, demonstrating the drift risk is real,
  not hypothetical:
  - Pipeline copy passes `verbose=args.verbose` to `load_dpcm_index_into_packer`
    (`main.py:1058`); the export copy does not (`main.py:651`).
  - Pipeline copy prints packed-count / "no samples referenced" / "no dpcm_index.json"
    status lines (`main.py:1067-1078`); the export copy prints none of them — a bug fix or
    message change to one path will silently miss the other.
  ```
  $ grep -n "load_dpcm_index_into_packer(" main.py
  651:  loaded_samples, _ = load_dpcm_index_into_packer(packer, dpcm_index, dpcm_index_path, sample_ids=sample_ids)
  1057: loaded_samples, _ = load_dpcm_index_into_packer(packer, dpcm_index, dpcm_index_path, verbose=args.verbose, sample_ids=sample_ids)
  ```
- **Impact**: Two copies of the drum-packing logic to keep in sync. A future fix (e.g. a new
  dpcm_index failure mode, or a message/format change) applied to one path but not the other
  ships an inconsistency; the existing `verbose`/print divergence is a mild instance already.
  No runtime break today. Blast radius: developer time + risk of one-sided fixes on the DPCM
  export path.
- **Related**: TD-11/#136 (main.py monolith — extracting this helper shrinks it); the DPCM
  index-resolution issues #256/#123 that seeded both blocks.
- **Suggested Fix**: Extract a single helper, e.g.
  `pack_dpcm_into_asm(frames, asm_path, *, verbose=False) -> Optional[str]` returning the
  warning string (or `None`), and call it from both sites. Keep the per-path *presentation*
  (banner lines / step numbers) at the call sites, but move the pack logic and the broad-except
  warning into the one helper so both paths behave identically.

### TD-11 (update): the two monoliths grew again since #136 / 2026-07-18
- **Severity**: LOW
- **Dimension**: 8 — Module/Function Size & Structure
- **Location**: `main.py` (1584 lines); `exporter/exporter_ca65.py` (1341 lines)
- **Status**: Existing: #136 — reported because Dimension 8 directs flagging further growth.
- **Description**: `main.py` was ~1480 when #136 was filed, 1535 on 2026-07-18, and is now
  **1584** (+49 since the last audit, +104 since the issue). `exporter/exporter_ca65.py` was
  ~1290 / 1321 and is now **1341** (+20 / +51). The structural debt #136 describes persists and
  is accreting:
  - `run_full_pipeline` (`main.py:819-1181`) is now ~362 lines (was ~330 at filing) —
    parse → map/arrange → frames → patterns → export → DPCM-pack → prepare → compile → validate
    inline. TD-28 above is one extractable sub-block of it.
  - `export_direct_frames` (`exporter/exporter_ca65.py:187-929`, next method `_compress_macro`
    at line 929) is ~742 lines (was ~738) emitting pitch tables + per-channel playback routines
    (pulse/triangle/noise/DPCM) + data tables inline.
- **Evidence**:
  ```
  $ wc -l main.py exporter/exporter_ca65.py
  1584 main.py
  1341 exporter/exporter_ca65.py
  ```
- **Impact**: Compounding change-cost in the two most central modules. No runtime effect.
- **Related**: TD-11/#136 (open); TD-28 (a concrete extractable slice of `run_full_pipeline`).
- **Suggested Fix**: Prioritize the #136 split. Concretely: (a) start with the low-risk TD-28
  helper extraction, (b) lift per-subcommand handlers + the global-flag pre-scan out of
  `main.py` into a `cli/` package, (c) extract the per-channel playback-routine emitters out of
  `export_direct_frames` into helper methods.

---

## Notes — open issues re-verified (backlog hygiene)

Not new findings; re-read from the tree for accuracy.

- **TD-08 / #137** — the stale DPCM `.incbin` TODO is still the **sole** TODO/FIXME/HACK/XXX in
  non-test source, at `exporter/exporter_ca65.py:991`. The real `.incbin` output is produced by
  `dpcm_sampler/dpcm_packer.py`'s `generate_assembly` and appended in `main.py` (the two TD-28
  blocks). Still stale, still LOW.
- **TD-26 / #346** — `tracker/parser.py` (old full parser) is still production-dead, imported
  only by 3 tests. It now imports `FRAME_RATE_HZ` from `constants` (line 4) like
  `parser_fast.py`, but remains off every pipeline path. Unchanged, still open.
- **TD-27 / #347** — `src/music_driver.s`, `src/nsf_main_driver.s`, `src/nes.inc` still present
  and still unreferenced by any Python/build script (NSF export path is unimplemented, #81).
  Unchanged, still open.
- **EXP-09 / #302** — `exporter/compression.py` `CompressionEngine` + `BaseExporter`
  compress/decompress helpers remain dead. Unchanged, still open.
- **TD-10 / #135** — `utils/profiling.py` bare `except:` is fixed to `except Exception:`
  (line 129); a broad `except Exception: break` remains but the named `KeyboardInterrupt`
  hazard is gone. Recommend updating/closing #135 (as flagged 2026-07-18).

`constants.py` (FRAME_RATE_HZ, FRAME_MS, PATTERN_MIN/MAX_LENGTH) is properly shared by
`main.py`, `tracker/parser_fast.py`, `tracker/tempo_map.py`, and `benchmarks/` — no magic-number
regression there. Stub scan clean: all `pass`/`NotImplementedError` sites are legitimate
(abstract `mappers/base.py`, `core/exceptions.py` exception bodies, the documented unimplemented
`exporter/exporter_nsf.py` #81).

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_TECH-DEBT_2026-07-19.md
```
