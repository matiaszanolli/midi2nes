import multiprocessing as mp
import threading
import time
from typing import List, Dict, Tuple, Any, Optional
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import numpy as np
from tqdm import tqdm
from tracker.tempo_map import EnhancedTempoMap
from tracker.pattern_detector import PatternCompressor

class ParallelPatternDetector:
    """
    High-performance pattern detector using multiprocessing to utilize all CPU cores.
    Designed for large MIDI files with thousands of events.
    """
    
    def __init__(self, tempo_map: EnhancedTempoMap, min_pattern_length=3, max_pattern_length=32):
        self.tempo_map = tempo_map
        self.min_pattern_length = min_pattern_length
        self.max_pattern_length = max_pattern_length
        self.compressor = PatternCompressor()
        
        # Get optimal number of workers
        self.max_workers = max(1, mp.cpu_count() - 1)  # Leave one core for OS
        
    def detect_patterns(self, events: List[Dict]) -> Dict:
        """
        Detect patterns using parallel processing across multiple CPU cores.
        """
        if not events:
            return {
                'patterns': {},
                'references': {},
                'stats': {'compression_ratio': 0, 'original_size': 0, 'compressed_size': 0, 'unique_patterns': 0},
                'variations': {}
            }
        
        print(f"🚀 Starting parallel pattern detection with {self.max_workers} workers")
        start_time = time.time()
        
        # Clean and validate events
        valid_events = self._filter_valid_events(events)
        if not valid_events:
            return self._empty_result()
        
        # Convert to sequence for processing
        sequence = [(e['note'], e['volume']) for e in valid_events]
        
        # Limit sequence size for performance
        MAX_EVENTS = 5000  # Increased from 1000 for better results
        if len(sequence) > MAX_EVENTS:
            print(f"⚠️  Large sequence ({len(sequence)} events), sampling {MAX_EVENTS} for performance")
            # Sample events across the whole sequence for better representation
            step = len(sequence) // MAX_EVENTS
            sequence = sequence[::step][:MAX_EVENTS]
            valid_events = valid_events[::step][:MAX_EVENTS]
        
        # Split work into chunks for parallel processing
        patterns = self._detect_patterns_parallel(sequence, valid_events)
        
        # Compress patterns
        compressed_patterns, pattern_refs = self.compressor.compress_patterns(patterns)
        
        # Calculate compression statistics
        compression_stats = self.compressor.calculate_compression_stats(
            patterns, compressed_patterns
        )
        
        end_time = time.time()
        print(f"✅ Parallel pattern detection completed in {end_time - start_time:.2f}s")
        
        return {
            'patterns': compressed_patterns,
            'references': pattern_refs,
            'stats': compression_stats,
            'variations': self._get_variation_summary(patterns)
        }
    
    def _filter_valid_events(self, events: List[Dict]) -> List[Dict]:
        """Filter and validate events for pattern detection"""
        return [
            event for event in events
            if isinstance(event.get('note'), (int, float)) and
               isinstance(event.get('volume'), (int, float)) and
               0 <= event.get('note', 0) <= 127 and
               0 <= event.get('volume', 0) <= 127
        ]
    
    def _detect_patterns_parallel(self, sequence: List[Tuple], valid_events: List[Dict]) -> Dict:
        """Detect patterns using parallel processing"""
        
        # Create work chunks by pattern length
        work_chunks = []
        for length in range(self.min_pattern_length, 
                          min(self.max_pattern_length, len(sequence)) + 1):
            # Split pattern search by length ranges to distribute work
            chunk_size = max(1, (len(sequence) - length + 1) // self.max_workers)
            
            for start_offset in range(0, len(sequence) - length + 1, chunk_size):
                end_offset = min(start_offset + chunk_size, len(sequence) - length + 1)
                work_chunks.append({
                    'sequence': sequence,
                    'events': valid_events,
                    'pattern_length': length,
                    'start_offset': start_offset,
                    'end_offset': end_offset,
                    'min_pattern_length': self.min_pattern_length
                })
        
        print(f"🔧 Created {len(work_chunks)} work chunks for parallel processing")
        
        # Process chunks in parallel
        all_candidate_patterns = []
        
        try:
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all work chunks
                future_to_chunk = {
                    executor.submit(_detect_patterns_worker, chunk): chunk 
                    for chunk in work_chunks
                }
                
                # Collect results as they complete with progress bar
                with tqdm(total=len(work_chunks), desc="Processing pattern chunks", unit="chunk") as pbar:
                    for future in as_completed(future_to_chunk):
                        try:
                            chunk_patterns = future.result(timeout=30)  # 30s timeout per chunk
                            all_candidate_patterns.extend(chunk_patterns)
                            pbar.update(1)
                            pbar.set_postfix(patterns=len(all_candidate_patterns))
                        except Exception as e:
                            pbar.write(f"  ⚠️  Chunk failed: {e}")
                            pbar.update(1)
                            continue
        
        except Exception as e:
            print(f"  ❌ Parallel processing failed, falling back to serial: {e}")
            # Fallback to serial processing
            return self._detect_patterns_serial(sequence, valid_events)
        
        print(f"📈 Found {len(all_candidate_patterns)} candidate patterns")
        
        # Select best non-overlapping patterns
        return self._select_best_patterns(all_candidate_patterns)
    
    def _detect_patterns_serial(self, sequence: List[Tuple], valid_events: List[Dict]) -> Dict:
        """Fallback serial pattern detection"""
        print("🔄 Using serial pattern detection")
        
        candidate_patterns = []
        
        for length in range(self.min_pattern_length, 
                          min(self.max_pattern_length, len(sequence)) + 1):
            for start in range(len(sequence) - length + 1):
                pattern = tuple(sequence[start:start + length])
                matches = self._find_pattern_matches(sequence, pattern, start)
                
                if len(matches) >= 3:  # Minimum 3 occurrences
                    score = self._score_pattern(length, len(matches), 0)
                    if score > 0:
                        candidate_patterns.append({
                            'start': start,
                            'length': length,
                            'pattern': pattern,
                            'positions': matches,
                            'score': score,
                            'events': [valid_events[i] for i in range(start, start + length)]
                        })
        
        return self._select_best_patterns(candidate_patterns)
    
    def _select_best_patterns(self, candidate_patterns: List[Dict]) -> Dict:
        """Select best non-overlapping patterns from candidates"""
        if not candidate_patterns:
            return {}
        
        # Sort by score (best first)
        candidate_patterns.sort(key=lambda x: x['score'], reverse=True)
        
        patterns = {}
        used_positions = set()
        
        for candidate in candidate_patterns:
            # Check if this pattern overlaps with already selected patterns
            pattern_positions = set()
            for pos in candidate['positions']:
                pattern_positions.update(range(pos, pos + candidate['length']))
            
            if not pattern_positions.intersection(used_positions):
                pattern_id = f"pattern_{len(patterns)}"
                patterns[pattern_id] = {
                    'events': candidate['events'],
                    'positions': candidate['positions'],
                    'exact_matches': candidate['positions'],
                    'variations': [],
                    'length': candidate['length']
                }
                used_positions.update(pattern_positions)
        
        return patterns
    
    def _find_pattern_matches(self, sequence: List, pattern: Tuple, start_pos: int) -> List[int]:
        """Find all occurrences of a pattern in the sequence"""
        matches = [start_pos]
        pattern_len = len(pattern)
        
        pos = start_pos + 1
        while pos <= len(sequence) - pattern_len:
            current = tuple(sequence[pos:pos + pattern_len])
            if current == pattern:
                matches.append(pos)
                pos += pattern_len  # Skip to avoid overlaps
            else:
                pos += 1
        
        return matches
    
    def _score_pattern(self, length: int, exact_count: int, variation_count: int) -> float:
        """Score pattern based on compression benefit"""
        total_count = exact_count + variation_count
        
        if total_count < 3:
            return -1
        
        # Base score: compression benefit
        compression_benefit = length * (total_count - 1)
        storage_cost = length + total_count
        net_benefit = compression_benefit - storage_cost
        
        # Bonuses
        length_bonus = length * 2.0 if length >= 4 else length
        frequency_bonus = total_count * 0.5 if total_count >= 4 else 0
        
        return net_benefit + length_bonus + frequency_bonus
    
    def _get_variation_summary(self, patterns: Dict) -> Dict:
        """Generate summary of pattern variations"""
        return {
            pattern_id: {
                'variation_count': len(pattern_info.get('variations', [])),
                'exact_matches': len(pattern_info.get('exact_matches', []))
            }
            for pattern_id, pattern_info in patterns.items()
        }
    
    def _empty_result(self) -> Dict:
        """Return empty result structure"""
        return {
            'patterns': {},
            'references': {},
            'stats': {'compression_ratio': 0, 'original_size': 0, 'compressed_size': 0, 'unique_patterns': 0},
            'variations': {}
        }


def _detect_patterns_worker(work_chunk: Dict) -> List[Dict]:
    """
    Worker function for parallel pattern detection.
    This runs in a separate process.
    """
    sequence = work_chunk['sequence']
    events = work_chunk['events']
    pattern_length = work_chunk['pattern_length']
    start_offset = work_chunk['start_offset']
    end_offset = work_chunk['end_offset']
    min_pattern_length = work_chunk['min_pattern_length']
    
    candidate_patterns = []
    
    # Search for patterns in this chunk
    for start in range(start_offset, end_offset):
        if start + pattern_length > len(sequence):
            break
            
        pattern = tuple(sequence[start:start + pattern_length])
        
        # Find all matches for this pattern
        matches = []
        pattern_len = len(pattern)
        pos = 0
        
        while pos <= len(sequence) - pattern_len:
            current = tuple(sequence[pos:pos + pattern_len])
            if current == pattern:
                matches.append(pos)
                pos += pattern_len  # Skip to avoid overlaps
            else:
                pos += 1
        
        # Score the pattern
        if len(matches) >= 3:  # Minimum 3 occurrences
            total_count = len(matches)
            compression_benefit = pattern_length * (total_count - 1)
            storage_cost = pattern_length + total_count
            net_benefit = compression_benefit - storage_cost
            
            length_bonus = pattern_length * 2.0 if pattern_length >= 4 else pattern_length
            frequency_bonus = total_count * 0.5 if total_count >= 4 else 0
            score = net_benefit + length_bonus + frequency_bonus
            
            if score > 0:
                candidate_patterns.append({
                    'start': start,
                    'length': pattern_length,
                    'pattern': pattern,
                    'positions': matches,
                    'score': score,
                    'events': [events[i] for i in range(start, start + pattern_length)]
                })
    
    return candidate_patterns


class ThreadedPatternDetector:
    """
    Threading-based pattern detector for I/O bound operations.
    Used when multiprocessing isn't available or practical.
    """
    
    def __init__(self, tempo_map: EnhancedTempoMap, min_pattern_length=3, max_pattern_length=32):
        self.tempo_map = tempo_map
        self.min_pattern_length = min_pattern_length
        self.max_pattern_length = max_pattern_length
        self.compressor = PatternCompressor()
        
        # Use threading for I/O-bound tasks
        self.max_threads = min(8, (mp.cpu_count() or 1) * 2)  # 2x CPU cores, max 8
    
    def detect_patterns(self, events: List[Dict]) -> Dict:
        """Detect patterns using threading for I/O-bound operations"""
        if not events:
            return {
                'patterns': {},
                'references': {},
                'stats': {'compression_ratio': 0, 'original_size': 0, 'compressed_size': 0, 'unique_patterns': 0},
                'variations': {}
            }
        
        print(f"🧵 Using threaded pattern detection with {self.max_threads} threads")
        start_time = time.time()
        
        # Use threading for pattern search coordination
        # The actual pattern matching is still CPU-bound but this helps with coordination
        patterns = self._detect_patterns_threaded(events)
        
        # Compress patterns
        compressed_patterns, pattern_refs = self.compressor.compress_patterns(patterns)
        
        # Calculate compression statistics
        compression_stats = self.compressor.calculate_compression_stats(
            patterns, compressed_patterns
        )
        
        end_time = time.time()
        print(f"✅ Threaded pattern detection completed in {end_time - start_time:.2f}s")
        
        return {
            'patterns': compressed_patterns,
            'references': pattern_refs,
            'stats': compression_stats,
            'variations': {}
        }
    
    def _detect_patterns_threaded(self, events: List[Dict]) -> Dict:
        """Use threading to coordinate pattern detection"""
        # Filter valid events
        valid_events = [
            event for event in events
            if isinstance(event.get('note'), (int, float)) and
               isinstance(event.get('volume'), (int, float))
        ]
        
        if not valid_events:
            return {}
        
        sequence = [(e['note'], e['volume']) for e in valid_events]
        
        # Limit for performance
        if len(sequence) > 2000:
            step = len(sequence) // 2000
            sequence = sequence[::step]
            valid_events = valid_events[::step]
        
        patterns = {}
        pattern_lock = threading.Lock()
        
        def search_patterns_for_length(length):
            local_patterns = []
            for start in range(len(sequence) - length + 1):
                pattern = tuple(sequence[start:start + length])
                matches = self._find_matches(sequence, pattern, start)
                
                if len(matches) >= 3:
                    score = length * len(matches)  # Simple scoring
                    local_patterns.append({
                        'id': f"pattern_{len(patterns)}_{start}",
                        'events': [valid_events[i] for i in range(start, start + length)],
                        'positions': matches,
                        'exact_matches': matches,
                        'variations': [],
                        'length': length,
                        'score': score
                    })
            
            # Add to global patterns with thread safety
            with pattern_lock:
                for p in local_patterns:
                    if len(patterns) < 50:  # Limit pattern count
                        patterns[p['id']] = p
        
        # Use threads for different pattern lengths
        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            futures = []
            for length in range(self.min_pattern_length, 
                              min(self.max_pattern_length, len(sequence)) + 1):
                future = executor.submit(search_patterns_for_length, length)
                futures.append(future)
            
            # Wait for all threads to complete
            for future in as_completed(futures):
                try:
                    future.result(timeout=10)  # 10s timeout per thread
                except Exception as e:
                    print(f"Thread failed: {e}")
        
        return patterns
    
    def _find_matches(self, sequence: List, pattern: Tuple, start_pos: int) -> List[int]:
        """Find pattern matches"""
        matches = [start_pos]
        pattern_len = len(pattern)
        
        pos = start_pos + 1
        while pos <= len(sequence) - pattern_len:
            if tuple(sequence[pos:pos + pattern_len]) == pattern:
                matches.append(pos)
                pos += pattern_len
            else:
                pos += 1
        
        return matches


if __name__ == "__main__":
    # Test the parallel pattern detector
    print("🧪 Testing Parallel Pattern Detector")
    
    # Create test data
    test_events = []
    for i in range(1000):
        test_events.append({
            'frame': i,
            'note': 60 + (i % 12),  # Create some repeating patterns
            'volume': 100 - (i % 20)
        })
    
    from tracker.tempo_map import EnhancedTempoMap
    tempo_map = EnhancedTempoMap()
    
    # Test parallel detector
    parallel_detector = ParallelPatternDetector(tempo_map)
    result = parallel_detector.detect_patterns(test_events)
    
    print(f"Found {len(result['patterns'])} patterns")
    print(f"Compression ratio: {result['stats']['compression_ratio']:.2f}")
