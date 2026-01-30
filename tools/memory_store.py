"""
Simple JSON-based Episodic Memory Store for SRE Agents.
Handles saving successful fixes, retrieving similar incidents, and confidence decay.
"""

import json
import os
import math
from typing import List, Dict, Any, Optional
from datetime import datetime

# Use absolute path in the sre-agent-system directory for persistence
MEMORY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sre_memory.json")

class MemoryStore:
    def __init__(self, filepath: str = MEMORY_FILE):
        self.filepath = filepath
        self.memories = self._load()

    def _load(self) -> List[Dict]:
        """Load memories from JSON file"""
        if not os.path.exists(self.filepath):
            return []
        try:
            with open(self.filepath, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []

    def save(self):
        """Persist memories to disk"""
        with open(self.filepath, 'w') as f:
            json.dump(self.memories, f, indent=2, default=str)

    def add_incident(self, 
                    symptoms: List[str], 
                    diagnosis: str, 
                    solution: str, 
                    specialists: List[str],
                    cost_impact: float = 0.0,
                    confidence: float = 0.8):
        """Add a new resolved incident to memory"""
        entry = {
            "id": f"mem-{int(datetime.now().timestamp())}",
            "timestamp": datetime.now().isoformat(),
            "symptoms": symptoms,
            "diagnosis": diagnosis,
            "solution": solution,
            "specialists": specialists,
            "cost_impact": cost_impact,
            "confidence": confidence,
            "success_count": 1,
            "failure_count": 0
        }
        self.memories.append(entry)
        self.save()

    def search(self, current_symptoms: List[str], min_confidence: float = 0.7) -> List[Dict]:
        """
        Search for similar past incidents.
        Uses simple keyword overlap for the demo.
        """
        results = []
        current_set = set(s.lower() for s in current_symptoms)

        for mem in self.memories:
            # Apply Time Decay
            age_days = (datetime.now() - datetime.fromisoformat(mem['timestamp'])).days
            decay_factor = math.exp(-age_days / 30)  # Decay over 30 days
            adjusted_confidence = mem['confidence'] * decay_factor

            if adjusted_confidence < min_confidence:
                continue

            # Check overlap
            mem_symptoms = set(s.lower() for s in mem['symptoms'])
            overlap = len(current_set.intersection(mem_symptoms))
            
            if overlap > 0:
                # Boost score by overlap ratio
                score = adjusted_confidence * (overlap / len(current_set))
                
                if score > min_confidence:
                    result = mem.copy()
                    result['match_score'] = score
                    results.append(result)

        # Sort by best match
        return sorted(results, key=lambda x: x['match_score'], reverse=True)

    def feedback(self, memory_id: str, success: bool):
        """Update confidence based on reuse outcome"""
        for mem in self.memories:
            if mem['id'] == memory_id:
                if success:
                    mem['success_count'] += 1
                    mem['confidence'] = min(0.99, mem['confidence'] * 1.1)
                else:
                    mem['failure_count'] += 1
                    mem['confidence'] *= 0.5 # Heavy penalty for failure
                
                mem['last_used'] = datetime.now().isoformat()
                self.save()
                return

# Helper for agents to use
_store = None
def get_memory_store():
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store
