# Issues 461, 462, 463, 464

All from `AUDIT_TECH_DEBT_2026-08-21.md`, domain: tech-debt (462/463 also documentation).
Severity: LOW (all four).

---

## #461 — TD-41: `nes/linker_mmc3.cfg` is an orphan and a stale 128KB-era snapshot

No code references it (`grep -rn linker_mmc3` across the tree finds nothing outside
audit-skill prose) — every mapper emits `nes.cfg` programmatically via
`generate_linker_config()`. It also fails the "deliberately-kept reference copy" test: it
describes a 128KB PRG layout, while `mappers/mmc3.py` generates a 512KB, 60-swap-bank
config — actively misleading as a reference.

**Suggested fix:** delete it (git history preserves it).

---

## #462 — TD-42: `CLAUDE.md` cites `PROJECT_STATUS.md`, which was deleted

`PROJECT_STATUS.md` was removed in commit `419885e` ("Codebase cleanup.") but CLAUDE.md's
Project Status section still points readers at it (`✅ Fully operational end-to-end
pipeline (see PROJECT_STATUS.md)`).

**Suggested fix:** drop the parenthetical or point it at `docs/ROADMAP.md` (current, "Song
banks → ROM … ✅ v1 shipped" matches the code).

---

## #463 — TD-43: `audit-tech-debt/SKILL.md` prose is stale

Two claims no longer match master:
1. Describes `utils/profiling.py`'s bare `except:` (line 120, #135/TD-10) as still-open —
   #135 is CLOSED and fixed; no bare `except:` remains, only narrow exception types and a
   comment explaining `KeyboardInterrupt`/`SystemExit` propagate.
2. Claims `exporter_ca65.py` is "~1445 lines total" — actual is 1685 lines (growth from the
   jukebox feature, `_build_song_bytecode`/`export_song_bank_bytecode`, not a regression).

**Suggested fix:** rewrite Dimension 7's example as a verify-the-fix note; refresh Dimension
8's line count to 1685 with the jukebox methods noted as the explanation.

---

## #464 — TD-44: `input.mid` — third-party copyrighted MIDI tracked at repo root, doesn't
match README's benchmarks

Tracked `input.mid` is a third-party sequenced song (track names: "Sequenced by Steven
Picken", "Edited by MaliceX", "(C) 2002-2003 Steven Picken"; 14 tracks, 31,146 bytes, file
mtime 2007). README's "Test Results (input.mid — 51KB, 15 tracks)" benchmark section
describes a DIFFERENT file — the tracked sample isn't even the documented baseline. No test
depends on the file existing (test references use the name only as a CLI-args placeholder).

**Suggested fix:** remove `input.mid` from tracking (deterministic synthetic fixtures per
#372/#373 already exist); update README's example section to reference a generated fixture,
or replace it with an original, license-clean demo MIDI whose stats match the README table.
