"""Performance monitoring and optimization for Claude Discovery Agent."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for a discovery session."""
    session_id: str
    query: str
    start_time: float
    end_time: Optional[float] = None
    total_duration_ms: Optional[float] = None
    
    # Token usage
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    # Tool execution metrics
    tools_used: List[str] = field(default_factory=list)
    tool_execution_times: Dict[str, float] = field(default_factory=dict)
    parallel_tool_calls: int = 0
    sequential_tool_calls: int = 0
    
    # Response quality metrics
    response_length: int = 0
    citations_generated: int = 0
    follow_up_questions: int = 0
    
    # Streaming metrics
    first_chunk_latency_ms: Optional[float] = None
    streaming_chunks: int = 0
    
    # Error tracking
    errors: List[str] = field(default_factory=list)
    
    def finalize(self):
        """Finalize metrics calculation."""
        if self.end_time:
            self.total_duration_ms = (self.end_time - self.start_time) * 1000
    
    def add_tool_execution(self, tool_name: str, execution_time_ms: float, was_parallel: bool = False):
        """Add tool execution metrics."""
        self.tools_used.append(tool_name)
        self.tool_execution_times[tool_name] = execution_time_ms
        
        if was_parallel:
            self.parallel_tool_calls += 1
        else:
            self.sequential_tool_calls += 1
    
    def add_error(self, error: str):
        """Add error to tracking."""
        self.errors.append(error)
        logger.warning(f"Performance: Error tracked - {error}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary."""
        return {
            "session_id": self.session_id,
            "query": self.query[:100] + "..." if len(self.query) > 100 else self.query,
            "total_duration_ms": self.total_duration_ms,
            "token_usage": {
                "input": self.input_tokens,
                "output": self.output_tokens,
                "total": self.total_tokens,
                "efficiency_ratio": self.output_tokens / max(self.input_tokens, 1)
            },
            "tool_metrics": {
                "tools_used": len(set(self.tools_used)),
                "parallel_calls": self.parallel_tool_calls,
                "sequential_calls": self.sequential_tool_calls,
                "avg_tool_time": sum(self.tool_execution_times.values()) / max(len(self.tool_execution_times), 1),
                "fastest_tool": min(self.tool_execution_times.values()) if self.tool_execution_times else 0,
                "slowest_tool": max(self.tool_execution_times.values()) if self.tool_execution_times else 0
            },
            "response_quality": {
                "response_length": self.response_length,
                "citations": self.citations_generated,
                "follow_ups": self.follow_up_questions
            },
            "streaming": {
                "first_chunk_latency": self.first_chunk_latency_ms,
                "total_chunks": self.streaming_chunks
            },
            "errors": len(self.errors),
            "success_rate": 1.0 - (len(self.errors) / max(len(self.tools_used), 1))
        }


class PerformanceMonitor:
    """Monitors and tracks Claude Discovery Agent performance."""
    
    def __init__(self):
        self.active_sessions: Dict[str, PerformanceMetrics] = {}
        self.completed_sessions: List[PerformanceMetrics] = []
        self.max_completed_sessions = 100  # Keep last 100 sessions
    
    def start_session(self, session_id: str, query: str) -> PerformanceMetrics:
        """Start monitoring a discovery session."""
        metrics = PerformanceMetrics(
            session_id=session_id,
            query=query,
            start_time=time.time()
        )
        self.active_sessions[session_id] = metrics
        logger.info(f"📊 Performance monitoring started for session {session_id}")
        return metrics
    
    def end_session(self, session_id: str) -> Optional[PerformanceMetrics]:
        """End monitoring and finalize metrics."""
        if session_id in self.active_sessions:
            metrics = self.active_sessions.pop(session_id)
            metrics.end_time = time.time()
            metrics.finalize()
            
            # Add to completed sessions
            self.completed_sessions.append(metrics)
            
            # Maintain max sessions limit
            if len(self.completed_sessions) > self.max_completed_sessions:
                self.completed_sessions.pop(0)
            
            logger.info(f"📊 Session {session_id} completed: {metrics.total_duration_ms:.1f}ms, {metrics.total_tokens} tokens")
            return metrics
        
        return None
    
    @asynccontextmanager
    async def monitor_tool_execution(self, session_id: str, tool_name: str, is_parallel: bool = False):
        """Context manager to monitor tool execution time."""
        start_time = time.time()
        try:
            yield
        finally:
            execution_time = (time.time() - start_time) * 1000
            if session_id in self.active_sessions:
                self.active_sessions[session_id].add_tool_execution(tool_name, execution_time, is_parallel)
                logger.debug(f"🔧 Tool {tool_name} executed in {execution_time:.1f}ms")
    
    def update_token_usage(self, session_id: str, input_tokens: int, output_tokens: int):
        """Update token usage for a session."""
        if session_id in self.active_sessions:
            metrics = self.active_sessions[session_id]
            metrics.input_tokens += input_tokens
            metrics.output_tokens += output_tokens
            metrics.total_tokens = metrics.input_tokens + metrics.output_tokens
    
    def record_first_chunk(self, session_id: str):
        """Record first streaming chunk latency."""
        if session_id in self.active_sessions:
            metrics = self.active_sessions[session_id]
            if metrics.first_chunk_latency_ms is None:
                metrics.first_chunk_latency_ms = (time.time() - metrics.start_time) * 1000
                logger.debug(f"⚡ First chunk latency: {metrics.first_chunk_latency_ms:.1f}ms")
    
    def record_streaming_chunk(self, session_id: str, chunk_size: int):
        """Record streaming chunk."""
        if session_id in self.active_sessions:
            metrics = self.active_sessions[session_id]
            metrics.streaming_chunks += 1
            if metrics.first_chunk_latency_ms is None:
                self.record_first_chunk(session_id)
    
    def record_response_quality(self, session_id: str, response_length: int, citations: int, follow_ups: int):
        """Record response quality metrics."""
        if session_id in self.active_sessions:
            metrics = self.active_sessions[session_id]
            metrics.response_length = response_length
            metrics.citations_generated = citations
            metrics.follow_up_questions = follow_ups
    
    def record_error(self, session_id: str, error: str):
        """Record an error for a session."""
        if session_id in self.active_sessions:
            self.active_sessions[session_id].add_error(error)
        logger.error(f"📊 Error in session {session_id}: {error}")
    
    def get_session_metrics(self, session_id: str) -> Optional[PerformanceMetrics]:
        """Get metrics for active or completed session."""
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]
        
        for metrics in reversed(self.completed_sessions):
            if metrics.session_id == session_id:
                return metrics
        
        return None
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get overall performance summary."""
        if not self.completed_sessions:
            return {
                "total_sessions": 0,
                "message": "No completed sessions yet"
            }
        
        # Calculate averages from completed sessions
        avg_duration = sum(m.total_duration_ms or 0 for m in self.completed_sessions) / len(self.completed_sessions)
        avg_tokens = sum(m.total_tokens for m in self.completed_sessions) / len(self.completed_sessions)
        avg_tools = sum(len(set(m.tools_used)) for m in self.completed_sessions) / len(self.completed_sessions)
        
        # Token efficiency (output/input ratio)
        token_efficiencies = []
        for m in self.completed_sessions:
            if m.input_tokens > 0:
                token_efficiencies.append(m.output_tokens / m.input_tokens)
        avg_efficiency = sum(token_efficiencies) / len(token_efficiencies) if token_efficiencies else 0
        
        # Success rate
        total_tool_calls = sum(len(m.tools_used) for m in self.completed_sessions)
        total_errors = sum(len(m.errors) for m in self.completed_sessions)
        success_rate = 1.0 - (total_errors / max(total_tool_calls, 1))
        
        # Performance trends (last 10 sessions vs previous 10)
        recent_sessions = self.completed_sessions[-10:] if len(self.completed_sessions) >= 10 else self.completed_sessions
        recent_avg_duration = sum(m.total_duration_ms or 0 for m in recent_sessions) / len(recent_sessions)
        
        return {
            "total_sessions": len(self.completed_sessions),
            "active_sessions": len(self.active_sessions),
            "performance_averages": {
                "duration_ms": avg_duration,
                "total_tokens": avg_tokens,
                "tools_per_query": avg_tools,
                "token_efficiency_ratio": avg_efficiency
            },
            "quality_metrics": {
                "success_rate": success_rate,
                "avg_response_length": sum(m.response_length for m in self.completed_sessions) / len(self.completed_sessions),
                "avg_citations": sum(m.citations_generated for m in self.completed_sessions) / len(self.completed_sessions)
            },
            "recent_performance": {
                "recent_avg_duration_ms": recent_avg_duration,
                "trend": "improving" if recent_avg_duration < avg_duration else "stable" if abs(recent_avg_duration - avg_duration) < 100 else "declining"
            },
            "optimization_recommendations": self._get_optimization_recommendations()
        }
    
    def _get_optimization_recommendations(self) -> List[str]:
        """Generate optimization recommendations based on metrics."""
        if not self.completed_sessions:
            return []
        
        recommendations = []
        recent_sessions = self.completed_sessions[-10:]
        
        # Check average response time
        avg_duration = sum(m.total_duration_ms or 0 for m in recent_sessions) / len(recent_sessions)
        if avg_duration > 10000:  # 10 seconds
            recommendations.append("Consider optimizing tool execution - average response time exceeds 10s")
        
        # Check token efficiency
        token_efficiencies = [m.output_tokens / max(m.input_tokens, 1) for m in recent_sessions]
        avg_efficiency = sum(token_efficiencies) / len(token_efficiencies)
        if avg_efficiency > 3:
            recommendations.append("High token efficiency - consider using more complex queries")
        elif avg_efficiency < 0.5:
            recommendations.append("Low token efficiency - review system prompts for verbosity")
        
        # Check parallel vs sequential tool usage
        total_parallel = sum(m.parallel_tool_calls for m in recent_sessions)
        total_sequential = sum(m.sequential_tool_calls for m in recent_sessions)
        if total_sequential > total_parallel * 2 and total_parallel > 0:
            recommendations.append("Consider promoting more parallel tool usage")
        
        # Check error rates
        total_errors = sum(len(m.errors) for m in recent_sessions)
        error_rate = total_errors / len(recent_sessions)
        if error_rate > 0.1:
            recommendations.append("High error rate detected - review error handling")
        
        return recommendations


# Global performance monitor instance
performance_monitor = PerformanceMonitor()