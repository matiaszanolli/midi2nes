"""
Enhanced TempoMap implementation for midi2nes
Provides advanced tempo tracking, validation, and optimization features
"""

import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
from enum import Enum
from constants import FRAME_MS, FRAME_RATE_HZ


# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@dataclass
class TempoValidationConfig:
    """Configuration for tempo change validation"""
    min_tempo_bpm: float = 20.0
    max_tempo_bpm: float = 300.0
    min_duration_frames: int = 1
    max_duration_frames: int = FRAME_RATE_HZ * 60  # 1 minute
    max_tempo_change_ratio: float = 2.0  # Maximum allowed tempo change ratio


class TempoChangeType(Enum):
    """Types of tempo changes supported"""
    IMMEDIATE = "immediate"
    LINEAR = "linear"
    CURVE = "curve"
    PATTERN_SYNC = "pattern_sync"


class TempoOptimizationStrategy(Enum):
    """Optimization strategies for tempo changes"""
    MINIMIZE_CHANGES = "minimize_changes"
    SMOOTH_TRANSITIONS = "smooth_transitions"
    PATTERN_ALIGNED = "pattern_aligned"
    FRAME_ALIGNED = "frame_aligned"


class TempoValidationError(Exception):
    """Exception raised when tempo validation fails"""
    pass


class TempoChange:
    """Represents a single tempo change event"""
    def __init__(self, tick: int, tempo: int, 
                 change_type: TempoChangeType = TempoChangeType.IMMEDIATE,
                 duration_ticks: int = 0, curve_factor: float = 1.0,
                 pattern_id: Optional[str] = None):
        self.tick = tick
        self.tempo = tempo
        self.change_type = change_type
        self.duration_ticks = duration_ticks
        self.curve_factor = curve_factor
        self.pattern_id = pattern_id
        self.end_tick = tick + duration_ticks if duration_ticks > 0 else tick


class PatternTempoInfo:
    """Tempo information specific to a pattern"""
    def __init__(self, pattern_id: str, base_tempo: int, 
                 variations: List[TempoChange] = None):
        self.pattern_id = pattern_id
        self.base_tempo = base_tempo
        self.variations = variations or []


class TempoMap:
    """Base TempoMap class - maintains compatibility with existing code"""
    def __init__(self, initial_tempo=500000, ticks_per_beat=480):
        """
        Initialize TempoMap with default tempo (120 BPM = 500000 microseconds per beat)
        
        Args:
            initial_tempo: Microseconds per quarter note (500000 = 120 BPM)
            ticks_per_beat: MIDI ticks per quarter note
        """
        self.tempo_changes = [(0, initial_tempo)]
        self.ticks_per_beat = ticks_per_beat
        self._time_cache = {}
        
    def add_tempo_change(self, tick: int, tempo: int):
        """Add a tempo change at the specified tick"""
        self.tempo_changes.append((tick, tempo))
        self.tempo_changes.sort()
        self._time_cache = {}
        
    def get_tempo_at_tick(self, tick: int) -> int:
        """Get the active tempo at a specific tick"""
        active_tempo = self.tempo_changes[0][1]
        for change_tick, tempo in self.tempo_changes:
            if change_tick <= tick:
                active_tempo = tempo
            else:
                break
        return active_tempo
        
    def calculate_time_ms(self, start_tick: int, end_tick: int) -> float:
        """Calculate time in milliseconds between two ticks"""
        if start_tick == end_tick:
            return 0.0
            
        cache_key = (start_tick, end_tick)
        if cache_key in self._time_cache:
            return self._time_cache[cache_key]
            
        total_time_ms = 0.0
        current_tick = start_tick
        current_tempo = self.get_tempo_at_tick(start_tick)
        
        for next_tick, next_tempo in self.tempo_changes:
            if next_tick <= start_tick:
                current_tempo = next_tempo
                continue
                
            if next_tick >= end_tick:
                break
                
            segment_ticks = next_tick - current_tick
            segment_time = self._ticks_to_ms(segment_ticks, current_tempo)
            total_time_ms += segment_time
            
            current_tick = next_tick
            current_tempo = next_tempo
            
        if current_tick < end_tick:
            remaining_ticks = end_tick - current_tick
            remaining_time = self._ticks_to_ms(remaining_ticks, current_tempo)
            total_time_ms += remaining_time
            
        self._time_cache[cache_key] = total_time_ms
        return total_time_ms
        
    def _ticks_to_ms(self, ticks: int, tempo_microseconds: int) -> float:
        """Convert ticks to milliseconds for a given tempo"""
        # Keep floating point precision for accurate time calculation
        microseconds_per_tick = tempo_microseconds / self.ticks_per_beat
        return (ticks * microseconds_per_tick) / 1000.0
        
    def get_frame_for_tick(self, tick):
        """Get frame number ensuring frame alignment"""
        time_ms = self.calculate_time_ms(0, tick)
        return round(time_ms / FRAME_MS)
        
    def get_tempo_bpm_at_tick(self, tick: int) -> float:
        """Get tempo in BPM at a specific tick"""
        tempo_microseconds = self.get_tempo_at_tick(tick)
        return 60_000_000 / tempo_microseconds
        
    def get_debug_info(self) -> Dict:
        """Get debug information about tempo changes"""
        info = {
            "ticks_per_beat": self.ticks_per_beat,
            "tempo_changes": []
        }
        
        for tick, tempo in self.tempo_changes:
            bpm = 60_000_000 / tempo
            info["tempo_changes"].append({
                "tick": tick,
                "tempo_microseconds": tempo,
                "bpm": round(bpm, 2),
                "time_ms": self.calculate_time_ms(0, tick),
                "frame": self.get_frame_for_tick(tick)
            })
            
        return info


