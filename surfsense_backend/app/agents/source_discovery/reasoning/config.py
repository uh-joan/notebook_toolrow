"""
Configuration for the reasoning system.

Defines configurable thresholds, timeouts, and behavior parameters
for the source discovery reasoning agent.
"""

import os
from pydantic import BaseModel, Field
from typing import Dict, Any


class ReasoningConfig(BaseModel):
    """Configuration for reasoning behavior and thresholds."""
    
    # Result quantity thresholds
    min_ok: int = Field(5, description="Minimum results to consider sufficient")
    max_ok: int = Field(500, description="Maximum results before refinement needed")
    
    # Execution limits
    max_rounds: int = Field(3, description="Maximum expansion/refinement rounds")
    per_query_timeout_s: int = Field(20, description="Timeout per individual tool query")
    total_timeout_s: int = Field(120, description="Total timeout for entire reasoning session")
    parallel_limit: int = Field(5, description="Maximum parallel tool executions")
    
    # Search strategy defaults
    default_years_back: int = Field(10, description="Default search window in years")
    broaden_years_back: int = Field(20, description="Expanded search window for broadening")
    
    # Ranking weights
    ranking_weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "authority": 0.5,   # Tool reliability weight
            "recency": 0.3,     # Temporal relevance weight  
            "yield": 0.2        # Result quantity weight
        },
        description="Weights for result ranking algorithm"
    )
    
    # Tool authority scores (higher = more authoritative)
    tool_authority_scores: Dict[str, int] = Field(
        default_factory=lambda: {
            "nlm_ct_codes": 3,
            "fda_info": 3,
            "ct_gov_studies": 2,
            "pubmed_articles": 2,
            "sec_edgar": 2,
            "who_health": 1
        },
        description="Authority scores for different tools"
    )
    
    # Feature flags - all enabled by default for optimal user experience
    enable_caching: bool = Field(True, description="Enable result caching")
    enable_parallel_execution: bool = Field(True, description="Enable parallel tool execution")
    enable_query_expansion: bool = Field(True, description="Enable automatic query expansion")
    enable_result_refinement: bool = Field(True, description="Enable automatic result refinement")
    
    # Logging and observability
    log_level: str = Field("INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")
    trace_sampling_rate: float = Field(1.0, description="Fraction of traces to keep (0.0-1.0)")
    emit_metrics: bool = Field(True, description="Whether to emit performance metrics")
    
    # Cache settings
    cache_ttl_seconds: int = Field(3600, description="Cache time-to-live in seconds")
    max_cache_size: int = Field(1000, description="Maximum number of cached results")
    
    @classmethod
    def from_env(cls) -> "ReasoningConfig":
        """Create config from environment variables with fallback to defaults."""
        return cls(
            min_ok=int(os.getenv("REASONING_MIN_OK", "5")),
            max_ok=int(os.getenv("REASONING_MAX_OK", "500")),
            max_rounds=int(os.getenv("REASONING_MAX_ROUNDS", "3")),
            per_query_timeout_s=int(os.getenv("REASONING_QUERY_TIMEOUT", "20")),
            total_timeout_s=int(os.getenv("REASONING_TOTAL_TIMEOUT", "120")),
            parallel_limit=int(os.getenv("REASONING_PARALLEL_LIMIT", "5")),
            default_years_back=int(os.getenv("REASONING_DEFAULT_YEARS", "10")),
            broaden_years_back=int(os.getenv("REASONING_BROADEN_YEARS", "20")),
            log_level=os.getenv("REASONING_LOG_LEVEL", "INFO"),
            trace_sampling_rate=float(os.getenv("REASONING_TRACE_SAMPLING", "1.0")),
            enable_caching=os.getenv("REASONING_ENABLE_CACHING", "true").lower() == "true",
            enable_parallel_execution=os.getenv("REASONING_ENABLE_PARALLEL", "true").lower() == "true",
            enable_query_expansion=os.getenv("REASONING_ENABLE_EXPANSION", "true").lower() == "true",
            enable_result_refinement=os.getenv("REASONING_ENABLE_REFINEMENT", "true").lower() == "true",
            emit_metrics=os.getenv("REASONING_EMIT_METRICS", "true").lower() == "true",
            cache_ttl_seconds=int(os.getenv("REASONING_CACHE_TTL", "3600")),
            max_cache_size=int(os.getenv("REASONING_MAX_CACHE_SIZE", "1000"))
        )
    
    def is_zero_hit(self, hits: int) -> bool:
        """Check if result count is zero."""
        return hits == 0
    
    def is_too_few(self, hits: int) -> bool:
        """Check if result count is below minimum threshold."""
        return hits < self.min_ok
    
    def is_too_many(self, hits: int) -> bool:
        """Check if result count exceeds maximum threshold."""
        return hits > self.max_ok
    
    def is_acceptable(self, hits: int) -> bool:
        """Check if result count is within acceptable range."""
        return self.min_ok <= hits <= self.max_ok
