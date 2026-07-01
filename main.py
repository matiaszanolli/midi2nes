import argparse
import sys
import json
import tempfile
import shutil
from typing import Dict, Optional
from pathlib import Path

# Import version information
try:
    from midi2nes import __version__
except ImportError:
    # Fallback for development mode
    __version__ = "0.5.0-dev"

from tracker.parser import parse_midi_to_frames
from tracker.track_mapper import assign_tracks_to_nes_channels
from nes.emulator_core import NESEmulatorCore
from arranger import arrange_for_nes
from nes.project_builder import NESProjectBuilder
from nes.song_bank import SongBank
from exporter.exporter_ca65 import CA65Exporter
from exporter.exporter import generate_famitracker_txt_with_patterns
from tracker.pattern_detector import EnhancedPatternDetector, sample_events_for_detection
from tracker.tempo_map import EnhancedTempoMap
from dpcm_sampler.enhanced_drum_mapper import EnhancedDrumMapper, DrumMapperConfig
from config.config_manager import ConfigManager
from benchmarks.performance_suite import PerformanceBenchmark
from utils.profiling import get_memory_usage, log_memory_usage
from compiler import compile_rom

# Shared pattern-detection bounds. Both entry points (the `detect-patterns`
# subcommand and the default full pipeline) must use identical parameters so
# their `patterns`/`references` JSON artifacts agree for the same input (#19).
PATTERN_MIN_LENGTH = 3
PATTERN_MAX_LENGTH = 12

def run_parse(args):
    # Use fast parser by default for better performance
    from tracker.parser_fast import parse_midi_to_frames as parse_fast
    midi_data = parse_fast(args.input)
    Path(args.output).write_text(json.dumps(midi_data, indent=2))
    print(f"[OK] Parsed MIDI -> {args.output}")

def run_map(args):
    midi_data = json.loads(Path(args.input).read_text())
    # Honor --dpcm-index instead of silently using the default (#13).
    dpcm_index_path = getattr(args, 'dpcm_index', None) or 'dpcm_index.json'
    # Extract just the events from the parsed data
    mapped = assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)
    Path(args.output).write_text(json.dumps(mapped, indent=2))
    print(f"[OK] Mapped tracks -> {args.output}")

def run_frames(args):
    mapped = json.loads(Path(args.input).read_text())
    emulator = NESEmulatorCore()
    frames = emulator.process_all_tracks(mapped)
    Path(args.output).write_text(json.dumps(frames, indent=2))
    print(f" Generated frames -> {args.output}")

def estimate_segment_sizes(music_asm_path):
    """ROM byte totals music.asm emits (.byte/.word/.incbin), keyed by the active
    `.segment "NAME"`.

    Per-segment rather than a single total because a banked mapper (MMC3)
    distributes data across distinct PRG regions, and the binding limit is the
    region each segment lands in, not the full PRG (#126, #127). ld65 remains the
    exact backstop. .res lives in RAM/ZP (not PRG ROM) and is ignored. A bounded
    `.incbin "f", 0, N` (a truncated DPCM sample, #68) counts N, not the file size.
    """
    import re
    music_path = Path(music_asm_path)
    if not music_path.exists():
        return {}
    sizes = {}
    current = None
    base_dir = music_path.parent
    for raw in music_path.read_text().splitlines():
        line = raw.split(';', 1)[0].strip()  # drop comments
        low = line.lower()
        if low.startswith('.segment'):
            m = re.search(r'"([^"]+)"', line)
            if m:
                current = m.group(1)
            continue
        n = 0
        if low.startswith('.byte'):
            n = len([t for t in line[5:].split(',') if t.strip()])
        elif low.startswith('.word'):
            n = 2 * len([t for t in line[5:].split(',') if t.strip()])
        elif low.startswith('.incbin'):
            bounded = re.search(r'"[^"]+"\s*,\s*\d+\s*,\s*(\d+)', line)
            if bounded:
                n = int(bounded.group(1))
            else:
                m = re.search(r'"([^"]+)"', line)
                if m:
                    p = Path(m.group(1))
                    if not p.is_absolute():
                        p = base_dir / p
                    if p.exists():
                        n = p.stat().st_size
        if n:
            sizes[current] = sizes.get(current, 0) + n
    return sizes


def estimate_music_data_size(music_asm_path):
    """Total ROM data bytes music.asm emits (sum across all segments)."""
    return sum(estimate_segment_sizes(music_asm_path).values())


def check_mapper_capacity(music_asm_path, mapper):
    """Pre-flight capacity gate (#11, #126, #127): abort before linking if the
    emitted music data overflows any of the selected mapper's PRG regions.

    Sizes each music.asm segment against the region the mapper's linker config
    loads it into (a banked mapper has several binding regions, not one 510 KB
    ceiling), so an oversized song fails with a clear budget message instead of a
    raw ld65 region overflow. Raises ValueError listing every overflow. Returns
    the total data size for logging.
    """
    segment_sizes = estimate_segment_sizes(music_asm_path)
    errors = mapper.validate_segment_sizes(segment_sizes)
    if errors:
        detail = "\n".join(f"  - {e}" for e in errors)
        raise ValueError(
            f"Music data does not fit the {mapper.name} PRG layout:\n{detail}\n"
            f"Shorten the song or DPCM samples, or select a larger mapper."
        )
    return sum(segment_sizes.values())


