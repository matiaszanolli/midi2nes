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

### Song banks → ROM
`SongBank` (`nes/song_bank.py`) is currently **storage/analysis only**: the
`song add|list|remove` subcommands manage a JSON bank but nothing compiles a
bank into a `.nes`. Closing the gap (issue #30 / F-13):
- [ ] `song build <bank> <out.nes>` route through the project builder + compiler.
- [ ] Real multi-song ROM layout: per-song sequence pointers, a song table, and
      an in-ROM song-select entry point (today `prepare_multi_song_project` /
      `add_song_bank` are placeholders that fall back to single-song).

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
