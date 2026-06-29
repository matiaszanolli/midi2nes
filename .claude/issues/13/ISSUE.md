# F-05: map --config / --dpcm-index are declared but ignored

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md

p_map declares --config and --dpcm-index but run_map hardcodes dpcm_index_path =
'dpcm_index.json' and never reads args.config/args.dpcm_index. run_full_pipeline also
hardcodes dpcm_index.json. A custom --dpcm-index is silently ignored.

## Suggested Fix
Honor args.dpcm_index or 'dpcm_index.json' and pass args.config into the mapper, or drop
the unused options.
