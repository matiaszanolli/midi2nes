# TD-28: Duplicated DPCM-packing block across main.py's two export paths (already drifting)

Issue: #380 | Labels: low, tech-debt, enhancement

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH-DEBT_2026-07-19.md

## Description

The DPCM sample-packing sequence is copy-pasted into both the `export` subcommand (`run_export`) and the full pipeline (`run_full_pipeline`). Both blocks do the same thing in the same order: import `DpcmPacker` + `load_dpcm_index_into_packer` + `get_dpcm_sample_ids_from_frames`, instantiate a `DpcmPacker`, check `Path('dpcm_index.json').exists()`, `json.load` it, compute `sample_ids = get_dpcm_sample_ids_from_frames(frames)`, call `load_dpcm_index_into_packer`, append `packer.generate_assembly()` to the ASM, and wrap the whole thing in a broad `except Exception` that sets the same `dpcm_pack_warning` "NO drums" message (both carry the identical #123 comment).

This is a live-path duplication: the default `main.py input.mid out.nes` run hits the pipeline copy; `export` hits the other.

**Location:** `main.py:625-668` (`run_export`) and `main.py:1034-1084` (`run_full_pipeline`)

## Evidence

The two blocks have **already diverged**, demonstrating the drift risk is real, not hypothetical:

- Pipeline copy passes `verbose=args.verbose` to `load_dpcm_index_into_packer` (`main.py:1057-1059`); the export copy does not (`main.py:651-652`).
- Pipeline copy prints packed-count / "no samples referenced" / "no dpcm_index.json" status lines (`main.py:1067-1078`); the export copy prints none of them — a bug fix or message change to one path will silently miss the other.

```
$ grep -n "load_dpcm_index_into_packer(" main.py
651:  loaded_samples, _ = load_dpcm_index_into_packer(
      packer, dpcm_index, dpcm_index_path, sample_ids=sample_ids)          # export: no verbose=
1057: loaded_samples, _ = load_dpcm_index_into_packer(
      packer, dpcm_index, dpcm_index_path, verbose=args.verbose, ...)       # pipeline: has verbose=
```

## Impact

Two copies of the drum-packing logic to keep in sync. A future fix (e.g. a new dpcm_index failure mode, or a message/format change) applied to one path but not the other ships an inconsistency; the existing `verbose`/print divergence is a mild instance already. No runtime break today. Blast radius: developer time + risk of one-sided fixes on the DPCM export path.

## Related

- TD-11 / #136 (main.py monolith — extracting this helper shrinks it)
- #256 / #123 (the DPCM index-resolution issues that seeded both blocks)

## Suggested Fix

Extract a single helper, e.g. `pack_dpcm_into_asm(frames, asm_path, *, verbose=False) -> Optional[str]` returning the warning string (or `None`), and call it from both sites. Keep the per-path *presentation* (banner lines / step numbers) at the call sites, but move the pack logic and the broad-except warning into the one helper so both paths behave identically.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Both call sites (`run_export` and `run_full_pipeline`) route through the single extracted helper
- [ ] **TESTS**: A regression test pins the extracted helper's behavior (warning-on-failure, verbose passthrough, empty/absent dpcm_index.json)
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