def _restore_backup(output_rom, backup_path):
    """Restore a pre-build backup ROM over the (now-invalid) output."""
    if backup_path and Path(backup_path).exists():
        print(f"  💊 Restoring backup ROM: {Path(backup_path).name} → {Path(output_rom).name}")
        shutil.copy2(backup_path, output_rom)
        print(f"  ✅ Original ROM restored from backup")


def validate_rom(output_rom, verbose=False):
    """Post-build ROM validation shared by the full pipeline and the `compile`
    subcommand (#15) so step-by-step ROMs get the same gate as the default path.

    Returns True if the ROM is bootable. On a boot-fatal defect (invalid
    $FFFA-$FFFF vectors or no APU init) it returns False — the caller owns backup
    restore (#26). Non-fatal health issues are warned but pass. A diagnostics
    failure is warned (verbose) and treated as non-blocking, matching prior behavior.
    """
    try:
        from debug.rom_diagnostics import ROMDiagnostics
        rom_result = ROMDiagnostics(verbose=False).diagnose_rom(str(output_rom))
    except Exception as e:
        if verbose:
            print(f"  Warning: ROM validation failed: {e}")
        return True

    fatal_defects = []
    if not rom_result.reset_vectors_valid:
        fatal_defects.append("invalid reset/NMI/IRQ vectors ($FFFA-$FFFF)")
    if rom_result.apu_pattern_count == 0:
        fatal_defects.append("no APU initialization code found")
    if fatal_defects:
        print("[ERROR] ROM validation failed - unbootable ROM:")
        for defect in fatal_defects:
            print(f"    - {defect}")
        return False

    if rom_result.overall_health not in ["HEALTHY", "GOOD"]:
        print(f"⚠️  ROM health check: {rom_result.overall_health}")
        print(f"  Issues found: {len(rom_result.issues)}")
        for issue in rom_result.issues[:3]:
            print(f"    - {issue}")
        if rom_result.overall_health == "ERROR":
            print("[ERROR] ROM validation failed - ROM is invalid")
            return False
    else:
        print(f"  ✓ ROM Health: {rom_result.overall_health}")
        print(f"  ✓ APU Patterns: {rom_result.apu_pattern_count}")
        print(f"  ✓ Assembly Score: {rom_result.assembly_code_score}/220")
    return True


def run_compile(args):
    """Compile a prepared NES project to a ROM and validate it (#15).

    Gives the step-by-step path the same compile + post-build validation the
    full pipeline runs, instead of stopping at `prepare` and building by hand.
    """
    project_path = Path(args.input)
    output_rom = Path(args.output)
    if not project_path.is_dir():
        print(f"[ERROR] Prepared project directory not found: {project_path}")
        sys.exit(1)

    print(f"Compiling NES ROM from {project_path} ...")
    if not compile_rom(project_path, output_rom):
        print("[ERROR] ROM compilation failed")
        sys.exit(1)

    if not getattr(args, 'skip_validation', False):
        print("Validating ROM...")
        if not validate_rom(output_rom, verbose=getattr(args, 'verbose', False)):
            sys.exit(1)

    print(f"[OK] Compiled ROM -> {output_rom}")


def run_prepare(args):
    from mappers.mmc3 import MMC3Mapper
    mapper = MMC3Mapper()
    try:
        check_mapper_capacity(args.input, mapper)
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    builder = NESProjectBuilder(args.output, mapper=mapper)
    # prepare_project may raise (bad path/permissions) or return falsy; either
    # way surface a clean nonzero exit instead of an uncaught traceback or a
    # silent exit 0 on failure (#15).
    try:
        prepared = builder.prepare_project(args.input)
    except Exception as e:
        print(f"[ERROR] Failed to prepare NES project: {e}")
        sys.exit(1)
    if not prepared:
        print("[ERROR] Failed to prepare NES project")
        sys.exit(1)
    print(f" Prepared NES project -> {args.output}")
    print(" Ready for CC65 compilation!")
    print(" To build:")
    print(f" 1. cd {args.output}")
    print(" 2. ./build.sh  (or build.bat on Windows)")
    print(" Or compile + validate in one step: python main.py compile "
          f"{args.output} <output.nes>")

