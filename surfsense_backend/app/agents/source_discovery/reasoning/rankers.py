"""
Result ranking and selection heuristics.

Provides intelligent ranking of search results based on authority,
recency, yield, and relevance scores.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date

from .models import ToolResult, EvidenceItem
from .config import ReasoningConfig
from .utils import calculate_recency_score, extract_hit_count

logger = logging.getLogger(__name__)


class ResultRanker:
    """Ranks and selects the best results from multiple tool executions."""
    
    def __init__(self, config: ReasoningConfig):
        self.config = config
    
    def rank_tool_results(self, results: List[ToolResult]) -> List[ToolResult]:
        """Rank tool results by overall quality score."""
        if not results:
            return []
        
        scored_results = []
        for result in results:
            score = self._calculate_result_score(result)
            scored_results.append((result, score))
        
        # Sort by score (descending)
        scored_results.sort(key=lambda x: x[1], reverse=True)
        
        return [result for result, score in scored_results]
    
    def pick_best_result(self, results: List[ToolResult]) -> Optional[ToolResult]:
        """Pick the single best result from a list."""
        if not results:
            return None
        
        # Filter out failed results
        successful_results = [r for r in results if r.ok]
        if not successful_results:
            return None
        
        # Rank and return the best
        ranked = self.rank_tool_results(successful_results)
        return ranked[0] if ranked else None
    
    def rank_evidence_items(self, evidence: List[EvidenceItem], query: str) -> List[EvidenceItem]:
        """Rank evidence items by relevance to query."""
        if not evidence:
            return []
        
        scored_evidence = []
        for item in evidence:
            score = self._calculate_evidence_score(item, query)
            scored_evidence.append((item, score))
        
        # Sort by score (descending)
        scored_evidence.sort(key=lambda x: x[1], reverse=True)
        
        return [item for item, score in scored_evidence]
    
    def _calculate_result_score(self, result: ToolResult) -> float:
        """Calculate overall quality score for a tool result."""
        if not result.ok:
            return 0.0
        
        # Authority score based on tool reliability
        authority_score = self._get_authority_score(result.tool)
        
        # Yield score based on number of results
        yield_score = self._get_yield_score(result.hits)
        
        # Performance score (inverse of duration)
        performance_score = self._get_performance_score(result.duration_ms)
        
        # Cache bonus (cached results are slightly preferred for consistency)
        cache_bonus = 0.1 if result.from_cache else 0.0
        
        # Weighted combination
        weights = self.config.ranking_weights
        total_score = (
            weights.get("authority", 0.5) * authority_score +
            weights.get("yield", 0.2) * yield_score +
            weights.get("recency", 0.2) * performance_score +
            0.1 * cache_bonus
        )
        
        return total_score
    
    def _calculate_evidence_score(self, evidence: EvidenceItem, query: str) -> float:
        """Calculate relevance score for an evidence item."""
        score = 0.0
        
        # Authority score based on source
        authority_score = self._get_authority_score(evidence.source)
        score += 0.4 * authority_score
        
        # Title relevance score
        if evidence.title:
            title_score = self._calculate_text_relevance(evidence.title, query)
            score += 0.3 * title_score
        
        # Recency score (if date information available)
        recency_score = self._get_evidence_recency_score(evidence)
        score += 0.2 * recency_score
        
        # Metadata completeness score
        completeness_score = self._get_completeness_score(evidence)
        score += 0.1 * completeness_score
        
        return score
    
    def _get_authority_score(self, tool: str) -> float:
        """Get normalized authority score for a tool."""
        authority_scores = self.config.tool_authority_scores
        raw_score = authority_scores.get(tool, 1)
        max_score = max(authority_scores.values()) if authority_scores else 3
        
        return raw_score / max_score
    
    def _get_yield_score(self, hits: int) -> float:
        """Get normalized yield score based on number of results."""
        if hits == 0:
            return 0.0
        
        # Optimal range scoring
        if self.config.min_ok <= hits <= self.config.max_ok:
            return 1.0  # Perfect range
        elif hits < self.config.min_ok:
            return hits / self.config.min_ok  # Partial score for low hits
        else:
            # Penalty for too many results (diminishing returns)
            excess = hits - self.config.max_ok
            penalty = min(excess / self.config.max_ok, 0.5)  # Max 50% penalty
            return 1.0 - penalty
    
    def _get_performance_score(self, duration_ms: Optional[int]) -> float:
        """Get performance score based on execution time."""
        if duration_ms is None:
            return 0.5  # Neutral score if unknown
        
        # Convert to seconds
        duration_s = duration_ms / 1000.0
        
        # Score based on speed (faster is better)
        if duration_s <= 1.0:
            return 1.0  # Very fast
        elif duration_s <= 5.0:
            return 0.8  # Fast
        elif duration_s <= 15.0:
            return 0.6  # Acceptable
        elif duration_s <= 30.0:
            return 0.4  # Slow
        else:
            return 0.2  # Very slow
    
    def _get_evidence_recency_score(self, evidence: EvidenceItem) -> float:
        """Get recency score for evidence item."""
        # Look for date fields in metadata
        date_fields = ['date', 'posted_date', 'last_update', 'publication_date', 'start_date']
        
        for field in date_fields:
            if field in evidence.meta:
                date_str = evidence.meta[field]
                if date_str:
                    return calculate_recency_score(str(date_str))
        
        # No date found - neutral score
        return 0.5
    
    def _get_completeness_score(self, evidence: EvidenceItem) -> float:
        """Get completeness score based on available metadata."""
        score = 0.0
        
        # Basic fields
        if evidence.id:
            score += 0.3
        if evidence.title:
            score += 0.3
        if evidence.url:
            score += 0.2
        
        # Metadata richness
        if evidence.meta:
            meta_count = len(evidence.meta)
            # Diminishing returns for metadata
            meta_score = min(meta_count / 10.0, 0.2)
            score += meta_score
        
        return min(score, 1.0)
    
    def _calculate_text_relevance(self, text: str, query: str) -> float:
        """Calculate text relevance score using simple keyword matching."""
        if not text or not query:
            return 0.0
        
        text_lower = text.lower()
        query_lower = query.lower()
        
        # Extract keywords from query (simple tokenization)
        query_words = set(word.strip('.,!?";') for word in query_lower.split())
        query_words = {word for word in query_words if len(word) > 2}  # Filter short words
        
        if not query_words:
            return 0.0
        
        # Count matching words
        matches = 0
        for word in query_words:
            if word in text_lower:
                matches += 1
        
        # Calculate relevance as percentage of query words found
        relevance = matches / len(query_words)
        
        # Bonus for exact phrase matches
        if query_lower in text_lower:
            relevance += 0.2
        
        return min(relevance, 1.0)


class ResultSelector:
    """Selects optimal results based on various criteria."""
    
    def __init__(self, config: ReasoningConfig):
        self.config = config
        self.ranker = ResultRanker(config)
    
    def select_diverse_results(self, results: List[ToolResult], max_results: int = 3) -> List[ToolResult]:
        """Select diverse results from different tools/sources."""
        if not results:
            return []
        
        # First, rank all results
        ranked_results = self.ranker.rank_tool_results(results)
        
        # Then select diverse set
        selected = []
        used_tools = set()
        
        for result in ranked_results:
            if len(selected) >= max_results:
                break
            
            # Prefer diversity in tools
            if result.tool not in used_tools or len(selected) < max_results // 2:
                selected.append(result)
                used_tools.add(result.tool)
        
        return selected
    
    def select_results_by_threshold(self, results: List[ToolResult], 
                                  min_score: float = 0.5) -> List[ToolResult]:
        """Select results above a quality threshold."""
        if not results:
            return []
        
        qualified_results = []
        
        for result in results:
            score = self.ranker._calculate_result_score(result)
            if score >= min_score:
                qualified_results.append(result)
        
        return self.ranker.rank_tool_results(qualified_results)
    
    def select_complementary_results(self, results: List[ToolResult]) -> List[ToolResult]:
        """Select results that complement each other."""
        if not results:
            return []
        
        # Group results by tool type
        tool_groups = {}
        for result in results:
            tool_type = self._get_tool_type(result.tool)
            if tool_type not in tool_groups:
                tool_groups[tool_type] = []
            tool_groups[tool_type].append(result)
        
        # Select best from each tool type
        selected = []
        for tool_type, group_results in tool_groups.items():
            best = self.ranker.pick_best_result(group_results)
            if best:
                selected.append(best)
        
        return self.ranker.rank_tool_results(selected)
    
    def _get_tool_type(self, tool: str) -> str:
        """Categorize tool by type for complementary selection."""
        if "ct_gov" in tool:
            return "trials"
        elif "nlm_ct" in tool:
            return "codes"
        elif "fda" in tool:
            return "regulatory"
        elif "pubmed" in tool:
            return "literature"
        elif "sec" in tool:
            return "financial"
        elif "who" in tool:
            return "health_data"
        else:
            return "other"


class AdaptiveRanker:
    """Adaptive ranking that learns from user feedback over time."""
    
    def __init__(self, config: ReasoningConfig):
        self.config = config
        self.base_ranker = ResultRanker(config)
        self.user_preferences = {}  # Could be stored in database
    
    def rank_with_adaptation(self, results: List[ToolResult], 
                           user_id: str) -> List[ToolResult]:
        """Rank results with adaptation to user preferences."""
        # For now, use base ranking
        # In future, could adapt based on user_preferences[user_id]
        return self.base_ranker.rank_tool_results(results)
    
    def learn_from_feedback(self, user_id: str, query: str, 
                          results: List[ToolResult], feedback: Dict[str, Any]):
        """Learn from user feedback to improve future rankings."""
        # Placeholder for learning implementation
        # Could track which results users find most useful
        pass


# Factory functions
def create_ranker(config: ReasoningConfig) -> ResultRanker:
    """Create a standard result ranker."""
    return ResultRanker(config)


def create_selector(config: ReasoningConfig) -> ResultSelector:
    """Create a result selector."""
    return ResultSelector(config)


def create_adaptive_ranker(config: ReasoningConfig) -> AdaptiveRanker:
    """Create an adaptive ranker."""
    return AdaptiveRanker(config)
