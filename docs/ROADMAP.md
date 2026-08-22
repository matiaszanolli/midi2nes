# MIDI2NES Roadmap

**Current version:** `v0.5.0-dev` — see [HISTORY.md](../HISTORY.md) for what
shipped in each release and [MEMORY.md](../MEMORY.md) for durable project notes.

This is the authoritative forward-looking plan. `docs/WORK_PLAN_1.0.0.md` is an
archived v0.3.5-era snapshot (#226/TD-17) — superseded by this document.

The pipeline is fully operational end-to-end (MIDI → playable NES ROM). The road
to **v1.0.0** is about polish, robustness, broader format/hardware coverage, and
documentation — not core functionality.

---

## ✅ Recently completed (v0.5.0 — Macro Engine & Arranger)

- **MMC3 macro-driven bytecode engine** — compressed, in-ROM bytecode
  interpreter replacing static frame dumps.
- **DPCM sample support** — FFD sample packing, automatic bank allocation, DMC
  level handling.
- **Arranger mode (`--arranger`)** — role analysis, GM mapping, smart channel
  allocation, hardware arpeggiation for polyphony.
- **On-screen debug overlay (`--debug`)** — real-time APU/frame/pointer
  diagnostics in the ROM.
- **Logarithmic velocity → volume scaling** across pulse/noise/macro paths.
- **Enhanced tempo mapping** with sub-frame precision and frame alignment.
- **Audit tooling** — shared protocol + audit skills across all subsystems.

## ✅ Earlier foundations (v0.4.0)

120× faster parsing, multi-core pattern detection (up to ~95× compression),
MMC1 128KB ROMs, version management, YAML config system, benchmarking
infrastructure, and the `debug/` diagnostic suite.

---

## 🔜 Next up — Stabilization (toward v0.6.0)

### Code quality & tooling
- [ ] Formatter + linter (Black / Flake8 or Ruff) and pre-commit hooks.
- [ ] Structured logging and user-friendly, actionable error messages.
- [ ] CI: run the full test suite + performance regression checks on push.

### Correctness & robustness
- [ ] Resolve audit findings (NES hardware accuracy, exporter round-trips,
      pipeline data contracts, DPCM constraints).
- [ ] Strengthen input validation and subprocess/deserialization safety.
- [ ] Expand the test MIDI library and add fuzzing for edge cases.
- [ ] Reconcile stale docs (`docs/legacy/`, CLAUDE.md mapper notes) with the
      MMC3 reality; bump `midi2nes/__version__.py` to match.

### Format & hardware coverage
- [ ] NSF export hardening (header validation, NSF 2.0 consideration).
- [ ] FamiStudio export fidelity (effects, pattern organization).
- [ ] Mapper coverage and auto-selection tuning (NROM/MMC1/MMC3).

### Song banks → ROM (#30/F-13) — ✅ v1 shipped, follow-ups remain
`song build <bank.json> <out.nes>` compiles a `SongBank` into a real
multi-song "jukebox" ROM: `SongBank` now records each song's source MIDI
path (`song add`), and `song build` re-parses/maps every song, exports a
combined MMC3 macro-bytecode `music.asm` with a real song table (per-song
sequence pointers + a per-song instrument-table pointer, continuing the
shared 60-bank pool fresh per song), and `nes/project_builder.py` wires in
runtime song-switching: auto-advance when a song ends, and a Start-button
press skips to the next song immediately (both wrap around). The engine
additions are `.ifdef JUKEBOX_BUILD`-gated in `nes/audio_engine.asm`, so
ordinary single-song builds are byte-identical to before this shipped.

v1 deliberately narrowed scope — tracked as follow-ups, not silent gaps:
- [ ] DPCM/drums in jukebox builds. `song build` currently rejects any song
      with real DPCM events — DPCM sample banks and sequence banks already
      share one 60-bank pool for a *single* song; extending that sharing
      safely across N songs is unsolved.
- [ ] `--mapper` choice for `song build` (always MMC3 today — the song-table/
      bank-pool mechanism is bytecode-engine-specific and MMC3-only).
- [ ] `--debug` overlay support for jukebox builds.
- [ ] A visual song-select screen. Today's Start-skip is audible-only; no
      PPU/tile-rendering code exists anywhere in this codebase yet.
- **51-song hard limit.** The engine's `song_table` is indexed
  `song_index*5+channel` with 8-bit accumulator/Y-register math
  (`load_song_streams_indexed` in `nes/audio_engine.asm`), which caps at
  index 255 — `export_song_bank_bytecode` raises `ValueError` past 51 songs
  rather than let the index wrap and silently corrupt playback (#426).

## 🧭 Mid-term (v0.7.0–v0.9.0)

- [ ] Musical analysis tooling (chord/tempo complexity, instrumentation hints).
- [ ] Pattern/compression visualization and quality metrics.
- [ ] Preview/playback path (NES-accurate synthesis, A/B comparison).
- [ ] Comprehensive user manual, tutorials, and API/architecture docs.
- [ ] Optional GUI (web drag-and-drop or desktop app).

## 🏁 v1.0.0 — Production readiness

- [ ] Packaging: pip (and optionally conda / Docker) distribution.
- [ ] Stress/stability testing and graceful degradation on edge cases.
- [ ] Cross-platform verification (Windows, macOS, Linux).
- [ ] Documentation finalized; release notes and migration guides.

### Target success metrics
- Process multi-MB MIDI files in well under 30 s; peak memory < 512 MB typical.
- Maintain ≥ 95% test coverage with zero performance regressions vs v0.4.0.
- Full APU feature coverage; CA65 / NSF / FamiStudio all first-class.