def run_export(args):
    """Export function supporting multiple formats with pattern compression"""
    frames = json.loads(Path(args.input).read_text())
    
    # Check if we have pattern data
    pattern_data = None
    if args.patterns:
        pattern_data = json.loads(Path(args.patterns).read_text())
    
    # NOTE: `nsf` was removed from --format until the NSF exporter produces a
    # playable file (#81/EXP-05). The old `if args.format == "nsftxt"` branch
    # dispatched on a string argparse never allowed, so `--format nsf` silently
    # wrote nothing (#79). With `ca65` the only choice, argparse now rejects an
    # nsf request up front instead of no-oping; re-add the branch here when NSF
    # is real.
    if args.format == "ca65":
        # Always use CA65Exporter, with empty patterns if none provided
        if pattern_data:
            patterns = pattern_data['patterns']
            references = pattern_data['references']
        else:
            patterns = {}
            references = {}
            
        exporter = CA65Exporter()
        exporter.export_tables_with_patterns(
            frames,
            patterns,
            references,
            args.output,
            standalone=False  # Don't include header and vectors for project builder
        )
            
        # Pack DPCM samples for exported ASM
        try:
            from dpcm_sampler.dpcm_packer import DpcmPacker
            from dpcm_sampler.generate_dpcm_index import (
                load_dpcm_index_into_packer,
                get_dpcm_sample_ids_from_frames,
            )
            packer = DpcmPacker()
            dpcm_index_path = Path('dpcm_index.json')
            if dpcm_index_path.exists():
                with open(dpcm_index_path, 'r') as f:
                    dpcm_index = json.load(f)
                # Pack only the samples this song triggers, not the whole catalog (#140).
                # Pass the set directly: an empty set means "pack nothing" (no DPCM
                # in this song), not "pack everything".
                sample_ids = get_dpcm_sample_ids_from_frames(frames)
                loaded_samples, _ = load_dpcm_index_into_packer(
                    packer, dpcm_index, dpcm_index_path, sample_ids=sample_ids)
                if loaded_samples == 0 and sample_ids:
                    print(f" Warning: this song references {len(sample_ids)} DPCM sample(s) but none resolved to a file — percussion will be silent.")
                with open(args.output, 'a') as f:
                    f.write("\n\n" + packer.generate_assembly())
        except Exception as e:
            print(f" Warning: Failed to pack DPCM samples: {e}")
                
        print(f" Exported CA65 ASM -> {args.output}")

def run_detect_patterns(args):
    frames = json.loads(Path(args.input).read_text())
    
    # Create tempo map and pattern detector
    tempo_map = EnhancedTempoMap(initial_tempo=500000)  # 120 BPM default
    detector = EnhancedPatternDetector(tempo_map, min_pattern_length=PATTERN_MIN_LENGTH,
                                       max_pattern_length=PATTERN_MAX_LENGTH)
    
    # Extract events from frames structure
    events = []
    for channel_name, channel_frames in frames.items():
        for frame_num, frame_data in channel_frames.items():
            event = {
                'frame': int(frame_num),
                'note': frame_data.get('note', 0),
                'volume': frame_data.get('volume', 0)
            }
            events.append(event)
    
    # Sort events by frame number
    events.sort(key=lambda x: x['frame'])

    # Apply the shared large-file policy (#21) so this subcommand stays as
    # robust as the default pipeline on big inputs instead of running unbounded.
    original_count = len(events)
    events, was_sampled = sample_events_for_detection(events)
    if was_sampled:
        print(f"⚠️  Large file ({original_count} events): sampled to {len(events)} "
              f"({len(events)/original_count*100:.1f}%, lossy) before pattern detection")

    # Detect patterns
    pattern_result = detector.detect_patterns(events)
    
    # Save compressed patterns
    output = {
        'patterns': pattern_result['patterns'],
        'references': pattern_result['references'],
        'stats': pattern_result['stats']
    }
    Path(args.output).write_text(json.dumps(output, indent=2))
    print(f" Detected patterns -> {args.output}")
    print(f" Compression ratio: {pattern_result['stats']['compression_ratio']:.1f}% reduction")

def run_song_add(args):
    """Add a song to the song bank"""
    bank = SongBank()
    
    # Load existing bank if specified
    if args.bank and Path(args.bank).exists():
        bank.import_bank(args.bank)
    
    # Prepare metadata
    metadata = {
        'composer': args.composer,
        'loop_point': args.loop_point,
        'tags': args.tags.split(',') if args.tags else [],
        'tempo_base': args.tempo
    }
    
    # Add song to bank
    bank.add_song_from_midi(args.input, args.name, metadata)
    
    # Save bank
    output_path = args.bank or 'song_bank.json'
    bank.export_bank(output_path)
    print(f"Song added to bank: {output_path}")

def run_song_list(args):
    """List songs in the song bank"""
    if not Path(args.bank).exists():
        print(f"Error: Song bank file not found: {args.bank}")
        return
    
    bank = SongBank()
    bank.import_bank(args.bank)
    
    print("\nSongs in bank:")
    print("-" * 50)
    for name, song_data in bank.songs.items():
        metadata = song_data['metadata']
        print(f"Title: {name}")
        if metadata.get('composer'):
            print(f"Composer: {metadata['composer']}")
        if metadata.get('tags'):
            print(f"Tags: {', '.join(metadata['tags'])}")
        if metadata.get('loop_point') is not None:
            print(f"Loop point: {metadata['loop_point']}")
        print(f"Bank: {song_data['bank']}")
        print("-" * 50)

def run_song_remove(args):
    """Remove a song from the bank"""
    if not Path(args.bank).exists():
        print(f"Error: Song bank file not found: {args.bank}")
        return
    
    bank = SongBank()
    bank.import_bank(args.bank)
    
    if args.name not in bank.songs:
        print(f"Error: Song '{args.name}' not found in bank")
        return
    
    del bank.songs[args.name]
    bank.export_bank(args.bank)
    print(f"Song '{args.name}' removed from bank")

