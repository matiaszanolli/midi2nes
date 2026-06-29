# F-01: export_tables_with_patterns ignores its references argument; patterns is only a boolean switch

**Severity:** HIGH · **Domain:** pipeline

export_tables_with_patterns never reads `references`; all bytes derive from `frames`.
`patterns` truthiness only selects direct vs macro-bytecode exporter. The ca65_references
build in run_full_pipeline is dead computation and the documented "export reads references"
contract is fiction.

## Suggested Fix (chosen: remove dead build + document)
Delete the dead ca65_references build; document that pattern detection is analysis-only and
the macro-bytecode dedup is the real ROM compression; references is not consumed.
