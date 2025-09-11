"""
Structured logging and observability for the reasoning system.

Provides JSON-structured logging, performance metrics, and trace correlation
for monitoring and debugging the reasoning agent.
"""

import json
import logging
import time
import uuid
from typing import Dict, Any, Optional
from contextvars import ContextVar
from dataclasses import dataclass, asdict

from .models import TraceEvent

# Context variable for trace correlation
trace_id_context: ContextVar[str] = ContextVar('trace_id', default='')

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for reasoning operations."""
    
    total_duration_ms: int
    tool_execution_count: int
    expansion_rounds: int
    refinement_rounds: int
    zero_hit_recoveries: int
    overbroad_refinements: int
    cache_hits: int
    cache_misses: int
    timeout_count: int
    error_count: int


class ReasoningLogger:
    """Structured logger for reasoning operations."""
    
    def __init__(self, logger_name: str = __name__):
        self.logger = logging.getLogger(logger_name)
        self.metrics: Dict[str, int] = {}
        self.trace_id: Optional[str] = None
        
    def start_session(self, user_id: str, query: str) -> str:
        """Start a new reasoning session with trace correlation."""
        self.trace_id = str(uuid.uuid4())[:8]
        trace_id_context.set(self.trace_id)
        
        self._log_structured("reasoning_session_start", {
            "trace_id": self.trace_id,
            "user_id": user_id,
            "query": query,
            "timestamp": time.time()
        })
        
        return self.trace_id
    
    def end_session(self, success: bool, duration_ms: int, evidence_count: int) -> None:
        """End the reasoning session."""
        self._log_structured("reasoning_session_end", {
            "trace_id": self.trace_id,
            "success": success,
            "duration_ms": duration_ms,
            "evidence_count": evidence_count,
            "metrics": self.metrics.copy(),
            "timestamp": time.time()
        })
        
        # Reset metrics for next session
        self.metrics.clear()
    
    def log_trace_event(self, event: TraceEvent) -> None:
        """Log a reasoning trace event."""
        self._log_structured("reasoning_trace_event", {
            "trace_id": self.trace_id,
            "step": event.step,
            "strategy": event.strategy,
            "tool": event.tool,
            "input": event.input,
            "outcome": event.outcome,
            "reason": event.reason,
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            "duration_ms": event.duration_ms
        })
    
    def log_tool_execution(self, tool: str, params: Dict[str, Any], 
                          success: bool, duration_ms: int, hits: int,
                          from_cache: bool = False) -> None:
        """Log tool execution details."""
        self._increment_metric("tool_execution_count")
        
        if from_cache:
            self._increment_metric("cache_hits")
        else:
            self._increment_metric("cache_misses")
        
        if not success:
            self._increment_metric("error_count")
        
        self._log_structured("tool_execution", {
            "trace_id": self.trace_id,
            "tool": tool,
            "params": params,
            "success": success,
            "duration_ms": duration_ms,
            "hits": hits,
            "from_cache": from_cache,
            "timestamp": time.time()
        })
    
    def log_strategy_execution(self, strategy: str, success: bool, 
                             hits_before: int, hits_after: int) -> None:
        """Log strategy execution results."""
        if strategy.startswith("zero_hit"):
            self._increment_metric("zero_hit_recoveries")
        elif strategy.startswith("overbroad"):
            self._increment_metric("overbroad_refinements")
        elif "expansion" in strategy:
            self._increment_metric("expansion_rounds")
        elif "refinement" in strategy:
            self._increment_metric("refinement_rounds")
        
        self._log_structured("strategy_execution", {
            "trace_id": self.trace_id,
            "strategy": strategy,
            "success": success,
            "hits_before": hits_before,
            "hits_after": hits_after,
            "improvement": hits_after - hits_before,
            "timestamp": time.time()
        })
    
    def log_timeout(self, tool: str, timeout_s: int) -> None:
        """Log timeout events."""
        self._increment_metric("timeout_count")
        
        self._log_structured("tool_timeout", {
            "trace_id": self.trace_id,
            "tool": tool,
            "timeout_s": timeout_s,
            "timestamp": time.time()
        })
    
    def log_error(self, error: Exception, context: Dict[str, Any] = None) -> None:
        """Log error events with context."""
        self._increment_metric("error_count")
        
        self._log_structured("reasoning_error", {
            "trace_id": self.trace_id,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {},
            "timestamp": time.time()
        })
    
    def log_performance_summary(self, metrics: PerformanceMetrics) -> None:
        """Log performance summary."""
        self._log_structured("performance_summary", {
            "trace_id": self.trace_id,
            **asdict(metrics),
            "timestamp": time.time()
        })
    
    def _log_structured(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log structured data as JSON."""
        log_entry = {
            "event_type": event_type,
            **data
        }
        
        # Log as JSON for structured logging systems
        self.logger.info(json.dumps(log_entry, default=str))
    
    def _increment_metric(self, metric_name: str) -> None:
        """Increment a metric counter."""
        self.metrics[metric_name] = self.metrics.get(metric_name, 0) + 1