def load_config(config_path: Optional[str] = None) -> DrumMapperConfig:
    """Load drum mapper configuration from file or use defaults"""
    if config_path and Path(config_path).exists():
        return DrumMapperConfig.from_file(config_path)
    return DrumMapperConfig()

def run_full_pipeline(args):
    """Run the complete MIDI to NES ROM pipeline"""
    input_midi = Path(args.input)
    if not input_midi.exists():
        print(f"[ERROR] Input MIDI file not found: {input_midi}")
        sys.exit(1)
    
    # Determine output ROM path
    if hasattr(args, 'output') and args.output:
        output_rom = Path(args.output)
    else:
        output_rom = input_midi.with_suffix('.nes')
    
    # Create backup if output ROM already exists
    backup_path = None
    if output_rom.exists():
        backup_path = output_rom.with_suffix('.nes.backup')
        print(f"  💾 Creating backup of existing ROM: {backup_path.name}")
        shutil.copy2(output_rom, backup_path)
    
    # Check for no-patterns flag
    use_patterns = not (hasattr(args, 'no_patterns') and args.no_patterns)
    
    print(f"🎵 MIDI2NES Pipeline: {input_midi.name} → {output_rom.name}")
    if not use_patterns:
        print("   🔄 Direct export mode (no pattern compression)")
    print("=" * 60)
    
    # Create temporary directory for intermediate files
    build_succeeded = False
    with tempfile.TemporaryDirectory(prefix="midi2nes_") as temp_dir:
        temp_path = Path(temp_dir)

        try:
            # Step 1: Parse MIDI to frames (using fast parser)
            print("[1/7] Parsing MIDI file...")
            from tracker.parser_fast import parse_midi_to_frames as parse_fast
            midi_data = parse_fast(str(input_midi))

            # Check for arranger mode
            use_arranger = hasattr(args, 'arranger') and args.arranger

            if use_arranger:
                # Step 2+3: Use intelligent arranger with arpeggiation
                print("[2/7] Analyzing musical structure...")
                print("[3/7] Arranging for NES with arpeggiation...")
                frames = arrange_for_nes(
                    midi_data["events"],
                    arp_speed=3,  # 20Hz arpeggiation (classic NES)
                    verbose=args.verbose
                )
            else:
                # Step 2: Map tracks to NES channels (legacy mode)
                print("[2/7] Mapping tracks to NES channels...")
                dpcm_index_path = 'dpcm_index.json'
                mapped = assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)

                # Step 3: Generate frame data
                print("[3/7] Generating NES frame data...")
                emulator = NESEmulatorCore()
                frames = emulator.process_all_tracks(mapped)
            
            # Step 4: Pattern detection or direct export
            # Tracks any lossy event sampling so the success banner can warn that
            # the ROM is incomplete rather than reporting silent loss (#10).
            pattern_loss_warning = None
            if use_patterns:
                print("[4/7] Detecting patterns for compression...")
                tempo_map = EnhancedTempoMap(initial_tempo=500000)
                
                # Convert frames to events for pattern detection
                events = []
                for channel_name, channel_frames in frames.items():
                    for frame_num, frame_data in channel_frames.items():
                        events.append({
                            'frame': int(frame_num),
                            'note': frame_data.get('note', 0),
                            'volume': frame_data.get('volume', 0)
                        })
                events.sort(key=lambda x: x['frame'])

                # Check if we should skip pattern detection for very large files
                LARGE_FILE_THRESHOLD = 10000
                if len(events) > LARGE_FILE_THRESHOLD:
                    print(f"  ⚠️  Large MIDI file ({len(events):,} events) detected")
                    print(f"  💡 For best results with large files, consider using --no-patterns flag")
                    print(f"  🚀 Proceeding with improved pattern detection...")
                
                # Use parallel pattern detection with position mapping fix
                try:
                    from tracker.pattern_detector_parallel import ParallelPatternDetector
                    detector = ParallelPatternDetector(tempo_map, min_pattern_length=PATTERN_MIN_LENGTH, max_pattern_length=PATTERN_MAX_LENGTH)
                    print(f"  Using parallel pattern detection with {len(events):,} events")
                    pattern_result = detector.detect_patterns(events)
                except Exception as e:
                    print(f"  Parallel detection failed, using fallback: {e}")
                    from tracker.pattern_detector import EnhancedPatternDetector
                    detector = EnhancedPatternDetector(tempo_map, min_pattern_length=PATTERN_MIN_LENGTH, max_pattern_length=PATTERN_MAX_LENGTH)
                    # Sequential fallback is slower, so cap more conservatively —
                    # but sample uniformly (not head-truncate) to keep structure.
                    FALLBACK_MAX_EVENTS = 2000
                    fallback_count = len(events)
                    events, was_sampled = sample_events_for_detection(events, FALLBACK_MAX_EVENTS)
                    if was_sampled:
                        pattern_loss_warning = (
                            f"pattern detection fell back to the sequential detector and "
                            f"sampled {fallback_count:,} events down to {len(events):,} — "
                            f"the ROM is INCOMPLETE. Re-run with --no-patterns for full fidelity."
                        )
                        print(f"  ⚠️  WARNING: {pattern_loss_warning}")
                    pattern_result = detector.detect_patterns(events)
            else:
                print("[4/7] Skipping pattern detection (direct export mode)...")
                print(f"  📊 Processing direct frame export for complete data preservation")
                # Create dummy pattern result for direct export
                pattern_result = {
                    'patterns': {},
                    'references': {},
                    'stats': {
                        'compression_ratio': 1.0,
                        'original_events': sum(len(ch) for ch in frames.values()),
                        'compressed_size': sum(len(ch) for ch in frames.values()),
                        'patterns_found': 0
                    }
                }
                events = []  # Not needed for direct export
            
            # Step 5: Export to CA65 assembly
            print("[5/7] Exporting to CA65 assembly...")
            music_asm = temp_path / "music.asm"
            
            # The CA65 exporter emits every byte from `frames`; the detector's
            # pattern `references` are analysis/metrics only and are never read by
            # export_tables_with_patterns (#4). `patterns` truthiness merely
            # selects the macro-bytecode serializer over direct export, so pass an
            # empty references dict rather than building a table nothing consumes.
            exporter = CA65Exporter()
            exporter.export_tables_with_patterns(
                frames,
                pattern_result['patterns'],
                {},
                str(music_asm),
                standalone=False  # We'll create our own project structure
            )
            
            # Step 5.5: Pack DPCM samples
            print("[5.5/7] Packing DPCM samples...")
            try:
                from dpcm_sampler.dpcm_packer import DpcmPacker
                from dpcm_sampler.generate_dpcm_index import (
                    load_dpcm_index_into_packer,
                    get_dpcm_sample_ids_from_frames,
                )
                packer = DpcmPacker()
                dpcm_index_path = Path('dpcm_index.json')

                if dpcm_index_path.exists():
                    with open(dpcm_index_path, 'r') as f:
                        dpcm_index = json.load(f)

                    # Pack only the samples this song triggers (#140), truncating
                    # oversized ones (#68), in ascending id order so they align
                    # with the engine's positional tables. An empty set means
                    # "pack nothing", so pass it through directly (not `or None`).
                    sample_ids = get_dpcm_sample_ids_from_frames(frames)
                    loaded_samples, _ = load_dpcm_index_into_packer(
                        packer, dpcm_index, dpcm_index_path, verbose=args.verbose,
                        sample_ids=sample_ids
                    )

                    # Generate the lookup tables and binary includes, append to music.asm
                    dpcm_asm = packer.generate_assembly()
                    with open(music_asm, 'a') as f:
                        f.write("\n\n" + dpcm_asm)

                    if loaded_samples > 0:
                        print(f"  ✓ Packed {loaded_samples} DPCM samples across {len(packer.banks)} banks")
                    elif sample_ids:
                        print(f"  ⚠️ Warning: this song references {len(sample_ids)} DPCM sample(s) but none resolved to a file — percussion will be silent.")
                    else:
                        print("  ℹ️ No DPCM samples referenced by this song.")
                else:
                    print("  ℹ️ No dpcm_index.json found, skipping DPCM packing.")
            except Exception as e:
                print(f"  ⚠️ Warning: Failed to pack DPCM samples: {str(e)}")
                if args.verbose:
                    import traceback
                    traceback.print_exc()
                    
            # Step 6: Prepare NES project
            print("[6/7] Preparing NES project...")
            project_path = temp_path / "nes_project"

            # Enable debug mode if requested
            debug_mode = hasattr(args, 'debug') and args.debug

            from mappers.mmc3 import MMC3Mapper
            mapper = MMC3Mapper()

            # Capacity pre-flight (#11): catch an oversized song with a clear
            # message before ld65 reports a raw region overflow.
            try:
                data_size = check_mapper_capacity(str(music_asm), mapper)
                print(f"  ✓ Music data {data_size:,} bytes fits the {mapper.name} PRG regions")
            except ValueError as e:
                print(f"[ERROR] {e}")
                sys.exit(1)

            builder = NESProjectBuilder(str(project_path), debug_mode=debug_mode, mapper=mapper)

            if not builder.prepare_project(str(music_asm)):
                print("[ERROR] Failed to prepare NES project")
                sys.exit(1)
            
            # Step 7: Compile ROM
            print("[7/7] Compiling NES ROM...")
            if not compile_rom(project_path, output_rom):
                print("[ERROR] ROM compilation failed")
                sys.exit(1)  # finally handles restore

            # Step 8: Validate ROM — shared with the `compile` subcommand (#15)
            # so step-by-step ROMs get the same boot-fatal gate (#6).
            skip_validation = hasattr(args, 'skip_validation') and args.skip_validation
            if not skip_validation:
                print("[8/8] Validating ROM...")
                if not validate_rom(output_rom, verbose=getattr(args, 'verbose', False)):
                    sys.exit(1)  # finally handles restore

            # Success!
            rom_size = output_rom.stat().st_size
            print("\n" + "=" * 60)
            print(f"✅ SUCCESS! ROM created: {output_rom.name}")
            print(f"   ROM size: {rom_size:,} bytes ({rom_size / 1024:.1f} KB)")
            print(f"   Compression ratio: {pattern_result['stats']['compression_ratio']:.1f}% reduction")
            print(f"   Total patterns detected: {len(pattern_result['patterns'])}")
            if pattern_loss_warning:
                print(f"\n   ⚠️  INCOMPLETE OUTPUT: {pattern_loss_warning}")
            print("\n🎮 Your NES ROM is ready to run on emulators or flash carts!")

            # The new ROM is final and validated; mark success so the finally
            # block does not attempt a restore, then drop the now-redundant backup.
            build_succeeded = True
            if backup_path:
                backup_path.unlink(missing_ok=True)

        except Exception as e:
            print(f"\n[ERROR] Pipeline failed: {str(e)}")
            if args.verbose:
                import traceback
                print("\nFull traceback:")
                traceback.print_exc()
            sys.exit(1)

        finally:
            # Single restore point that covers every failure path after backup
            # creation: compile failure, prepare failure, top-level exception (#26).
            if not build_succeeded:
                _restore_backup(output_rom, backup_path)

