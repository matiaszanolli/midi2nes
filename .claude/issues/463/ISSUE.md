# TD-43: audit-tech-debt SKILL.md prose is stale — describes fixed #135 as still-open and understates exporter_ca65.py's size by 240 lines

- **Issue**: #463

**Severity:** LOW · **Domain:** tech-debt, documentation · **Source:** AUDIT_TECH_DEBT_2026-08-21.md

**Status:** NEW — `/audit-sync` candidate

## Description
Two claims in `.claude/commands/audit-tech-debt/SKILL.md` no longer match master:

1. "A concrete, still-open instance: `utils/profiling.py` has a bare `except:` clause (line 120) … (TD-10/#135)". #135 is CLOSED and the fix **did** land on master: `grep -n "except" utils/profiling.py` shows no bare `except:` anywhere — only narrow `(psutil.NoSuchProcess, psutil.AccessDenied)` and a commented `except Exception` (`:139`,`:145`) that explicitly lets `KeyboardInterrupt`/`SystemExit` propagate; the module docstring (`:19`) refers to the bare except in the past tense.
2. "`exporter_ca65.py` is now ~1445 lines total" — the file is 1685 lines. The growth is the jukebox feature (`_build_song_bytecode` + `export_song_bank_bytecode`, added in `c864426`/`8ea7ac3`), not a re-inlining regression, but the number sends the next auditor chasing a phantom 240-line change.

## Evidence
```
$ grep -n "except" utils/profiling.py
utils/profiling.py:139:            except (psutil.NoSuchProcess, psutil.AccessDenied):
utils/profiling.py:145:            except Exception:
(no bare `except:`)

$ wc -l exporter/exporter_ca65.py
1685 exporter/exporter_ca65.py
```
`.claude/commands/audit-tech-debt/SKILL.md:116-118` (Dimension 7 text) and `:130` ("~1445 lines total").

## Impact
Future tech-debt audits either re-report a fixed bug or burn time disproving stale prose. No runtime impact.

## Suggested Fix
Run `/audit-sync` over `audit-tech-debt/SKILL.md`: rewrite the Dimension 7 example as a verify-the-fix note and refresh the Dimension 8 line counts (1685 for `exporter/exporter_ca65.py`, with the jukebox methods as the explanation).

## Related
Same stale-skill-prose class as TEMPO-2026-08-21-1, PAT-2026-08-21-7, and the arranger/dpcm/performance drift noted by sibling 2026-08-21 reports — those cover *their* skill files; this finding covers only `audit-tech-debt/SKILL.md`. #135/TD-10.

## Completeness Checks
- [ ] **DOC**: `audit-tech-debt/SKILL.md`'s Dimension 7 and Dimension 8 prose match current master (via `/audit-sync`)
