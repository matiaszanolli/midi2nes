**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-08-24.md

## Description
`run_full_pipeline`'s legacy (non-arranger) mapping step hard-codes `dpcm_index_path = 'dpcm_index.json'` and, on a missing file, prints the same actionable hint `run_map` prints (`main.py:1492-1495`) — but `--dpcm-index` is never declared on the top-level parser (no entry in the global-flag whitelist at `main.py:1810-1862`, no `dpcm_index` attribute on `SimpleArgs` at `main.py:1879-1893`), so the suggested remedy fails immediately with "Unknown option: --dpcm-index" if the user actually follows it.

`run_map`'s equivalent message (`main.py:280-282`) is correct, since the `map` subcommand genuinely declares `--dpcm-index`. The default pipeline's copy of the message was pasted from there without accounting for the different flag surface.

## Evidence
`python main.py --dpcm-index custom_index.json song.mid` → `Error: Unknown option: --dpcm-index`. Message source: `main.py:1492-1495`, copy-pasted from `run_map`'s guard at `main.py:280-282` where it's accurate.

## Impact
Diagnostic-only; sends a user down a dead end instead of "restore `dpcm_index.json`" or "use `midi2nes map ... --dpcm-index <path>`".

## Related
#381/SAFE-2026-07-19-1 (introduced the copy-pasted message), #256/D-18 (original `run_map` guard).

## Suggested Fix
Either add a top-level `--dpcm-index` flag threaded through `SimpleArgs`/`run_full_pipeline`, or reword the default-pipeline message to not suggest a flag the default path doesn't accept.

## Completeness Checks
- [ ] **SIBLING**: `run_map`'s message is correct and should be the reference; the default-pipeline copy needs to either match the real flag surface or be reworded
- [ ] **TESTS**: A regression test could assert the default pipeline's missing-index message doesn't suggest a flag `SimpleArgs`/the top-level parser doesn't actually accept