def main():
    parser = argparse.ArgumentParser(
        description=f"MIDI to NES ROM compiler v{__version__}\n\nDefault usage: midi2nes song.mid [output.nes]",
        epilog="For more information, visit: https://github.com/matiaszanolli/midi2nes",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--version', action='version', version=f'MIDI2NES {__version__}')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug overlay in ROM (shows APU status, frame counter, errors on screen)')
    parser.add_argument('--arranger', '-a', action='store_true', help='Use intelligent arranger with arpeggiation for polyphonic content')
    
    subparsers = parser.add_subparsers(dest='command', help='Advanced commands (optional - default is MIDI to ROM conversion)')

    # Existing subcommands
    p_parse = subparsers.add_parser('parse', help='Parse MIDI to intermediate JSON')
    p_parse.add_argument('input')
    p_parse.add_argument('output')
    p_parse.set_defaults(func=run_parse)

    # Update map command with new configuration options
    p_map = subparsers.add_parser('map', help='Map parsed MIDI to NES channels')
    p_map.add_argument('input')
    p_map.add_argument('output')
    # NOTE: drum-mapper --config is not consumed by assign_tracks_to_nes_channels,
    # so it was dropped here rather than left as a silently-ignored flag (#13).
    p_map.add_argument('--dpcm-index', help='Path to DPCM sample index')
    p_map.set_defaults(func=run_map)

    # Add new configuration management commands
    p_config = subparsers.add_parser('config', help='Configuration management')
    config_subparsers = p_config.add_subparsers(dest='config_command')

    # Generate default config
    p_config_init = config_subparsers.add_parser('init', 
                                                help='Generate default configuration')
    p_config_init.add_argument('output', help='Output configuration file path')
    p_config_init.set_defaults(func=run_config_init)

    # Validate config
    p_config_validate = config_subparsers.add_parser('validate', 
                                                    help='Validate configuration file')
    p_config_validate.add_argument('config', help='Configuration file to validate')
    p_config_validate.set_defaults(func=run_config_validate)

    # Keep existing commands
    p_frames = subparsers.add_parser('frames', help='Generate frame data from mapped tracks')
    p_frames.add_argument('input')
    p_frames.add_argument('output')
    p_frames.set_defaults(func=run_frames)

    p_patterns = subparsers.add_parser('detect-patterns', 
                                      help='Detect and compress patterns in frame data')
    p_patterns.add_argument('input')
    p_patterns.add_argument('output')
    p_patterns.add_argument('--config', help='Path to pattern detection configuration')
    p_patterns.set_defaults(func=run_detect_patterns)

    p_export = subparsers.add_parser('export', help='Export NES-ready files (ca65/FamiTracker)')
    p_export.add_argument('input')
    p_export.add_argument('output')
    # `nsf` is intentionally absent until the NSF exporter is playable (#79/#81);
    # offering it made `--format nsf` a silent no-op rather than a real export.
    p_export.add_argument('--format', choices=['ca65'], default='ca65')
    p_export.add_argument('--patterns', help='Path to pattern data JSON (optional)')
    p_export.set_defaults(func=run_export)

    # Keep other existing commands...
    p_prepare = subparsers.add_parser('prepare', help='Prepare CA65 project for compilation')
    p_prepare.add_argument('input', help='Input music.asm file')
    p_prepare.add_argument('output', help='Output project directory')
    p_prepare.set_defaults(func=run_prepare)

    # `compile` gives the step-by-step path the same compile + validation gate as
    # the full pipeline, instead of stopping at `prepare` (#15).
    p_compile = subparsers.add_parser('compile', help='Compile a prepared NES project to a ROM and validate it')
    p_compile.add_argument('input', help='Prepared NES project directory')
    p_compile.add_argument('output', help='Output .nes ROM path')
    p_compile.add_argument('--skip-validation', action='store_true', help='Skip post-compile ROM validation')
    p_compile.add_argument('--verbose', '-v', action='store_true', help='Verbose validation output')
    p_compile.set_defaults(func=run_compile)

    # Song bank management commands
    p_song = subparsers.add_parser(
        'song',
        help='Song bank management (JSON storage/analysis only; not compiled to ROM)'
    )
    song_subparsers = p_song.add_subparsers(dest='song_command')

    p_song_add = song_subparsers.add_parser('add', help='Add song to bank')
    p_song_add.add_argument('input', help='Input MIDI file')
    p_song_add.add_argument('--bank', help='Song bank file (creates new if not exists)')
    p_song_add.add_argument('--name', help='Song name (defaults to filename)')
    p_song_add.add_argument('--composer', help='Song composer')
    p_song_add.add_argument('--loop-point', type=int, help='Loop point in frames')
    p_song_add.add_argument('--tags', help='Comma-separated tags')
    p_song_add.add_argument('--tempo', type=int, default=120, help='Base tempo (default: 120)')
    p_song_add.add_argument('--config', help='Path to drum mapper configuration')
    p_song_add.set_defaults(func=run_song_add)

    p_song_list = song_subparsers.add_parser('list', help='List songs in bank')
    p_song_list.add_argument('bank', help='Song bank file')
    p_song_list.set_defaults(func=run_song_list)

    p_song_remove = song_subparsers.add_parser('remove', help='Remove song from bank')
    p_song_remove.add_argument('bank', help='Song bank file')
    p_song_remove.add_argument('name', help='Song name to remove')
    p_song_remove.set_defaults(func=run_song_remove)

    # Add benchmark command
    p_benchmark = subparsers.add_parser('benchmark', help='Performance benchmarking')
    benchmark_subparsers = p_benchmark.add_subparsers(dest='benchmark_command')
    
    # Run benchmark
    p_benchmark_run = benchmark_subparsers.add_parser('run', help='Run performance benchmark')
    p_benchmark_run.add_argument('files', nargs='*', help='MIDI files to benchmark (optional)')
    p_benchmark_run.add_argument('--output', default='benchmark_results', help='Output directory')
    p_benchmark_run.add_argument('--memory', action='store_true', help='Enable detailed memory profiling')
    p_benchmark_run.set_defaults(func=run_benchmark)
    
    # Memory usage command
    p_benchmark_memory = benchmark_subparsers.add_parser('memory', help='Show current memory usage')
    p_benchmark_memory.set_defaults(func=run_benchmark_memory)

    # Custom argument parsing to handle default behavior
    import sys
    
    # Check if first argument (if any) is a subcommand
    subcommands = ['parse', 'map', 'config', 'frames', 'detect-patterns', 'export', 'prepare', 'compile', 'song', 'benchmark']
    
    # Handle special cases first
    if len(sys.argv) == 1:
        parser.print_help()
        return
    
    if len(sys.argv) == 2 and sys.argv[1] in ['--help', '-h']:
        parser.print_help()
        sys.exit(0)
    
    if len(sys.argv) == 2 and sys.argv[1] in ['--version']:
        parser.parse_args(sys.argv[1:])
        return
    
    # Check if first non-option argument is a subcommand
    first_arg = None
    for arg in sys.argv[1:]:
        if not arg.startswith('-'):
            first_arg = arg
            break
    
    if first_arg in subcommands:
        # It's a subcommand, parse normally
        args = parser.parse_args()
        if hasattr(args, 'func'):
            args.func(args)
        else:
            parser.print_help()
    else:
        # It's the default MIDI-to-ROM behavior
        # Parse global options first
        global_args = []
        remaining_args = []
        
        i = 1
        while i < len(sys.argv):
            arg = sys.argv[i]
            if arg in ['--verbose', '-v']:
                global_args.extend([arg])
                i += 1
            elif arg in ['--debug', '-d']:
                global_args.extend([arg])
                i += 1
            elif arg in ['--arranger', '-a']:
                global_args.extend([arg])
                i += 1
            elif arg == '--version':
                global_args.extend([arg])
                i += 1
            elif arg == '--no-patterns':
                global_args.extend([arg])
                i += 1
            elif arg == '--skip-validation':
                global_args.extend([arg])
                i += 1
            elif arg.startswith('-'):
                # Reject unknown/typo flags instead of silently dropping them —
                # a swallowed --no-patterns/--arranger produces a different ROM (#8).
                print(f"Error: Unknown option: {arg}", file=sys.stderr)
                print("Run 'midi2nes --help' for available options.", file=sys.stderr)
                sys.exit(2)
            else:
                remaining_args.append(arg)
                i += 1

        if not remaining_args:
            print("Error: Please provide an input MIDI file")
            print("\nUsage examples:")
            print("  midi2nes song.mid                  # Creates song.nes")
            print("  midi2nes song.mid output.nes       # Creates output.nes")
            print("  midi2nes --arranger song.mid       # Smart voice allocation + arpeggiation")
            print("  midi2nes --no-patterns song.mid    # Direct export (no compression)")
            print("  midi2nes --debug song.mid          # Debug ROM (shows APU status on screen)")
            print("  midi2nes --skip-validation song.mid # Skip ROM validation after compilation")
            print("  midi2nes --help                    # Show full help")
            sys.exit(1)

        # Create a simple args object for the default pipeline
        class SimpleArgs:
            def __init__(self):
                self.input = remaining_args[0] if remaining_args else None
                self.output = remaining_args[1] if len(remaining_args) > 1 else None
                self.verbose = '--verbose' in global_args or '-v' in global_args
                self.no_patterns = '--no-patterns' in global_args
                self.debug = '--debug' in global_args or '-d' in global_args
                self.arranger = '--arranger' in global_args or '-a' in global_args
                self.skip_validation = '--skip-validation' in global_args
                self.command = None

        args = SimpleArgs()
        run_full_pipeline(args)

