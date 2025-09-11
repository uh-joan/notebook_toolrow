"""
Reasoning orchestrator implementing plan-act-observe-reflect loop.

This is the core reasoning engine that coordinates tool selection,
execution, and result refinement using intelligent strategies.
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional

from .models import FinalResponse, TraceEvent, QueryAnalysis, SearchState, ToolResult
from .config import ReasoningConfig
from .utils import is_zero, too_few, too_many, extract_terms, extract_hit_count
from .adapters import BaseAdapter
from .logging import reasoning_logger, metrics_collector, create_performance_metrics, track_performance

logger = logging.getLogger(__name__)


class ReasoningOrchestrator:
    """Core reasoning orchestrator for source discovery."""
    
    def __init__(self, adapters: Dict[str, BaseAdapter], config: Optional[ReasoningConfig] = None):
        self.adapters = adapters
        self.config = config or ReasoningConfig()
        self.trace: List[TraceEvent] = []
        self.start_time = None
        
    @track_performance("reasoning_session")
    async def run(self, task: Dict[str, Any]) -> FinalResponse:
        """Execute the full reasoning loop for a search task."""
        self.start_time = time.time()
        self.trace = []
        
        # Start logging session
        query = task.get("query", "")
        user_id = task.get("user_id", "unknown")
        trace_id = reasoning_logger.start_session(user_id, query)
        
        try:
            # Phase 1: Analyze query
            query_analysis = await self._analyze_query(task)
            
            # Phase 2: Plan initial search strategy
            search_state = await self._plan_initial_search(task, query_analysis)
            
            # Phase 3: Execute reasoning loop
            final_state = await self._reasoning_loop(search_state)
            
            # Phase 4: Finalize response
            response = await self._finalize_response(final_state, query_analysis)
            
            # End logging session
            duration_ms = int((time.time() - self.start_time) * 1000)
            reasoning_logger.end_session(response.success, duration_ms, len(response.evidence))
            
            return response
            
        except Exception as e:
            logger.error(f"Reasoning orchestrator error: {e}")
            reasoning_logger.log_error(e, {"task": task})
            
            # End logging session with failure
            duration_ms = int((time.time() - self.start_time) * 1000)
            reasoning_logger.end_session(False, duration_ms, 0)
            
            return self._create_error_response(str(e), task.get("query", ""))
    
    async def _analyze_query(self, task: Dict[str, Any]) -> QueryAnalysis:
        """Analyze the user query to determine search strategy."""
        query = task.get("query", "")
        
        # Extract entities and determine query characteristics
        entities = extract_terms(query)
        
        # Determine query type based on keywords and entities
        query_type = self._classify_query_type(query, entities)
        
        # Determine search intent (precision vs recall)
        intent = self._determine_search_intent(query, entities)
        
        # Assess complexity
        complexity = self._assess_complexity(query, entities)
        
        # Suggest initial tools
        suggested_tools = self._suggest_tools(query_type, entities)
        
        analysis = QueryAnalysis(
            query_type=query_type,
            entities=entities,
            intent=intent,
            complexity=complexity,
            suggested_tools=suggested_tools,
            confidence=0.8  # TODO: Implement confidence calculation
        )
        
        self._log_trace(
            step="analyze",
            strategy="query_analysis",
            tool=None,
            input={"query": query},
            outcome={"type": query_type, "intent": intent, "complexity": complexity},
            reason="Initial query analysis to guide search strategy"
        )
        
        return analysis
    
    async def _plan_initial_search(self, task: Dict[str, Any], analysis: QueryAnalysis) -> SearchState:
        """Plan the initial search strategy based on query analysis."""
        query = task.get("query", "")
        
        # Extract working terms
        working_terms = []
        for entity_type, terms in analysis.entities.items():
            working_terms.extend(terms)
        
        # Add the full query as a working term
        working_terms.append(query)
        
        state = SearchState(
            original_query=query,
            working_terms=working_terms,
            extracted_entities=analysis.entities
        )
        
        self._log_trace(
            step="plan",
            strategy="initial_planning",
            tool=None,
            input={"query": query, "entities": analysis.entities},
            outcome={"working_terms": len(working_terms)},
            reason="Planning initial search strategy based on query analysis"
        )
        
        return state
    
    async def _reasoning_loop(self, state: SearchState) -> SearchState:
        """Execute the main reasoning loop with expansion and refinement."""
        rounds = 0
        
        while rounds < self.config.max_rounds:
            rounds += 1
            state.round_number = rounds
            
            # Execute initial search attempts
            results = await self._execute_search_round(state)
            
            # Evaluate results
            total_hits = sum(extract_hit_count(r) for r in results if r.ok)
            
            if total_hits == 0:
                # Zero hits - try expansion strategies
                state = await self._handle_zero_hits(state, results)
            elif self.config.is_too_few(total_hits):
                # Too few hits - try expansion
                state = await self._handle_too_few_hits(state, results)
            elif self.config.is_too_many(total_hits):
                # Too many hits - try refinement
                state = await self._handle_too_many_hits(state, results)
            else:
                # Acceptable results - we're done
                state = await self._handle_acceptable_results(state, results)
                break
        
        return state
    
    async def _execute_search_round(self, state: SearchState) -> List[ToolResult]:
        """Execute a round of searches based on current state."""
        # Determine which tools to use based on current state
        tool_queries = await self._select_tools_for_round(state)
        
        # Execute searches (parallel or sequential based on dependencies)
        if self.config.enable_parallel_execution and len(tool_queries) > 1:
            results = await self._execute_parallel_searches(tool_queries)
        else:
            results = await self._execute_sequential_searches(tool_queries)
        
        # Log the search round
        self._log_trace(
            step="search_round",
            strategy="execute_searches",
            tool=None,
            input={"tools": [q["tool"] for q in tool_queries]},
            outcome={"results": len(results), "total_hits": sum(extract_hit_count(r) for r in results if r.ok)},
            reason=f"Executing search round {state.round_number}"
        )
        
        return results
    
    async def _select_tools_for_round(self, state: SearchState) -> List[Dict[str, Any]]:
        """Select tools and parameters for the current search round."""
        queries = []
        
        # Primary strategy: use the most relevant tool first
        if "codes" in state.original_query.lower() or any("icd" in term.lower() for term in state.working_terms):
            # Code-focused search
            queries.append({
                "tool": "nlm_ct_codes",
                "params": {"method": "icd-10-cm", "terms": state.working_terms[0] if state.working_terms else ""}
            })
        elif "trial" in state.original_query.lower() or "study" in state.original_query.lower():
            # Trial-focused search
            queries.append({
                "tool": "ct_gov_studies.search",
                "params": {"q": " ".join(state.working_terms[:3]), "pageSize": 10}
            })
        elif "fda" in state.original_query.lower() or "drug" in state.original_query.lower():
            # FDA-focused search
            queries.append({
                "tool": "fda_info",
                "params": {"query": state.working_terms[0] if state.working_terms else ""}
            })
        elif "pubmed" in state.original_query.lower() or "literature" in state.original_query.lower():
            # Literature-focused search
            queries.append({
                "tool": "pubmed_articles",
                "params": {"query": " ".join(state.working_terms[:3])}
            })
        else:
            # Default: try trials first as they're most common
            queries.append({
                "tool": "ct_gov_studies.search",
                "params": {"q": " ".join(state.working_terms[:3]), "pageSize": 10}
            })
        
        return queries
    
    async def _execute_parallel_searches(self, tool_queries: List[Dict[str, Any]]) -> List[ToolResult]:
        """Execute multiple tool searches in parallel."""
        async def execute_single(query):
            adapter = self.adapters.get(query["tool"])
            if adapter:
                return await adapter.call(query["params"])
            else:
                return ToolResult(
                    tool=query["tool"],
                    ok=False,
                    hits=0,
                    data=None,
                    error=f"Adapter not found for tool: {query['tool']}"
                )
        
        # Use semaphore to limit concurrency
        semaphore = asyncio.Semaphore(self.config.parallel_limit)
        
        async def bounded_execute(query):
            async with semaphore:
                return await execute_single(query)
        
        results = await asyncio.gather(
            *[bounded_execute(query) for query in tool_queries],
            return_exceptions=True
        )
        
        # Convert exceptions to ToolResult errors
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(ToolResult(
                    tool=tool_queries[i]["tool"],
                    ok=False,
                    hits=0,
                    data=None,
                    error=str(result)
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def _execute_sequential_searches(self, tool_queries: List[Dict[str, Any]]) -> List[ToolResult]:
        """Execute tool searches sequentially."""
        results = []
        
        for query in tool_queries:
            adapter = self.adapters.get(query["tool"])
            if adapter:
                result = await adapter.call(query["params"])
                results.append(result)
            else:
                results.append(ToolResult(
                    tool=query["tool"],
                    ok=False,
                    hits=0,
                    data=None,
                    error=f"Adapter not found for tool: {query['tool']}"
                ))
        
        return results
    
    async def _handle_zero_hits(self, state: SearchState, results: List[ToolResult]) -> SearchState:
        """Handle zero hit scenario with expansion strategies."""
        # Strategy 1: Try term suggestions if we used ct_gov_studies
        if any(r.tool == "ct_gov_studies" for r in results):
            suggest_adapter = self.adapters.get("ct_gov_studies.suggest")
            if suggest_adapter:
                suggest_result = await suggest_adapter.call({"q": state.working_terms[0]})
                if suggest_result.ok and suggest_result.data:
                    # Add suggested terms to working terms
                    if isinstance(suggest_result.data, list):
                        state.working_terms.extend(suggest_result.data[:3])
                    
                    self._log_trace(
                        step="expand",
                        strategy="term_suggestion",
                        tool="ct_gov_studies.suggest",
                        input={"original_term": state.working_terms[0]},
                        outcome={"suggestions_added": len(suggest_result.data) if isinstance(suggest_result.data, list) else 0},
                        reason="Zero hits - expanding with suggested terms"
                    )
        
        # Strategy 2: Try broader search with codes
        if "nlm_ct_codes" not in [r.tool for r in results]:
            codes_adapter = self.adapters.get("nlm_ct_codes")
            if codes_adapter and state.working_terms:
                codes_result = await codes_adapter.call({
                    "method": "icd-10-cm",
                    "terms": state.working_terms[0]
                })
                if codes_result.ok and codes_result.data:
                    # Extract codes and add to working terms
                    if isinstance(codes_result.data, dict) and "results" in codes_result.data:
                        codes = [item.get("code", "") for item in codes_result.data["results"][:3]]
                        state.working_terms.extend([c for c in codes if c])
                    
                    self._log_trace(
                        step="expand",
                        strategy="code_mapping",
                        tool="nlm_ct_codes",
                        input={"terms": state.working_terms[0]},
                        outcome={"codes_added": len(codes) if 'codes' in locals() else 0},
                        reason="Zero hits - expanding with medical codes"
                    )
        
        state.attempted_strategies.append("zero_hit_expansion")
        return state
    
    async def _handle_too_few_hits(self, state: SearchState, results: List[ToolResult]) -> SearchState:
        """Handle too few hits scenario with expansion strategies."""
        # Similar to zero hits but less aggressive
        state.attempted_strategies.append("too_few_expansion")
        
        self._log_trace(
            step="expand",
            strategy="broaden_search",
            tool=None,
            input={"current_hits": sum(extract_hit_count(r) for r in results if r.ok)},
            outcome={"strategy": "broaden_search"},
            reason="Too few results - broadening search parameters"
        )
        
        return state
    
    async def _handle_too_many_hits(self, state: SearchState, results: List[ToolResult]) -> SearchState:
        """Handle too many hits scenario with refinement strategies."""
        state.attempted_strategies.append("too_many_refinement")
        
        self._log_trace(
            step="refine",
            strategy="narrow_search",
            tool=None,
            input={"current_hits": sum(extract_hit_count(r) for r in results if r.ok)},
            outcome={"strategy": "narrow_search"},
            reason="Too many results - narrowing search parameters"
        )
        
        return state
    
    async def _handle_acceptable_results(self, state: SearchState, results: List[ToolResult]) -> SearchState:
        """Handle acceptable results - collect evidence."""
        from .utils import extract_entities_from_result
        
        # Extract evidence from results
        for result in results:
            if result.ok and result.data:
                entities = extract_entities_from_result(result, result.tool)
                # Convert entities to evidence items (simplified)
                from .models import EvidenceItem
                evidence_items = [
                    EvidenceItem(
                        source=result.tool,
                        id=entity.get("id"),
                        title=entity.get("title") or entity.get("name"),
                        meta=entity
                    )
                    for entity in entities
                ]
                state.add_evidence(evidence_items)
        
        self._log_trace(
            step="collect",
            strategy="evidence_extraction",
            tool=None,
            input={"results": len(results)},
            outcome={"evidence_items": len(state.evidence)},
            reason="Acceptable results - collecting evidence"
        )
        
        return state
    
    async def _finalize_response(self, state: SearchState, analysis: QueryAnalysis) -> FinalResponse:
        """Create the final response from the search state."""
        # Calculate total duration
        total_duration_ms = int((time.time() - self.start_time) * 1000) if self.start_time else None
        
        # Create structured answer
        answer = {
            "summary": f"Found {len(state.evidence)} relevant sources for: {state.original_query}",
            "total_sources": len(state.evidence),
            "search_rounds": state.round_number,
            "strategies_used": state.attempted_strategies
        }
        
        # Determine limitations
        limitations = []
        if state.round_number >= self.config.max_rounds:
            limitations.append("Search reached maximum rounds - results may be incomplete")
        if not state.evidence:
            limitations.append("No evidence found - query may be too specific or use unsupported terms")
        
        # Suggest next actions
        next_actions = []
        if not state.evidence:
            next_actions.append("Try broader search terms or different keywords")
            next_actions.append("Check spelling and terminology")
        elif len(state.evidence) < self.config.min_ok:
            next_actions.append("Consider broadening search criteria")
            next_actions.append("Try related or synonymous terms")
        
        return FinalResponse(
            answer=answer,
            evidence=state.evidence,
            trace=self.trace,
            limitations=limitations,
            next_best_actions=next_actions,
            query_analysis=analysis,
            total_duration_ms=total_duration_ms,
            success=len(state.evidence) > 0
        )
    
    def _create_error_response(self, error: str, query: str) -> FinalResponse:
        """Create an error response."""
        return FinalResponse(
            answer={"error": error, "query": query},
            evidence=[],
            trace=self.trace,
            limitations=[f"Error occurred: {error}"],
            next_best_actions=["Try again with different parameters"],
            success=False
        )
    
    def _log_trace(self, step: str, strategy: str, tool: Optional[str], 
                   input: Dict[str, Any], outcome: Dict[str, Any], reason: str) -> None:
        """Log a trace event."""
        event = TraceEvent(
            step=step,
            strategy=strategy,
            tool=tool,
            input=input,
            outcome=outcome,
            reason=reason
        )
        
        self.trace.append(event)
        
        # Log to structured logger
        reasoning_logger.log_trace_event(event)
    
    def _classify_query_type(self, query: str, entities: Dict[str, List[str]]) -> str:
        """Classify the query type based on content."""
        query_lower = query.lower()
        
        if "trial" in query_lower or "study" in query_lower:
            return "trials"
        elif "code" in query_lower or "icd" in query_lower:
            return "codes"
        elif "drug" in query_lower or "fda" in query_lower:
            return "drugs"
        elif "pubmed" in query_lower or "literature" in query_lower:
            return "literature"
        elif "sec" in query_lower or "company" in query_lower:
            return "financial"
        elif "who" in query_lower or "health data" in query_lower:
            return "health_data"
        else:
            return "general"
    
    def _determine_search_intent(self, query: str, entities: Dict[str, List[str]]) -> str:
        """Determine search intent (precision vs recall)."""
        # High precision indicators
        if any(word in query.lower() for word in ["specific", "exact", "precise"]):
            return "high_precision"
        
        # High recall indicators  
        if any(word in query.lower() for word in ["all", "any", "broad", "comprehensive"]):
            return "high_recall"
        
        # Default to balanced
        return "balanced"
    
    def _assess_complexity(self, query: str, entities: Dict[str, List[str]]) -> str:
        """Assess query complexity."""
        word_count = len(query.split())
        entity_count = sum(len(terms) for terms in entities.values())
        
        if word_count > 20 or entity_count > 5:
            return "complex"
        elif word_count > 10 or entity_count > 2:
            return "moderate"
        else:
            return "simple"
    
    def _suggest_tools(self, query_type: str, entities: Dict[str, List[str]]) -> List[str]:
        """Suggest initial tools based on query type."""
        suggestions = {
            "trials": ["ct_gov_studies.search", "ct_gov_studies.suggest"],
            "codes": ["nlm_ct_codes"],
            "drugs": ["fda_info", "ct_gov_studies.search"],
            "literature": ["pubmed_articles"],
            "financial": ["sec_edgar"],
            "health_data": ["who_health"],
            "general": ["ct_gov_studies.search", "nlm_ct_codes"]
        }
        
        return suggestions.get(query_type, suggestions["general"])