class EnhancedTempoMap(TempoMap):
    def __init__(self, initial_tempo=500000, ticks_per_beat=480,
                 validation_config: Optional[TempoValidationConfig] = None,
                 optimization_strategy: TempoOptimizationStrategy = TempoOptimizationStrategy.FRAME_ALIGNED):
        self.validation_config = validation_config or TempoValidationConfig()
        initial_bpm = 60_000_000 / initial_tempo
        if not (self.validation_config.min_tempo_bpm <= initial_bpm <= 
                self.validation_config.max_tempo_bpm):
            raise TempoValidationError(
                f"Initial tempo {initial_bpm:.1f} BPM outside valid range "
                f"[{self.validation_config.min_tempo_bpm}, "
                f"{self.validation_config.max_tempo_bpm}]"
            )
        
        super().__init__(initial_tempo, ticks_per_beat)
        self.optimization_strategy = optimization_strategy
        self.enhanced_changes = [TempoChange(0, initial_tempo)]
        self.pattern_tempos = {}
        self.loop_points = {}
        self._frame_cache = {}
        self.optimization_stats = defaultdict(int)

    def add_tempo_change(self, tick: int, tempo: int, 
                        change_type: TempoChangeType = TempoChangeType.IMMEDIATE,
                        duration_ticks: int = 0):
        """Add a tempo change with frame alignment"""
        if tick == 0:
            raise TempoValidationError("Cannot add tempo change at tick 0")
            
        # Create initial change
        change = TempoChange(tick, tempo, change_type, duration_ticks)
        
        # First validate basic tempo properties
        self._validate_basic_tempo(change)
        
        # Validate duration for gradual changes
        if duration_ticks > 0:
            frames = self.get_frame_for_tick(duration_ticks)
            if not (self.validation_config.min_duration_frames <= frames <= 
                    self.validation_config.max_duration_frames):
                raise TempoValidationError(
                    f"Change duration {frames} frames outside valid range "
                    f"[{self.validation_config.min_duration_frames}, "
                    f"{self.validation_config.max_duration_frames}]"
                )
        
        # If frame alignment is enabled, check alignment
        original_tick = tick
        if (self.optimization_strategy == TempoOptimizationStrategy.FRAME_ALIGNED and
            change_type == TempoChangeType.IMMEDIATE):
            time_ms = self.calculate_time_ms(0, tick)
            remainder = time_ms % FRAME_MS
            
            if remainder > 0.001:  # Not aligned with frame boundary
                # Try to find aligned tick
                frame_number = round(time_ms / FRAME_MS)
                target_time = frame_number * FRAME_MS
                
                # Binary search for aligned tick
                left = max(0, tick - self.ticks_per_beat)
                right = tick + self.ticks_per_beat
                best_tick = tick
                best_diff = remainder
                
                while left <= right:
                    mid = (left + right) // 2
                    test_time = self.calculate_time_ms(0, mid)
                    diff = abs(test_time % FRAME_MS)
                    
                    if diff < best_diff:
                        best_diff = diff
                        best_tick = mid
                        
                    if diff < 0.001:  # Found exact match
                        break
                        
                    if test_time < target_time:
                        left = mid + 1
                    else:
                        right = mid - 1
                
                # If we couldn't find a good alignment, raise error
                if best_diff > 0.001:
                    raise TempoValidationError(
                        f"Could not align tempo change at tick {original_tick} to frame boundary"
                    )
                    
                change.tick = best_tick
        
        # Add to base tempo map
        super().add_tempo_change(change.tick, tempo)
        
        # Add to enhanced changes
        self.enhanced_changes.append(change)
        self.enhanced_changes.sort(key=lambda x: x.tick)
        
        # Handle gradual changes
        if change_type != TempoChangeType.IMMEDIATE:
            self._create_gradual_change_steps(change)
        
        # Clear caches
        self._time_cache = {}
        self._frame_cache = {}
        
    def _validate_basic_tempo(self, change: TempoChange):
        """Validate basic tempo properties"""
        # Check BPM range
        bpm = round(60_000_000 / change.tempo, 6)
        if not (self.validation_config.min_tempo_bpm <= bpm <= 
                self.validation_config.max_tempo_bpm):
            raise TempoValidationError(
                f"Tempo {bpm:.1f} BPM outside valid range "
                f"[{self.validation_config.min_tempo_bpm}, "
                f"{self.validation_config.max_tempo_bpm}]"
            )
        
        # Check tempo change ratio for non-initial changes
        if change.tick > 0:
            prev_tempo = self.get_tempo_at_tick(change.tick - 1)
            if prev_tempo > 0:
                ratio = max(change.tempo / prev_tempo, prev_tempo / change.tempo)
                if ratio > self.validation_config.max_tempo_change_ratio:
                    raise TempoValidationError(
                        f"Tempo change ratio {ratio:.2f} exceeds maximum "
                        f"{self.validation_config.max_tempo_change_ratio}"
                    )

    def _validate_tempo_change(self, change: TempoChange):
        """Validate a tempo change against configuration rules"""
        # First check BPM range
        bpm = round(60_000_000 / change.tempo, 6)  # Round to 6 decimal places
        if not (self.validation_config.min_tempo_bpm <= bpm <= 
                self.validation_config.max_tempo_bpm):
            raise TempoValidationError(
                f"Tempo {bpm:.1f} BPM outside valid range "
                f"[{self.validation_config.min_tempo_bpm}, "
                f"{self.validation_config.max_tempo_bpm}]"
            )
        
        # Check duration if applicable
        if change.duration_ticks > 0:
            frames = self.get_frame_for_tick(change.duration_ticks)
            if not (self.validation_config.min_duration_frames <= frames <= 
                    self.validation_config.max_duration_frames):
                raise TempoValidationError(
                    f"Change duration {frames} frames outside valid range "
                    f"[{self.validation_config.min_duration_frames}, "
                    f"{self.validation_config.max_duration_frames}]"
                )
        
        # Check tempo change ratio for non-initial changes
        if change.tick > 0:
            prev_tempo = self.get_tempo_at_tick(change.tick - 1)
            if prev_tempo > 0:
                ratio = max(change.tempo / prev_tempo, prev_tempo / change.tempo)
                if ratio > self.validation_config.max_tempo_change_ratio:
                    raise TempoValidationError(
                        f"Tempo change ratio {ratio:.2f} exceeds maximum "
                        f"{self.validation_config.max_tempo_change_ratio}"
                    )
        
        # Frame boundary validation - only check if frame alignment is enabled
        if (self.optimization_strategy == TempoOptimizationStrategy.FRAME_ALIGNED and
            change.change_type == TempoChangeType.IMMEDIATE):
            frame_time = self.calculate_time_ms(0, change.tick)
            remainder = frame_time % FRAME_MS
            if remainder > 0.001:  # Allow 1 microsecond tolerance
                raise TempoValidationError(
                    f"Tempo change at tick {change.tick} not aligned with frame "
                    f"boundary (off by {remainder:.3f}ms)"
                )
    
    def get_tempo_at_tick(self, tick: int) -> int:
        """Override to ensure correct tempo retrieval"""
        # Use parent class implementation for accurate tempo lookup
        return super().get_tempo_at_tick(tick)

    def _validate_frame_boundaries(self, tick: int, tempo: int):
        """Validate that tempo changes align with frame boundaries"""
        frame_time = self.calculate_time_ms(0, tick)
        if frame_time % FRAME_MS > 0.1:  # Allow small rounding errors
            raise TempoValidationError(
                f"Tempo change at tick {tick} does not align with frame boundary"
            )
                    
    def _create_gradual_change_steps(self, change: TempoChange):
        """Create intermediate steps for gradual tempo changes"""
        if change.duration_ticks <= 0:
            return
            
        start_tempo = self.get_tempo_at_tick(change.tick)
        steps = max(1, change.duration_ticks // (self.ticks_per_beat // 4))
        
        for i in range(steps + 1):
            current_tick = change.tick + (i * change.duration_ticks // steps)
            progress = i / steps
            
            if change.change_type == TempoChangeType.LINEAR:
                current_tempo = self._calculate_linear_tempo(
                    start_tempo, change.tempo, progress
                )
            elif change.change_type == TempoChangeType.CURVE:
                current_tempo = self._calculate_curved_tempo(
                    start_tempo, change.tempo, progress, change.curve_factor
                )
            else:
                current_tempo = change.tempo
                
            # Update base TempoMap's tempo changes
            if i > 0:  # Skip first step as it's already at the start tempo
                super().add_tempo_change(current_tick, current_tempo)
            
    def _calculate_linear_tempo(self, start_tempo: int, end_tempo: int, 
                              progress: float) -> int:
        """Calculate intermediate tempo for linear changes"""
        return int(start_tempo + (end_tempo - start_tempo) * progress)
        
    def _calculate_curved_tempo(self, start_tempo: int, end_tempo: int, 
                            progress: float, curve_factor: float) -> int:
        """Calculate intermediate tempo for curved changes"""
        curved_progress = pow(progress, curve_factor)
        raw_tempo = start_tempo + (end_tempo - start_tempo) * curved_progress
        # Quantize to 16 microsecond steps
        return (int(raw_tempo) // 16) * 16
        
    def _calculate_pattern_sync_tempo(self, start_tempo: int, end_tempo: int, 
                                    progress: float) -> int:
        """Calculate tempo for pattern-synchronized changes using smoothstep"""
        smooth_progress = progress * progress * (3 - 2 * progress)
        return int(start_tempo + (end_tempo - start_tempo) * smooth_progress)
        
    def add_pattern_tempo(self, pattern_id: str, base_tempo: int, 
                        variations: List[TempoChange] = None):
        """Add pattern-specific tempo information"""
        self.pattern_tempos[pattern_id] = PatternTempoInfo(
            pattern_id, base_tempo, variations or []
        )
        
    def register_loop_point(self, loop_id: str, start_tick: int, end_tick: int):
        """Register tempo state for loop points"""
        start_tempo = self.get_tempo_at_tick(start_tick)
        end_tempo = self.get_tempo_at_tick(end_tick)
        
        self.loop_points[loop_id] = {
            'start': {'tick': start_tick, 'tempo': start_tempo},
            'end': {'tick': end_tick, 'tempo': end_tempo}
        }
        
    def get_enhanced_tempo_at_tick(self, tick: int, 
                                  pattern_context: Optional[str] = None) -> int:
        """Get tempo at tick, considering pattern context if provided"""
        base_tempo = self.get_tempo_at_tick(tick)
        
        if pattern_context and pattern_context in self.pattern_tempos:
            pattern_info = self.pattern_tempos[pattern_context]
            # Apply pattern-specific variations
            for variation in pattern_info.variations:
                if variation.tick <= tick <= variation.end_tick:
                    progress = (tick - variation.tick) / variation.duration_ticks
                    return self._calculate_pattern_sync_tempo(
                        base_tempo, variation.tempo, progress
                    )
        
        return base_tempo
    
    def optimize_pattern_tempos(self):
        """Optimize tempo changes within patterns"""
        for pattern_id, pattern_info in self.pattern_tempos.items():
            base_tempo = pattern_info.base_tempo
            optimized_variations = []
            
            for var in pattern_info.variations:
                # Only keep variations that make a significant difference
                if abs(var.tempo - base_tempo) / base_tempo > 0.05:  # 5% threshold
                    # Align variation to frame boundary
                    frame_time = self.calculate_time_ms(0, var.tick)
                    frame_number = frame_time / FRAME_MS
                    aligned_frame = round(frame_number)
                    aligned_time = aligned_frame * FRAME_MS
                    aligned_tick = self._find_tick_at_time(aligned_time)
                    
                    var.tick = aligned_tick
                    optimized_variations.append(var)
                    self.optimization_stats['pattern_tempo_optimizations'] += 1
                    
            self.pattern_tempos[pattern_id] = PatternTempoInfo(
                pattern_id, base_tempo, optimized_variations
            )
        
    def _minimize_tempo_changes(self):
        """Reduce number of tempo changes by combining similar changes"""
        i = 0
        while i < len(self.tempo_changes) - 1:
            current_tempo = self.tempo_changes[i][1]
            next_tempo = self.tempo_changes[i + 1][1]
            
            if abs(current_tempo - next_tempo) / current_tempo < 0.05:
                # Combine changes if difference is less than 5%
                self.tempo_changes.pop(i + 1)
                self.optimization_stats['changes_combined'] += 1
            else:
                i += 1
                
    def _smooth_tempo_transitions(self):
        """Add intermediate steps for large tempo changes"""
        new_changes = []
        
        for i in range(len(self.tempo_changes) - 1):
            current_tick, current_tempo = self.tempo_changes[i]
            next_tick, next_tempo = self.tempo_changes[i + 1]
            new_changes.append((current_tick, current_tempo))
            
            ratio = max(current_tempo / next_tempo, next_tempo / current_tempo)
            
            if ratio > 1.5:  # Add intermediate steps for large changes
                steps = int(ratio * 2)
                step_ticks = (next_tick - current_tick) / steps
                
                for step in range(1, steps):
                    progress = step / steps
                    intermediate_tempo = self._calculate_linear_tempo(
                        current_tempo, next_tempo, progress
                    )
                    intermediate_tick = current_tick + int(step * step_ticks)
                    new_changes.append((intermediate_tick, intermediate_tempo))
                    self.optimization_stats['smoothing_steps_added'] += 1
                    
        new_changes.append(self.tempo_changes[-1])
        self.tempo_changes = new_changes

    def _align_to_frames(self):
        """Align tempo changes with frame boundaries"""
        aligned_changes = []
        
        for tick, tempo in self.tempo_changes:
            frame_time = self.calculate_time_ms(0, tick)
            frame_number = frame_time / FRAME_MS
            aligned_frame = round(frame_number)
            aligned_time = aligned_frame * FRAME_MS
            
            # Binary search with proper bounds
            left = max(0, tick - self.ticks_per_beat)
            right = tick + self.ticks_per_beat
            aligned_tick = tick  # Default to original tick
            
            while left <= right:
                mid = (left + right) // 2
                mid_time = self.calculate_time_ms(0, mid)
                
                if abs(mid_time - aligned_time) < 0.001:  # Within 1 microsecond
                    aligned_tick = mid
                    break
                elif mid_time < aligned_time:
                    left = mid + 1
                else:
                    right = mid - 1
                    
            aligned_changes.append((aligned_tick, tempo))
        
        if aligned_changes:  # Only update if we have changes
            self.tempo_changes = sorted(aligned_changes)

    def optimize_tempo_changes(self):
        """Optimize tempo changes based on selected strategy"""
        if not self.optimization_strategy:
            return
                
        if self.optimization_strategy == TempoOptimizationStrategy.MINIMIZE_CHANGES:
            self._minimize_tempo_changes()
        elif self.optimization_strategy == TempoOptimizationStrategy.SMOOTH_TRANSITIONS:
            self._smooth_tempo_transitions()
        elif self.optimization_strategy == TempoOptimizationStrategy.FRAME_ALIGNED:
            # For frame alignment, we need to:
            # 1. Clear any cached values
            self._time_cache = {}
            self._frame_cache = {}
            
            # 2. Perform the alignment
            self._align_to_frames()
                
        # Clear caches after optimization
        self._time_cache = {}
        self._frame_cache = {}

    def _find_frame_aligned_tick(self, target_time_ms: float) -> int:
        """Find tick that results in the target frame time using iterative approach"""
        
        # Start with a reasonable approximation
        initial_tempo_us = self.get_tempo_at_tick(0)
        ticks_per_ms = (self.ticks_per_beat * 1000) / initial_tempo_us
        approximate_tick = int(target_time_ms * ticks_per_ms)
        
        # Use iterative refinement instead of binary search
        best_tick = approximate_tick
        best_diff = float('inf')
        
        # Search in a reasonable range around the approximation
        search_range = max(self.ticks_per_beat // 4, 10)  # Search ±1/4 beat or ±10 ticks
        
        for offset in range(-search_range, search_range + 1):
            candidate_tick = max(0, approximate_tick + offset)
            candidate_time = self.calculate_time_ms(0, candidate_tick)
            diff = abs(candidate_time - target_time_ms)
            
            if diff < best_diff:
                best_diff = diff
                best_tick = candidate_tick
                
            # If we found a very close match, use it
            if diff < 0.01:  # 0.01ms tolerance
                break
        
        return best_tick

    def _find_tick_at_time(self, target_time_ms: float) -> int:
        """Find tick that corresponds to a specific time"""
        if self.optimization_strategy == TempoOptimizationStrategy.FRAME_ALIGNED:
            # For frame alignment, ensure target time is on frame boundary
            frame_number = round(target_time_ms / FRAME_MS)
            target_time_ms = frame_number * FRAME_MS
        
        # Calculate ticks per millisecond at current tempo
        current_tempo = self.get_tempo_at_tick(0)  # Use initial tempo as approximation
        ticks_per_ms = (self.ticks_per_beat * 1000) / current_tempo
        
        # Calculate approximate tick
        approximate_tick = int(round(target_time_ms * ticks_per_ms))
        
        # For frame alignment, verify and adjust if needed
        if self.optimization_strategy == TempoOptimizationStrategy.FRAME_ALIGNED:
            actual_time = self.calculate_time_ms(0, approximate_tick)
            if abs(actual_time % FRAME_MS) > 0.01:  # Very strict tolerance
                # Try adjusting tick up or down by 1 to find better alignment
                prev_tick = approximate_tick - 1
                next_tick = approximate_tick + 1
                
                prev_time = self.calculate_time_ms(0, prev_tick)
                next_time = self.calculate_time_ms(0, next_tick)
                
                prev_diff = abs(prev_time % FRAME_MS)
                curr_diff = abs(actual_time % FRAME_MS)
                next_diff = abs(next_time % FRAME_MS)
                
                if prev_diff < curr_diff and prev_diff < next_diff:
                    approximate_tick = prev_tick
                elif next_diff < curr_diff and next_diff < prev_diff:
                    approximate_tick = next_tick
        
        return max(0, approximate_tick)

    def get_optimization_Stats(self) -> Dict:
        """Get statistics about optimization operations"""
        return dict(self.optimization_stats)
        
    def analyze_pattern_tempo_characteristics(self, pattern_id: str) -> Dict:
        """Analyze detailed tempo characteristics of a pattern"""
        if pattern_id not in self.pattern_tempos:
            return {}
            
        pattern_info = self.pattern_tempos[pattern_id]
        analysis = {
            'base_tempo_bpm': 60_000_000 / pattern_info.base_tempo,
            'variation_count': len(pattern_info.variations),
            'tempo_range': {
                'min': float('inf'),
                'max': float('-inf'),
                'avg': 0
            },
            'timing_stability': 0.0,
            'complexity_score': 0
        }
        
        tempos = []
        for var in pattern_info.variations:
            tempo_bpm = 60_000_000 / var.tempo
            tempos.append(tempo_bpm)
            analysis['tempo_range']['min'] = min(
                analysis['tempo_range']['min'], tempo_bpm
            )
            analysis['tempo_range']['max'] = max(
                analysis['tempo_range']['max'], tempo_bpm
            )
            
        if tempos:
            analysis['tempo_range']['avg'] = sum(tempos) / len(tempos)
            
            # Calculate timing stability (lower variance = more stable)
            variance = sum((t - analysis['tempo_range']['avg']) ** 2 
                         for t in tempos) / len(tempos)
            analysis['timing_stability'] = 1.0 / (1.0 + variance)
            
            # Calculate complexity score
            analysis['complexity_score'] = len(pattern_info.variations) + sum(
                2 if var.change_type in 
                [TempoChangeType.CURVE, TempoChangeType.PATTERN_SYNC] else 1
                for var in pattern_info.variations
            )
            
        return analysis
        
    def get_debug_info(self) -> Dict:
        """Enhanced debug information including frame timing and validation"""
        info = super().get_debug_info()
        
        # Add enhanced information
        info["validation_config"] = {
            "min_tempo_bpm": self.validation_config.min_tempo_bpm,
            "max_tempo_bpm": self.validation_config.max_tempo_bpm,
            "min_duration_frames": self.validation_config.min_duration_frames,
            "max_duration_frames": self.validation_config.max_duration_frames,
            "max_tempo_change_ratio": self.validation_config.max_tempo_change_ratio
        }
        
        info["optimization_strategy"] = self.optimization_strategy.value
        info["optimization_stats"] = dict(self.optimization_stats)
        info["pattern_count"] = len(self.pattern_tempos)
        info["loop_points_count"] = len(self.loop_points)
        
        # Enhance tempo change information
        for change_info in info["tempo_changes"]:
            change_info["frame"] = self.get_frame_for_tick(change_info["tick"])
            
        return info

    def _check_frame_alignment(self, change: TempoChange):
        """Check if a tempo change aligns with frame boundaries"""
        if change.tick > 0:
            # Calculate frame alignment using microsecond precision
            prev_tempo = self.get_tempo_at_tick(change.tick - 1)
            us_per_tick = prev_tempo / self.ticks_per_beat
            time_us = change.tick * us_per_tick
            remainder_us = time_us % (FRAME_MS * 1000)
            
            if remainder_us > 1:  # Allow 1 microsecond tolerance
                raise TempoValidationError(
                    f"Tempo change at tick {change.tick} not aligned with frame "
                    f"boundary (off by {remainder_us/1000:.3f}ms)"
                )


# Backwards compatibility - export the classes that might be imported
__all__ = ['TempoMap', 'EnhancedTempoMap', 'TempoValidationConfig', 
           'TempoChangeType', 'TempoOptimizationStrategy', 'TempoValidationError']
