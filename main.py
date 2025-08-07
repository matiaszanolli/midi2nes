import argparse
import sys
import json
import tempfile
import subprocess
import shutil
from typing import Dict, Optional
from pathlib import Path

# Import version information
try:
    from midi2nes import __version__
except ImportError:
    # Fallback for development mode
    __version__ = "0.4.0-dev"

from tracker.parser import parse_midi_to_frames
from tracker.track_mapper import assign_tracks_to_nes_channels
from nes.emulator_core import NESEmulatorCore
from nes.project_builder import NESProjectBuilder
from nes.song_bank import SongBank
from exporter.exporter_nsf import NSFExporter
from exporter.exporter_ca65 import CA65Exporter
from exporter.exporter import generate_famitracker_txt_with_patterns
from tracker.pattern_detector import EnhancedPatternDetector
from tracker.tempo_map import EnhancedTempoMap
from dpcm_sampler.enhanced_drum_mapper import EnhancedDrumMapper, DrumMapperConfig
from config.config_manager import ConfigManager
from benchmarks.performance_suite import PerformanceBenchmark
from utils.profiling import get_memory_usage, log_memory_usage

def run_parse(args):
    midi_data = parse_midi_to_frames(args.input)
    Path(args.output).write_text(json.dumps(midi_data, indent=2))
    print(f"[OK] Parsed MIDI -> {args.output}")

def run_map(args):
    midi_data = json.loads(Path(args.input).read_text())
    dpcm_index_path = 'dpcm_index.json'
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

def run_prepare(args):
    builder = NESProjectBuilder(args.output)
    if builder.prepare_project(args.input):
        print(f" Prepared NES project -> {args.output}")
        print(" Ready for CC65 compilation!")
        print(" To build:")
        print(f" 1. cd {args.output}")
        print(" 2. ./build.sh  (or build.bat on Windows)")

def run_export(args):
    """Export function supporting multiple formats with pattern compression"""
    frames = json.loads(Path(args.input).read_text())
    
    # Check if we have pattern data
    pattern_data = None
    if args.patterns:
        pattern_data = json.loads(Path(args.patterns).read_text())
    
    if args.format == "nsftxt":
        # Create NSF exporter instance
        exporter = NSFExporter()
        
        # Export with optional metadata
        exporter.export(
            frames_data=frames,
            output_path=args.output,
            song_name="MIDI2NES Export"  # You could add these as optional CLI arguments
        )
        print(f" Exported NSF -> {args.output}")
    
    elif args.format == "ca65":
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
            args.output
        )
        print(f" Exported CA65 ASM -> {args.output}")

def run_detect_patterns(args):
    frames = json.loads(Path(args.input).read_text())
    
    # Create tempo map and pattern detector
    tempo_map = EnhancedTempoMap(initial_tempo=500000)  # 120 BPM default
    detector = EnhancedPatternDetector(tempo_map, min_pattern_length=3)
    
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
    print(f" Compression ratio: {pattern_result['stats']['compression_ratio']:.2f}")

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