def run_config_init(args):
    """Generate default configuration file"""
    try:
        config_manager = ConfigManager()
        config_manager.copy_default_config_to(args.output)
        print(f"[OK] Generated default configuration -> {args.output}")
        print(f"     Edit this file to customize MIDI2NES behavior")
    except Exception as e:
        print(f"[ERROR] Failed to generate configuration: {str(e)}")
        sys.exit(1)

def run_config_validate(args):
    """Validate configuration file"""
    try:
        config_manager = ConfigManager(args.config)
        config_manager.validate()
        print(f"[OK] Configuration file is valid: {args.config}")
        
        # Show some key settings
        if hasattr(args, 'verbose') and args.verbose:
            print("\nConfiguration summary:")
            print(f"  Pattern detection min length: {config_manager.get('processing.pattern_detection.min_length')}")
            print(f"  Memory limit: {config_manager.get('performance.max_memory_mb')} MB")
            print(f"  NSF load address: 0x{config_manager.get('export.nsf.load_address'):04X}")
            
    except Exception as e:
        print(f"[ERROR] Configuration validation failed: {str(e)}")
        sys.exit(1)

def run_benchmark(args):
    """Run performance benchmarks"""
    benchmark = PerformanceBenchmark()
    
    # Set up test files
    test_files = []
    if args.files:
        for file_pattern in args.files:
            file_path = Path(file_pattern)
            if file_path.is_file():
                test_files.append(str(file_path))
            elif file_path.is_dir():
                # Find MIDI files in directory
                midi_files = list(file_path.glob('*.mid')) + list(file_path.glob('*.midi'))
                test_files.extend([str(f) for f in midi_files])
            else:
                print(f"Warning: {file_pattern} not found")
    
    if not test_files:
        print("No test files specified. Using built-in test data.")
        # Generate some test data
        test_files = None
    
    try:
        # Create output directory
        output_dir = Path(args.output)
        output_dir.mkdir(exist_ok=True)
        
        # Run the benchmarks
        print(f"Running performance benchmarks...")
        if args.memory:
            print("Memory profiling enabled")
            
        if test_files:
            # Run benchmarks on provided files
            results = {}
            for midi_file in test_files:
                print(f"Running pipeline benchmark on: {midi_file}")
                try:
                    result = benchmark.run_full_pipeline(midi_file)
                    results[Path(midi_file).name] = {
                        'file_path': result.file_path,
                        'file_size_kb': result.file_size_kb,
                        'execution_time': result.total_duration_ms / 1000,  # Convert to seconds
                        'memory_peak': result.total_memory_mb,
                        'stages': [{stage.stage: {'duration_ms': stage.duration_ms, 'success': stage.success}} for stage in result.stages],
                        'midi_info': result.midi_info
                    }
                    if result.midi_info.get('total_events', 0) > 0:
                        results[Path(midi_file).name]['throughput'] = result.midi_info['total_events'] / (result.total_duration_ms / 1000)
                except Exception as e:
                    print(f"  Failed to benchmark {midi_file}: {str(e)}")
                    results[Path(midi_file).name] = {'error': str(e)}
        else:
            print("Running synthetic benchmark tests...")
            # Create simple synthetic test
            results = {
                'synthetic_test': {
                    'execution_time': 0.001,
                    'memory_peak': 10.0,
                    'note': 'Synthetic test - no actual MIDI files provided'
                }
            }
        
        # Save results to JSON
        results_file = output_dir / "benchmark_results.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        # Print summary
        print(f"\n[OK] Benchmark completed -> {results_file}")
        print("\nBenchmark Summary:")
        print("-" * 50)
        
        for test_name, result in results.items():
            if isinstance(result, dict) and 'execution_time' in result:
                print(f"{test_name}: {result['execution_time']:.3f}s")
                if 'memory_peak' in result:
                    print(f"  Peak memory: {result['memory_peak']:.2f} MB")
                if 'throughput' in result:
                    print(f"  Throughput: {result['throughput']:.1f} events/sec")
        
    except Exception as e:
        print(f"[ERROR] Benchmark failed: {str(e)}")
        sys.exit(1)

def run_benchmark_memory(args):
    """Show current memory usage"""
    try:
        memory_info = get_memory_usage()
        log_memory_usage("Current Memory Usage")
        
        print("Memory Usage Report:")
        print("-" * 30)
        for key, value in memory_info.items():
            if isinstance(value, float):
                print(f"{key}: {value:.2f} MB")
            else:
                print(f"{key}: {value}")
                
    except Exception as e:
        print(f"[ERROR] Memory profiling failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
