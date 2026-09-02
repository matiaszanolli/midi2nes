# TD-33: SongBank's virtual capacity model still disconnected from the real ROM capacity song build uses

Labels: bug, low, tech-debt, documentation

**Severity:** LOW · **Domain:** tech-debt, documentation · **Source:** AUDIT_TECH_DEBT_2026-08-21.md

**Status:** Carried from 2026-08-07 (TD-33) — downgraded from MEDIUM (the disconnect is now explicitly documented, and the real build path catches overflow) — partially addressed (class docstring rewritten in `8ea7ac3` now states the two models are "independent of — and not reconciled with" each other), never filed as a GitHub issue — filing now.

## Description
`song add` still accepts/rejects songs against a 16KB×8 virtual-bank model sized off raw MIDI event counts, while `song build` builds against emitted bytecode vs the MMC3 pool — so bank-level acceptance guarantees nothing about buildability. Since the prior report the docstring honestly documents this, but the code paths remain unreconciled.

## Evidence
`nes/song_bank.py:53-54` — `self.max_bank_size = 16384` / `self.total_banks = 8` — vs `main.py:1007` (`check_mapper_capacity`) which validates against the real MMC3 512KB/60-bank model. Docstring at `nes/song_bank.py:30-49` (confirmed present, states the disconnect); the allocator fields below it are unchanged.

## Impact
A user can fill a bank that later fails at `song build` (clear error, late feedback). The runtime-cost angle (overflow detected only after all songs parse) is PERF-B-04's finding.

## Suggested Fix
Either drop the virtual model (accept everything at `add`, size at `build`) or make `add_song` estimate against the real exporter-byte model; the docstring's pointer makes clear which model must win.

## Related
PERF-B-04 (2026-08-21, if/when filed), docs/ROADMAP.md follow-ups list. TD-34 (docstring fix, already CLOSED via `8ea7ac3`).

## Completeness Checks
- [ ] **CONTRACT**: If `add_song`'s acceptance model changes, `song build`'s real capacity check stays the sole source of truth for buildability
- [ ] **DOC**: `nes/song_bank.py`'s docstring is updated again once the models are reconciled (currently documents the gap, not a fix)