class MetricsCollector:
    """Collects and aggregates performance metrics."""
    
    def __init__(self):
        self.session_metrics: Dict[str, PerformanceMetrics] = {}
        self.aggregate_metrics: Dict[str, float] = {}
    
    def record_session(self, trace_id: str, metrics: PerformanceMetrics) -> None:
        """Record metrics for a session."""
        self.session_metrics[trace_id] = metrics
        self._update_aggregates(metrics)
    
    def get_session_metrics(self, trace_id: str) -> Optional[PerformanceMetrics]:
        """Get metrics for a specific session."""
        return self.session_metrics.get(trace_id)
    
    def get_aggregate_metrics(self) -> Dict[str, float]:
        """Get aggregated metrics across all sessions."""
        return self.aggregate_metrics.copy()
    
    def _update_aggregates(self, metrics: PerformanceMetrics) -> None:
        """Update aggregate metrics with new session data."""
        # Simple running averages - in production, use proper time-windowed metrics
        session_count = len(self.session_metrics)
        
        for field_name, value in asdict(metrics).items():
            if isinstance(value, (int, float)):
                current_avg = self.aggregate_metrics.get(f"avg_{field_name}", 0)
                new_avg = (current_avg * (session_count - 1) + value) / session_count
                self.aggregate_metrics[f"avg_{field_name}"] = new_avg
    
    def export_metrics(self) -> Dict[str, Any]:
        """Export metrics in a format suitable for monitoring systems."""
        return {
            "session_count": len(self.session_metrics),
            "aggregate_metrics": self.aggregate_metrics,
            "recent_sessions": list(self.session_metrics.keys())[-10:]  # Last 10 sessions
        }


# Global instances
reasoning_logger = ReasoningLogger("reasoning")
metrics_collector = MetricsCollector()


def get_current_trace_id() -> str:
    """Get the current trace ID from context."""
    return trace_id_context.get('')


def create_performance_metrics(start_time: float, tool_executions: int,
                             expansions: int, refinements: int,
                             zero_hits: int, overbroadn: int,
                             cache_hits: int, cache_misses: int,
                             timeouts: int, errors: int) -> PerformanceMetrics:
    """Create performance metrics from raw counters."""
    duration_ms = int((time.time() - start_time) * 1000)
    
    return PerformanceMetrics(
        total_duration_ms=duration_ms,
        tool_execution_count=tool_executions,
        expansion_rounds=expansions,
        refinement_rounds=refinements,
        zero_hit_recoveries=zero_hits,
        overbroad_refinements=overbroadn,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        timeout_count=timeouts,
        error_count=errors
    )


def configure_reasoning_logging(level: str = "INFO", 
                              format_json: bool = True) -> None:
    """Configure logging for the reasoning system."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Configure the reasoning logger
    reasoning_logger.logger.setLevel(log_level)
    
    if format_json:
        # JSON formatter for structured logging
        formatter = logging.Formatter('%(message)s')
    else:
        # Human-readable formatter for development
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    # Add console handler if not already present
    if not reasoning_logger.logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        reasoning_logger.logger.addHandler(handler)


# Performance monitoring decorators
def track_performance(operation_name: str):
    """Decorator to track performance of reasoning operations."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            trace_id = get_current_trace_id()
            
            try:
                result = await func(*args, **kwargs)
                duration_ms = int((time.time() - start_time) * 1000)
                
                reasoning_logger._log_structured("operation_performance", {
                    "trace_id": trace_id,
                    "operation": operation_name,
                    "duration_ms": duration_ms,
                    "success": True,
                    "timestamp": time.time()
                })
                
                return result
                
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                
                reasoning_logger._log_structured("operation_performance", {
                    "trace_id": trace_id,
                    "operation": operation_name,
                    "duration_ms": duration_ms,
                    "success": False,
                    "error": str(e),
                    "timestamp": time.time()
                })
                
                raise
        
        return wrapper
    return decorator