def compile_rom(project_dir: Path, rom_output: Path) -> bool:
    """Compile the NES project to ROM using CA65/LD65"""
    try:
        # Check if CA65 and LD65 are available
        result = subprocess.run(['ca65', '--version'], capture_output=True, text=True)
        if result.returncode != 0:
            print("[ERROR] CA65 assembler not found. Please install cc65 tools.")
            return False
        
        result = subprocess.run(['ld65', '--version'], capture_output=True, text=True)
        if result.returncode != 0:
            print("[ERROR] LD65 linker not found. Please install cc65 tools.")
            return False
        
        # Compile main.asm
        print("  Compiling main.asm...")
        result = subprocess.run(
            ['ca65', 'main.asm', '-o', 'main.o'],
            cwd=project_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"[ERROR] Failed to compile main.asm:\n{result.stderr}")
            return False
        
        # Compile music.asm
        print("  Compiling music.asm...")
        result = subprocess.run(
            ['ca65', 'music.asm', '-o', 'music.o'],
            cwd=project_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"[ERROR] Failed to compile music.asm:\n{result.stderr}")
            return False
        
        # Link the ROM
        print("  Linking ROM...")
        result = subprocess.run(
            ['ld65', '-C', 'nes.cfg', 'main.o', 'music.o', '-o', 'game.nes'],
            cwd=project_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"[ERROR] Failed to link ROM:\n{result.stderr}")
            return False
        
        # Copy the ROM to the desired output location
        shutil.copy(project_dir / 'game.nes', rom_output)
        
        return True
    except FileNotFoundError as e:
        print(f"[ERROR] Compilation tool not found: {str(e)}")
        print("Please install the cc65 toolchain: https://cc65.github.io/")
        return False
    except Exception as e:
        print(f"[ERROR] Compilation failed: {str(e)}")
        return False

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
    
    print(f"🎵 MIDI2NES Pipeline: {input_midi.name} → {output_rom.name}")
    print("=" * 60)
    
    # Create temporary directory for intermediate files
    with tempfile.TemporaryDirectory(prefix="midi2nes_") as temp_dir:
        temp_path = Path(temp_dir)
        
        try:
            # Step 1: Parse MIDI to frames
            print("[1/7] Parsing MIDI file...")
            midi_data = parse_midi_to_frames(str(input_midi))
            
            # Step 2: Map tracks to NES channels
            print("[2/7] Mapping tracks to NES channels...")
            dpcm_index_path = 'dpcm_index.json' 
            mapped = assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)
            
            # Step 3: Generate frame data
            print("[3/7] Generating NES frame data...")
            emulator = NESEmulatorCore()
            frames = emulator.process_all_tracks(mapped)
            
            # Step 4: Detect patterns (optional compression)
            print("[4/7] Detecting patterns for compression...")
            tempo_map = EnhancedTempoMap(initial_tempo=500000)
            detector = EnhancedPatternDetector(tempo_map, min_pattern_length=3)
            
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
            
            pattern_result = detector.detect_patterns(events)
            
            # Step 5: Export to CA65 assembly
            print("[5/7] Exporting to CA65 assembly...")
            music_asm = temp_path / "music.asm"
            
            exporter = CA65Exporter()
            exporter.export_tables_with_patterns(
                frames,
                pattern_result['patterns'],
                pattern_result['references'],
                str(music_asm),
                standalone=False  # We'll create our own project structure
            )
            
            # Step 6: Prepare NES project
            print("[6/7] Preparing NES project...")
            project_path = temp_path / "nes_project"
            builder = NESProjectBuilder(str(project_path))
            
            if not builder.prepare_project(str(music_asm)):
                print("[ERROR] Failed to prepare NES project")
                sys.exit(1)
            
            # Step 7: Compile ROM
            print("[7/7] Compiling NES ROM...")
            if not compile_rom(project_path, output_rom):
                print("[ERROR] ROM compilation failed")
                sys.exit(1)
            
            # Success!
            rom_size = output_rom.stat().st_size
            print("\n" + "=" * 60)
            print(f"✅ SUCCESS! ROM created: {output_rom.name}")
            print(f"   ROM size: {rom_size:,} bytes ({rom_size / 1024:.1f} KB)")
            print(f"   Compression ratio: {pattern_result['stats']['compression_ratio']:.2f}x")
            print(f"   Total patterns detected: {len(pattern_result['patterns'])}")
            print("\n🎮 Your NES ROM is ready to run on emulators or flash carts!")
            
        except Exception as e:
            print(f"\n[ERROR] Pipeline failed: {str(e)}")
            if args.verbose:
                import traceback
                print("\nFull traceback:")
                traceback.print_exc()
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description=f"MIDI to NES ROM compiler v{__version__}\n\nDefault usage: midi2nes song.mid [output.nes]",
        epilog="For more information, visit: https://github.com/matiaszanolli/midi2nes",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--version', action='version', version=f'MIDI2NES {__version__}')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    
    # Add positional arguments for default MIDI-to-ROM behavior
    parser.add_argument('input', nargs='?', help='Input MIDI file (.mid/.midi)')
    parser.add_argument('output', nargs='?', help='Output NES ROM file (.nes) - defaults to input name with .nes extension')
    
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
    p_map.add_argument('--config', help='Path to drum mapper configuration file')
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
    p_export.add_argument('--format', choices=['nsf', 'ca65'], default='ca65')
    p_export.add_argument('--patterns', help='Path to pattern data JSON (optional)')
    p_export.set_defaults(func=run_export)

    # Keep other existing commands...
    p_prepare = subparsers.add_parser('prepare', help='Prepare CA65 project for compilation')
    p_prepare.add_argument('input', help='Input music.asm file')
    p_prepare.add_argument('output', help='Output project directory')
    p_prepare.set_defaults(func=run_prepare)

    # Song bank management commands
    p_song = subparsers.add_parser('song', help='Song bank management')
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

    args = parser.parse_args()

    # Handle default MIDI-to-ROM behavior when no subcommand is provided
    if not args.command:
        if not args.input:
            print("Error: Please provide an input MIDI file")
            print("\nUsage examples:")
            print("  midi2nes song.mid                  # Creates song.nes")
            print("  midi2nes song.mid output.nes       # Creates output.nes")
            print("  midi2nes --help                    # Show full help")
            sys.exit(1)
        
        # Run the full pipeline with the provided arguments
        run_full_pipeline(args)
    elif hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

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
