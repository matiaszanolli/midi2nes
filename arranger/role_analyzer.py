"""
Voice Role Analyzer for NES Arrangement.

Analyzes MIDI tracks to determine their musical role (bass, melody, harmony, etc.)
using both GM instrument hints and musical analysis.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import statistics

from .gm_instruments import (
    MusicalRole, NESChannel, PlayStyle, DutyCycle,
    get_instrument_mapping, get_drum_mapping,
    InstrumentMapping, DrumMapping,
)


@dataclass
class NoteInfo:
    """Information about a single note."""
    pitch: int
    velocity: int
    start_frame: int
    end_frame: int
    channel: int = 0
    program: int = 0  # GM program number

    @property
    def duration(self) -> int:
        return self.end_frame - self.start_frame


@dataclass
class TrackAnalysis:
    """Analysis results for a single track/voice."""
    track_id: int
    name: str = ""

    # GM hints
    program: int = 0
    is_drum_track: bool = False

    # Detected role
    role: MusicalRole = MusicalRole.HARMONY
    confidence: float = 0.0

    # Musical characteristics
    avg_pitch: float = 60.0
    pitch_range: Tuple[int, int] = (60, 72)
    avg_velocity: float = 80.0
    note_density: float = 0.0  # Notes per second
    avg_duration: float = 0.0  # Average note duration in frames
    total_notes: int = 0

    # NES assignment
    preferred_channel: NESChannel = NESChannel.FLEXIBLE
    duty_cycle: Optional[DutyCycle] = None
    play_style: PlayStyle = PlayStyle.SUSTAIN
    priority: int = 5

    # Additional flags
    is_monophonic: bool = True
    max_polyphony: int = 1
    needs_arpeggiation: bool = False


@dataclass
class ArrangementPlan:
    """Complete arrangement plan for all tracks."""
    tracks: List[TrackAnalysis] = field(default_factory=list)

    # Channel assignments
    pulse1_tracks: List[int] = field(default_factory=list)
    pulse2_tracks: List[int] = field(default_factory=list)
    triangle_tracks: List[int] = field(default_factory=list)
    noise_tracks: List[int] = field(default_factory=list)
    dpcm_tracks: List[int] = field(default_factory=list)

    # Dropped tracks (couldn't fit)
    dropped_tracks: List[int] = field(default_factory=list)

    # Notes about the arrangement
    notes: List[str] = field(default_factory=list)


class VoiceRoleAnalyzer:
    """
    Analyzes MIDI data to determine musical roles and NES channel assignments.

    The analyzer works in phases:
    1. Extract note information from MIDI events
    2. Analyze each track's musical characteristics
    3. Use GM hints + analysis to determine roles
    4. Assign tracks to NES channels by priority
    """

    # Pitch thresholds for role detection
    BASS_THRESHOLD = 48      # Below E2 is definitely bass
    LOW_MID_THRESHOLD = 60   # Below C4 is low-mid
    HIGH_THRESHOLD = 72      # Above C5 is high

    # Density thresholds (notes per second at 60fps)
    SPARSE_DENSITY = 0.5     # Less than 1 note per 2 seconds
    DENSE_DENSITY = 4.0      # More than 4 notes per second

    def __init__(self):
        self.tracks: Dict[int, List[NoteInfo]] = defaultdict(list)
        self.track_programs: Dict[int, int] = {}
        self.track_names: Dict[int, str] = {}
        self.drum_tracks: set = set()
        self.tempo_fps: float = 60.0  # Frames per second

    def add_note(self, track_id: int, note: NoteInfo):
        """Add a note to a track for analysis."""
        self.tracks[track_id].append(note)

    def set_track_program(self, track_id: int, program: int):
        """Set the GM program number for a track."""
        self.track_programs[track_id] = program

    def set_track_name(self, track_id: int, name: str):
        """Set the track name."""
        self.track_names[track_id] = name

    def mark_drum_track(self, track_id: int):
        """Mark a track as drums (GM channel 10)."""
        self.drum_tracks.add(track_id)

    def analyze_track(self, track_id: int) -> TrackAnalysis:
        """Analyze a single track and determine its role."""
        notes = self.tracks.get(track_id, [])
        if not notes:
            return TrackAnalysis(track_id=track_id)

        analysis = TrackAnalysis(
            track_id=track_id,
            name=self.track_names.get(track_id, f"Track {track_id}"),
            program=self.track_programs.get(track_id, 0),
            is_drum_track=track_id in self.drum_tracks,
            total_notes=len(notes),
        )

        # Handle drum tracks specially
        if analysis.is_drum_track:
            return self._analyze_drum_track(analysis, notes)

        # Calculate pitch statistics
        pitches = [n.pitch for n in notes]
        analysis.avg_pitch = statistics.mean(pitches)
        analysis.pitch_range = (min(pitches), max(pitches))

        # Calculate velocity
        velocities = [n.velocity for n in notes]
        analysis.avg_velocity = statistics.mean(velocities)

        # Calculate note density
        if notes:
            total_frames = max(n.end_frame for n in notes) - min(n.start_frame for n in notes)
            if total_frames > 0:
                analysis.note_density = len(notes) / (total_frames / self.tempo_fps)

        # Calculate average duration
        durations = [n.duration for n in notes]
        analysis.avg_duration = statistics.mean(durations)

        # Check polyphony (notes overlapping)
        analysis.max_polyphony = self._calculate_max_polyphony(notes)
        analysis.is_monophonic = analysis.max_polyphony <= 1
        analysis.needs_arpeggiation = analysis.max_polyphony > 1

        # Determine role using GM hints and analysis
        self._determine_role(analysis)

        return analysis

    def _analyze_drum_track(self, analysis: TrackAnalysis, notes: List[NoteInfo]) -> TrackAnalysis:
        """Special analysis for drum tracks."""
        analysis.role = MusicalRole.PERCUSSION
        analysis.preferred_channel = NESChannel.NOISE  # Primary
        analysis.play_style = PlayStyle.STACCATO
        analysis.priority = 8  # Drums are important
        analysis.confidence = 1.0

        # Check for kick drums that need DPCM
        has_kicks = any(n.pitch in [35, 36] for n in notes)
        has_snares = any(n.pitch in [38, 40] for n in notes)

        if has_kicks or has_snares:
            analysis.notes = "Uses DPCM for kicks/snares"

        return analysis

    def _calculate_max_polyphony(self, notes: List[NoteInfo]) -> int:
        """Calculate maximum simultaneous notes."""
        if not notes:
            return 0

        events = []
        for note in notes:
            events.append((note.start_frame, 1))   # Note on
            events.append((note.end_frame, -1))    # Note off

        events.sort(key=lambda x: (x[0], -x[1]))  # Note offs before ons at same time

        current = 0
        max_poly = 0
        for _, delta in events:
            current += delta
            max_poly = max(max_poly, current)

        return max_poly

    def _determine_role(self, analysis: TrackAnalysis):
        """Determine the musical role using GM hints and analysis."""
        # Start with GM hint if available
        gm_mapping = get_instrument_mapping(analysis.program)

        # Base values from GM mapping
        analysis.preferred_channel = gm_mapping.channel
        analysis.duty_cycle = gm_mapping.duty
        analysis.play_style = gm_mapping.style
        analysis.priority = gm_mapping.priority

        # Now adjust based on actual musical analysis
        role_scores = {
            MusicalRole.BASS: 0.0,
            MusicalRole.MELODY: 0.0,
            MusicalRole.HARMONY: 0.0,
            MusicalRole.DECORATIVE: 0.0,
        }

        # GM instrument hint
        role_scores[gm_mapping.role] += 3.0

        # Pitch analysis
        if analysis.avg_pitch < self.BASS_THRESHOLD:
            role_scores[MusicalRole.BASS] += 4.0
        elif analysis.avg_pitch < self.LOW_MID_THRESHOLD:
            role_scores[MusicalRole.BASS] += 1.0
            role_scores[MusicalRole.HARMONY] += 1.0
        elif analysis.avg_pitch > self.HIGH_THRESHOLD:
            role_scores[MusicalRole.MELODY] += 2.0
            role_scores[MusicalRole.DECORATIVE] += 1.0
        else:
            role_scores[MusicalRole.MELODY] += 1.0
            role_scores[MusicalRole.HARMONY] += 1.0

        # Note density analysis
        if analysis.note_density < self.SPARSE_DENSITY:
            role_scores[MusicalRole.HARMONY] += 1.0  # Sustained pads
        elif analysis.note_density > self.DENSE_DENSITY:
            role_scores[MusicalRole.MELODY] += 1.0  # Active melodic line

        # Velocity analysis (louder = more prominent)
        if analysis.avg_velocity > 100:
            role_scores[MusicalRole.MELODY] += 1.0
        elif analysis.avg_velocity < 60:
            role_scores[MusicalRole.DECORATIVE] += 1.0

        # Polyphony analysis
        if analysis.max_polyphony > 2:
            role_scores[MusicalRole.HARMONY] += 2.0  # Chords
            analysis.needs_arpeggiation = True

        # Find highest scoring role
        best_role = max(role_scores, key=role_scores.get)
        total_score = sum(role_scores.values())

        analysis.role = best_role
        analysis.confidence = role_scores[best_role] / total_score if total_score > 0 else 0.0

        # Override channel preference based on detected role
        if best_role == MusicalRole.BASS:
            analysis.preferred_channel = NESChannel.TRIANGLE
            analysis.priority = max(analysis.priority, 8)
        elif best_role == MusicalRole.MELODY:
            analysis.preferred_channel = NESChannel.PULSE1
            analysis.priority = max(analysis.priority, 7)
        elif best_role == MusicalRole.HARMONY:
            analysis.preferred_channel = NESChannel.PULSE2
            if analysis.needs_arpeggiation:
                analysis.play_style = PlayStyle.ARPEGGIATE
        elif best_role == MusicalRole.DECORATIVE:
            analysis.preferred_channel = NESChannel.PULSE2
            analysis.priority = min(analysis.priority, 4)

    def create_arrangement_plan(self) -> ArrangementPlan:
        """Create a complete arrangement plan for all tracks."""
        plan = ArrangementPlan()

        # Analyze all tracks
        for track_id in self.tracks:
            analysis = self.analyze_track(track_id)
            plan.tracks.append(analysis)

        # Sort by priority (highest first)
        plan.tracks.sort(key=lambda t: t.priority, reverse=True)

        # Assign channels
        self._assign_channels(plan)

        return plan

    def _assign_channels(self, plan: ArrangementPlan):
        """Assign tracks to NES channels based on role and priority."""
        pulse1_assigned = False
        pulse2_assigned = False
        triangle_assigned = False
        noise_assigned = False
        dpcm_assigned = False

        for track in plan.tracks:
            assigned = False

            # Drums always get noise + potentially DPCM
            if track.is_drum_track:
                if not noise_assigned:
                    plan.noise_tracks.append(track.track_id)
                    noise_assigned = True
                    assigned = True
                if not dpcm_assigned:
                    plan.dpcm_tracks.append(track.track_id)
                    dpcm_assigned = True
                continue

            # Try preferred channel first
            if track.preferred_channel == NESChannel.TRIANGLE:
                if not triangle_assigned:
                    plan.triangle_tracks.append(track.track_id)
                    triangle_assigned = True
                    assigned = True

            elif track.preferred_channel == NESChannel.PULSE1:
                if not pulse1_assigned:
                    plan.pulse1_tracks.append(track.track_id)
                    pulse1_assigned = True
                    assigned = True
                elif not pulse2_assigned:
                    plan.pulse2_tracks.append(track.track_id)
                    pulse2_assigned = True
                    assigned = True
                    plan.notes.append(f"Track {track.track_id} ({track.name}): Pulse1 full, using Pulse2")

            elif track.preferred_channel == NESChannel.PULSE2:
                if not pulse2_assigned:
                    plan.pulse2_tracks.append(track.track_id)
                    pulse2_assigned = True
                    assigned = True
                elif not pulse1_assigned:
                    plan.pulse1_tracks.append(track.track_id)
                    pulse1_assigned = True
                    assigned = True
                    plan.notes.append(f"Track {track.track_id} ({track.name}): Pulse2 full, using Pulse1")

            elif track.preferred_channel in (NESChannel.ANY_PULSE, NESChannel.FLEXIBLE):
                if not pulse1_assigned:
                    plan.pulse1_tracks.append(track.track_id)
                    pulse1_assigned = True
                    assigned = True
                elif not pulse2_assigned:
                    plan.pulse2_tracks.append(track.track_id)
                    pulse2_assigned = True
                    assigned = True

            # If still not assigned, try any available channel
            if not assigned:
                if track.role == MusicalRole.BASS and not triangle_assigned:
                    plan.triangle_tracks.append(track.track_id)
                    triangle_assigned = True
                    assigned = True
                elif not pulse1_assigned:
                    plan.pulse1_tracks.append(track.track_id)
                    pulse1_assigned = True
                    assigned = True
                elif not pulse2_assigned:
                    plan.pulse2_tracks.append(track.track_id)
                    pulse2_assigned = True
                    assigned = True
                elif not triangle_assigned and track.role != MusicalRole.MELODY:
                    plan.triangle_tracks.append(track.track_id)
                    triangle_assigned = True
                    assigned = True

            # Track couldn't be assigned
            if not assigned:
                plan.dropped_tracks.append(track.track_id)
                plan.notes.append(
                    f"Track {track.track_id} ({track.name}): Dropped - no channels available"
                )

    def print_analysis(self, plan: ArrangementPlan):
        """Print a human-readable analysis."""
        print("\n" + "=" * 60)
        print("NES ARRANGEMENT ANALYSIS")
        print("=" * 60)

        for track in plan.tracks:
            gm = get_instrument_mapping(track.program)
            print(f"\nTrack {track.track_id}: {track.name}")
            print(f"  GM Instrument: {gm.name} (#{track.program})")
            print(f"  Detected Role: {track.role.name} (confidence: {track.confidence:.0%})")
            print(f"  Pitch Range: {track.pitch_range[0]}-{track.pitch_range[1]} (avg: {track.avg_pitch:.0f})")
            print(f"  Note Density: {track.note_density:.2f} notes/sec")
            print(f"  Max Polyphony: {track.max_polyphony}")
            print(f"  → NES Channel: {track.preferred_channel.value}")
            print(f"  → Play Style: {track.play_style.name}")
            if track.needs_arpeggiation:
                print(f"  ⚠ Needs arpeggiation")

        print("\n" + "-" * 60)
        print("CHANNEL ASSIGNMENTS:")
        print(f"  Pulse1:   {plan.pulse1_tracks or 'None'}")
        print(f"  Pulse2:   {plan.pulse2_tracks or 'None'}")
        print(f"  Triangle: {plan.triangle_tracks or 'None'}")
        print(f"  Noise:    {plan.noise_tracks or 'None'}")
        print(f"  DPCM:     {plan.dpcm_tracks or 'None'}")

        if plan.dropped_tracks:
            print(f"\n  ⚠ DROPPED: {plan.dropped_tracks}")

        if plan.notes:
            print("\nNotes:")
            for note in plan.notes:
                print(f"  • {note}")

        print("=" * 60)
