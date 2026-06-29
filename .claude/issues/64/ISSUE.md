# D-01: Shipped DPCM index filenames never resolve — all percussion silent

Issue: #64 — https://github.com/matiaszanolli/midi2nes/issues/64
Labels: bug, critical, dpcm
Filed from: AUDIT_DPCM_2026-06-29.md

---

**Severity:** CRITICAL · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-06-29.md

## Description
`generate_dpcm_index` writes `filename` as `rel_path` *relative to the scanned `dmc_folder`* (`dpcm_sampler/generate_dpcm_index.py:12` `rel_path = os.path.relpath(full_path, dmc_folder)`), so the shipped index stores bare names like `(Konami, Contra Force) Hit 1.dmc`. Both packer call sites build `Path(sample['filename'])` and test `sample_path.exists()` **relative to the current working directory** — never re-joining the `dmc/` root. The real files live under `dmc/`, so the bare names resolve to nothing.

## Location
- `dpcm_sampler/generate_dpcm_index.py:12-17`
- `main.py:263-265` and `main.py:547-557`

## Evidence
```
# repo state, run from repo root:
resolve from cwd:   0 / 1923
resolve from dmc/:  1923 / 1923
```
`main.py:264` `if sample_path.exists():` is False for all 1923 entries → `add_sample` is never called → `packer.banks` empty → `generate_assembly` emits the dummy tables (`dpcm_packer.py:96-101`: `dpcm_bank_table: .byte $00`, etc.). Confirmed: `dpcm_index.json` has 1923 entries.

## Impact
Every ROM built through the default pipeline or `export` packs **zero** DPCM samples. The engine's `play_dpcm`/`@write_dpcm` then index a 1-byte dummy table for every drum hit, so percussion is silent or garbage on every song with drums. Blast radius: all DPCM output, every pipeline run.

## Related
D-02 (id mismatch compounds), prior NH-01 (now fixed) assumed tables were populated.

## Suggested Fix
Store `filename` relative to a known DPCM root and have both packer sites resolve `Path(dpcm_root) / sample['filename']`, or write absolute paths in `generate_dpcm_index`. Add a non-fatal warning when `loaded_samples == 0` but the index was non-empty.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (both packer call sites in main.py)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
