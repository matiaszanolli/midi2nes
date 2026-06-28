# F-05: map --config / --dpcm-index are declared but ignored

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md
**Issue:** #13

## Description
p_map declares --config and --dpcm-index (main.py:519-520) but run_map hardcodes dpcm_index_path = 'dpcm_index.json' (main.py:42) and never reads args.config or args.dpcm_index. A user pointing --dpcm-index custom.json gets the default file silently.

## Evidence
main.py:42 hardcode; no reference to args.config/args.dpcm_index in run_map. Flags declared 519-520.

## Impact
Misleading interface; custom DPCM index silently ignored, drum mapping differs from request. Recoverable → MEDIUM.

## Related
F-03

## Suggested Fix
Honor args.dpcm_index or 'dpcm_index.json' and pass args.config into the mapper, or drop the unused options.

**Location:** `main.py:40-44` (body) vs `main.py:519-520` (declared)
