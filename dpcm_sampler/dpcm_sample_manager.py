from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import json
import os

class DPCMSampleManager:
    def __init__(self, max_samples=16, memory_limit=4096):  # 4KB default limit
        self.max_samples = max_samples
        self.memory_limit = memory_limit
        self.active_samples = {}  # Currently loaded samples
        self.usage_stats = defaultdict(int)  # Track sample usage
        self.sample_cache = {}  # Cache for frequently used samples
        self.sample_similarities = {}  # Track similar samples
        
    def allocate_sample(self, sample_name: str, sample_data: Dict) -> Dict:
        """
        Intelligently allocates DPCM samples based on usage and memory constraints
        
        Args:
            sample_name: Name of the sample to allocate
            sample_data: Dictionary containing sample metadata and binary data
            
        Returns:
            Dict containing sample allocation information
        """
        # Update usage statistics
        self.usage_stats[sample_name] += 1
        
        # Check if sample is already allocated
        if sample_name in self.active_samples:
            return self.active_samples[sample_name]
            
        # Calculate memory requirements - use length from metadata if available
        sample_size = sample_data.get('length', 1024)  # Default sample size
        
        # Check memory constraints
        current_memory = sum(s['metadata']['size'] 
                           for s in self.active_samples.values())
        
        if current_memory + sample_size > self.memory_limit:
            self._optimize_sample_bank()
            
        # Check if we can reuse a similar sample
        if len(self.active_samples) >= self.max_samples:
            similar_sample = self._find_similar_sample(sample_name, sample_data)
            if similar_sample:
                return similar_sample
            
            # If no similar sample, force optimization
            self._optimize_sample_bank(force=True)
            
        # Allocate new sample
        sample_info = {
            'id': len(self.active_samples),
            'name': sample_name,
            'data': sample_data.get('data', []),  # Default to empty list if no data
            'metadata': {
                'size': sample_size,
                'frequency': sample_data.get('frequency', 33144),
                'original_name': sample_name
            }
        }
        
        self.active_samples[sample_name] = sample_info
        self._update_similarities(sample_name, sample_data)
        
        return sample_info
        
    def _optimize_sample_bank(self, force: bool = False) -> None:
        """
        Optimizes the sample bank based on usage statistics and memory constraints
        
        Args:
            force: If True, forces removal of least used samples
        """
        if len(self.active_samples) < self.max_samples and not force:
            return
            
        # Calculate sample scores based on:
        # - Usage frequency
        # - Time since last use
        # - Memory size
        # - Similarity to other samples
        sample_scores = {}
        
        for name, sample in self.active_samples.items():
            usage_score = self.usage_stats[name]
            size_score = 1.0 / (sample['metadata']['size'] + 1)  # Prefer smaller samples
            similarity_score = len(self.sample_similarities.get(name, []))
            
            # Combined score (weighted)
            sample_scores[name] = (
                usage_score * 0.5 +  # Usage is most important
                size_score * 0.3 +   # Size is second
                similarity_score * 0.2  # Similarity is third
            )
            
        # Sort samples by score
        sorted_samples = sorted(
            sample_scores.items(),
            key=lambda x: x[1]
        )
        
        # Remove lowest scoring samples until we're under limits
        while (len(self.active_samples) >= self.max_samples or 
               self._get_total_memory() > self.memory_limit):
            if not sorted_samples:
                break
            sample_to_remove = sorted_samples.pop(0)[0]
            self._remove_sample(sample_to_remove)
            
    def _find_similar_sample(self, sample_name: str, 
                            sample_data: Dict) -> Optional[Dict]:
        """
        Finds a similar sample that can be reused
        
        Args:
            sample_name: Name of the sample to find similar for
            sample_data: Sample data to compare against
            
        Returns:
            Similar sample info if found, None otherwise
        """
        if not self.sample_similarities:
            return None
            
        # Check cache first
        if sample_name in self.sample_cache:
            return self.sample_cache[sample_name]
            
        # Find most similar active sample
        best_match = None
        highest_similarity = 0.0
        
        for active_name, similar_samples in self.sample_similarities.items():
            if active_name in self.active_samples and sample_name in similar_samples:
                similarity = similar_samples[sample_name]
                if similarity > highest_similarity:
                    highest_similarity = similarity
                    best_match = self.active_samples[active_name]
                    
        # Cache the result if good match found
        if highest_similarity > 0.85:  # High similarity threshold
            self.sample_cache[sample_name] = best_match
            return best_match
            
        return None
        
    def _update_similarities(self, sample_name: str, sample_data: Dict) -> None:
        """
        Updates the similarity matrix for the new sample
        """
        if not self.active_samples:
            return
            
        self.sample_similarities[sample_name] = {}
        
        for other_name, other_sample in self.active_samples.items():
            if other_name != sample_name:
                similarity = self._calculate_sample_similarity(
                    sample_data, other_sample
                )
                self.sample_similarities[sample_name][other_name] = similarity
                self.sample_similarities[other_name][sample_name] = similarity
                
    def _calculate_sample_similarity(self, sample1: Dict, sample2: Dict) -> float:
        """
        Calculates similarity between two samples based on:
        - Waveform similarity
        - Frequency characteristics
        - Sample length
        """
        # Basic implementation - can be enhanced with more sophisticated comparison
        data1 = sample1.get('data', [])
        data2 = sample2.get('data', [])
        
        # Length similarity
        max_len = max(len(data1), len(data2))
        if max_len == 0:
            length_similarity = 1.0
        else:
            length_similarity = 1.0 - abs(len(data1) - len(data2)) / max_len
        
        # Simple waveform similarity (can be enhanced)
        min_length = min(len(data1), len(data2))
        if min_length == 0:
            waveform_similarity = 1.0 if len(data1) == 0 and len(data2) == 0 else 0.0
        else:
            matches = sum(1 for i in range(min_length) if data1[i] == data2[i])
            waveform_similarity = matches / min_length
        
        # Combine similarities (weighted)
        return length_similarity * 0.4 + waveform_similarity * 0.6
        
    def _remove_sample(self, sample_name: str) -> None:
        """
        Removes a sample from the active samples
        """
        if sample_name in self.active_samples:
            del self.active_samples[sample_name]
        if sample_name in self.sample_similarities:
            del self.sample_similarities[sample_name]
        for similarities in self.sample_similarities.values():
            if sample_name in similarities:
                del similarities[sample_name]
                
    def _get_total_memory(self) -> int:
        """
        Calculates total memory usage of active samples
        """
        return sum(len(s.get('data', [])) // 8 for s in self.active_samples.values())
