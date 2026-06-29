**Severity:** HIGH · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-06-29.md

`--format nsf` dispatches on an impossible string and silently does nothing.

## Description
argparse restricts `--format` to `nsf` or `ca65`. `run_export` checks `if args.format == "nsftxt":` for the NSF branch and `elif args.format == "ca65":` for CA65. `"nsftxt"` is not an allowed choice, so the NSF branch is unreachable; `--format nsf` matches neither branch and `run_export` returns having written nothing — no NSF file, no error.

## Location
`main.py:222` (`if args.format == "nsftxt":`) vs `main.py:705` (`p_export.add_argument('--format', choices=['nsf', 'ca65'], default='ca65')`).

## Evidence
`main.py:222-234` — the two branches are `"nsftxt"` and `"ca65"`; there is no `"nsf"` branch. argparse rejects any other value before dispatch.

## Impact
A documented/advertised output format (`nsf`) produces no output and no diagnostic for the `export` subcommand. User-facing silent no-op.

## Related
EXP-05 (the NSF exporter the branch would have called is itself non-functional).

## Suggested Fix
Change the branch to `if args.format == "nsf":` (and fix the underlying NSF exporter per EXP-05), or drop `nsf` from `choices` until NSF is real.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON/CLI shape changes, the consumer was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related dispatch branches
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
