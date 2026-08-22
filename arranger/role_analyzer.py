"""
Voice Role Analyzer for NES Arrangement.

Analyzes MIDI tracks to determine their musical role (bass, melody, harmony, etc.)
using both GM instrument hints and musical analysis.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import statistics

from .gm_instruments import MusicalRole, NESChannel, PlayStyle, DutyCycle, get_instrument_mapping


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

        # Now adjust based on actual musical analysis. A plain dict of the 4
        # scoring buckets isn't enough here: GM_INSTRUMENT_MAP curates 19/128
        # programs (Timpani, Orchestra Hit, Agogo, Woodblock, etc.) with
        # role=PERCUSSION or SFX, neither of which is a scoring bucket -- any
        # non-drum-channel track using one of those programs would otherwise
        # KeyError below (#ARR-2026-08-07-1). defaultdict lets the lookups
        # further down (BASS/MELODY/HARMONY/DECORATIVE) read/increment
        # freely without a KeyError; the out-of-bucket GM hint itself is
        # guarded explicitly below so it never becomes a 5th key `max()` can
        # pick (#450/ARR-2026-08-21-3 -- crediting PERCUSSION/SFX here let
        # that key win outright on an unremarkable track's +3.0 alone, since
        # none of the analysis below can ever add to it).
        role_scores = defaultdict(float, {
            MusicalRole.BASS: 0.0,
            MusicalRole.MELODY: 0.0,
            MusicalRole.HARMONY: 0.0,
            MusicalRole.DECORATIVE: 0.0,
        })

        # GM instrument hint -- only credited when it names one of the 4
        # scoring buckets above. `in` never triggers the defaultdict's
        # factory, so an out-of-bucket role (PERCUSSION/SFX) is left
        # genuinely uncontested rather than inserted with a score that
        # could win max() on its own.
        if gm_mapping.role in role_scores:
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

        # Only override the GM-curated channel when the detected role
        # disagrees with GM's own role hint for this instrument. When they
        # agree, the curator's per-instrument choice (e.g. Ocarina/Whistle/
        # Blown Bottle -> TRIANGLE for a breathy timbre, several harmony
        # instruments -> ANY_PULSE for flexible allocation) survives instead
        # of being unconditionally collapsed to the generic 4-bucket
        # role->channel default (#408/ARR-2026-08-06-1). Priority/play-style
        # adjustments below are still role-driven either way.
        channel_override = not (best_role == gm_mapping.role)

        if best_role == MusicalRole.BASS:
            if channel_override:
                analysis.preferred_channel = NESChannel.TRIANGLE
            analysis.priority = max(analysis.priority, 8)
        elif best_role == MusicalRole.MELODY:
            if channel_override:
                analysis.preferred_channel = NESChannel.PULSE1
            analysis.priority = max(analysis.priority, 7)
        elif best_role == MusicalRole.HARMONY:
            if channel_override:
                analysis.preferred_channel = NESChannel.PULSE2
            if analysis.needs_arpeggiation:
                analysis.play_style = PlayStyle.ARPEGGIATE
        elif best_role == MusicalRole.DECORATIVE:
            if channel_override:
                analysis.preferred_channel = NESChannel.PULSE2
            analysis.priority = min(analysis.priority, 4)

    def create_arrangement_plan(self) -> ArrangementPlan:
        """Create a complete arrangement plan for all tracks."""
        plan = ArrangementPlan()

        # Analyze all tracks
        for track_id in self.tracks:
            analysis = self.analyze_track(track_id)
            plan.tracks.append(analysis)

        # Sort by priority (highest first). TrackAnalysis.priority (higher = keep)
        # is the single live drop key — there is no role-name ranking table (#88).
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

            # Drums always get noise + potentially DPCM. Only skip the
            # standard "couldn't be assigned" bookkeeping below when at least
            # one of the two was actually claimed here -- a second drum track
            # finding both already taken used to hit an unconditional
            # `continue`, vanishing with no dropped_tracks entry and no
            # plan.notes diagnostic, unlike every other overflow (#205/ARR-10).
            if track.is_drum_track:
                if not noise_assigned:
                    plan.noise_tracks.append(track.track_id)
                    noise_assigned = True
                    assigned = True
                if not dpcm_assigned:
                    plan.dpcm_tracks.append(track.track_id)
                    dpcm_assigned = True
                    assigned = True
                if assigned:
                    # Also share PULSE2 (not exclusive -- deliberately
                    # doesn't touch pulse2_assigned, so it never blocks a
                    # melodic track from claiming/falling back to PULSE2
                    # below) so GM_DRUM_MAP's PULSE2-mapped percussion
                    # (agogo/cuica/mute+open triangle) can actually reach
                    # PULSE2 instead of always collapsing onto NOISE
                    # (#330/ARR-NEW-6). Safe because _allocate_pulse's
                    # arpeggiation already interleaves multiple simultaneous
                    # notes on one physical pulse channel -- unlike
                    # TRIANGLE, which stays exclusively bass-owned below
                    # since _allocate_triangle is monophonic (naive
                    # lowest-note pick) and has no such collision handling.
                    # Gated on `assigned` (not unconditional) so a drum
                    # track that got neither noise nor DPCM -- fully dropped
                    # (#205/ARR-10) -- doesn't still pick up a PULSE2 slot.
                    plan.pulse2_tracks.append(track.track_id)

            else:
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

                # Live/reachable, unlike the BASS recheck below (#410): #408
                # made GM's own ANY_PULSE curation (gm_instruments.py, e.g.
                # Electric Piano 1/HARMONY, Electric Grand Piano/MELODY)
                # survive into preferred_channel whenever the detected role
                # agrees with GM's role hint, so this branch is exercised by
                # the live pipeline for those instruments, not test-only.
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
                    # #410/ARR-2026-08-06-3: this BASS/triangle recheck is
                    # unreachable from the live analyze_midi_events ->
                    # create_arrangement_plan pipeline. Every GM instrument
                    # mapped to MusicalRole.BASS (gm_instruments.py) is
                    # curated to NESChannel.TRIANGLE, and _determine_role
                    # forces preferred_channel to TRIANGLE for any track it
                    # scores as BASS regardless of GM agreement (:275 above)
                    # -- so a live BASS track always takes the TRIANGLE
                    # branch above (:355-359) first; reaching this fallback
                    # with triangle_assigned still False is impossible for
                    # it. Kept (not removed) because tests/test_role_analyzer.py
                    # exercises _assign_channels directly with hand-built
                    # TrackAnalysis(preferred_channel=PULSE1, role=BASS)
                    # combinations _determine_role itself never produces --
                    # this recheck is real defense for that non-pipeline
                    # input, not dead weight to delete.
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
                    # #409/ARR-2026-08-06-2 (CLOSED): this used to be
                    # `elif not triangle_assigned and track.role !=
                    # MusicalRole.MELODY:`, letting any non-MELODY role
                    # (HARMONY, DECORATIVE) claim triangle as a last resort --
                    # not just BASS, contradicting the "triangle is reserved
                    # for bass" invariant tests/test_role_analyzer.py already
                    # documented. Because plan.tracks is sorted by priority
                    # descending (create_arrangement_plan) but this exclusion
                    # was role-based rather than priority-based, a
                    # HIGHER-priority MELODY track processed earlier could be
                    # dropped for lack of a channel while a LOWER-priority
                    # HARMONY/DECORATIVE track processed later still grabbed
                    # the now-idle triangle -- the opposite of "highest
                    # priority survives". Triangle overflow for a non-BASS
                    # role is no longer offered here at all; the BASS branch
                    # above this if/elif chain is the only path onto triangle
                    # once pulse1/pulse2 are full, restoring the documented
                    # BASS-only invariant. A non-BASS track that can't fit now
                    # correctly falls through to dropped_tracks below, same as
                    # any other overflow.

            # Track couldn't be assigned
            if not assigned:
                plan.dropped_tracks.append(track.track_id)
                plan.notes.append(
                    f"Track {track.track_id} ({track.name}): Dropped - no channels available"
                )

    @staticmethod
    def print_analysis(plan: ArrangementPlan):
        """Print a human-readable analysis.

        A staticmethod since it only ever reads `plan` -- callable without
        an analyzer instance (arrange_for_nes's verbose path calls it
        directly, #451/ARR-2026-08-21-4); still callable as
        `analyzer.print_analysis(plan)` for existing callers/examples.
        """
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
