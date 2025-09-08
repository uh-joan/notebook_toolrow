"""Research orchestrator that combines RAG with Toolrow MCP."""

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.researcher.nodes import fetch_relevant_documents
from app.agents.researcher.qna_agent.nodes import answer_question
from app.config import config
from app.services.connector_service import ConnectorService
from app.toolrow_mcp.client import toolrow_mcp_manager
from app.toolrow_mcp.types import (
    AnswerPayload,
    Citation,
    DocumentCitation,
    EntityRecord,
    Intent,
    LiveCitation,
    ToolCall,
)

from .routing import IntentDetector, ToolRouter

logger = logging.getLogger(__name__)


class ResearchOrchestrator:
    """Orchestrates research workflow combining RAG and MCP."""
    
    def __init__(self):
        self.intent_detector = IntentDetector()
        self.tool_router = ToolRouter()
        self.coverage_threshold = 0.6  # Configurable threshold
        
    async def rag_answer(
        self,
        question: str,
        document_ids: List[int],
        user_id: str,
        search_space_id: int,
        db_session: AsyncSession
    ) -> Tuple[str, List[DocumentCitation], float]:
        """Generate RAG answer from selected documents."""
        try:
            logger.info(f"Starting RAG answer for question: {question[:100]}...")
            
            # Create connector service
            connector_service = ConnectorService(db_session, user_id=user_id)
            await connector_service.initialize_counter()
            
            # Fetch user-selected documents
            user_selected_sources = []
            user_selected_documents = []
            
            if document_ids:
                from app.agents.researcher.nodes import fetch_documents_by_ids
                
                user_selected_sources, user_selected_documents = await fetch_documents_by_ids(
                    document_ids=document_ids,
                    user_id=user_id,
                    db_session=db_session,
                )
            
            # Get relevant documents using existing RAG pipeline
            relevant_documents = await fetch_relevant_documents(
                research_questions=[question],
                user_id=user_id,
                search_space_id=search_space_id,
                db_session=db_session,
                connectors_to_search=[],  # Only use selected documents
                top_k=20,
                connector_service=connector_service,
                user_selected_sources=user_selected_sources,
            )
            
            # Combine all documents
            all_documents = user_selected_documents + relevant_documents
            
            if not all_documents:
                return "No relevant documents found to answer the question.", [], 0.0
            
            # Generate answer using QNA agent
            # This is a simplified version - in practice, you'd use the full QNA agent workflow
            answer = await self._generate_rag_answer(question, all_documents, user_id, db_session)
            
            # Extract citations from documents
            citations = self._extract_document_citations(all_documents)
            
            # Calculate coverage score (simplified heuristic)
            coverage = self._calculate_coverage(question, all_documents, citations)
            
            logger.info(f"RAG answer completed with coverage: {coverage:.2f}")
            return answer, citations, coverage
            
        except Exception as e:
            logger.error(f"Error in RAG answer generation: {e}")
            return f"Error generating answer: {e}", [], 0.0
    
    async def detect_intent(self, question: str) -> Intent:
        """Detect intent from user question."""
        return await self.intent_detector.detect(question)
    
    async def canonicalize_query(self, question: str) -> Dict[str, Any]:
        """Canonicalize query using Toolrow codes mapping."""
        # This would use Toolrow's nlm_ct_codes.map tool
        try:
            if not await toolrow_mcp_manager.is_available():
                return {"codes": [], "entities": []}
            
            # Call Toolrow canonicalization tool
            result = await toolrow_mcp_manager.invoke_toolrow_tool(
                tool_name="nlm_ct_codes.map",
                params={"query": question},
                timeout_ms=10000
            )
            
            return result.get("canonicalization", {"codes": [], "entities": []})
            
        except Exception as e:
            logger.error(f"Error in query canonicalization: {e}")
            return {"codes": [], "entities": []}
    
    async def route_tools(self, intent: Intent, canonicalized: Dict[str, Any]) -> List[ToolCall]:
        """Route intent to appropriate Toolrow tools."""
        return await self.tool_router.route(intent, canonicalized)
    
    async def rag_then_mcp(
        self,
        question: str,
        document_ids: List[int],
        user_id: str,
        search_space_id: int,
        db_session: AsyncSession,
        toolrow_enabled: bool = True
    ) -> AnswerPayload:
        """Execute complete RAG + MCP research workflow."""
        logger.info(f"Starting research workflow for: {question[:100]}...")
        
        # Step 1: Get RAG answer
        rag_answer, rag_citations, coverage = await self.rag_answer(
            question, document_ids, user_id, search_space_id, db_session
        )
        
        # Step 2: Check if RAG is sufficient
        if coverage >= self.coverage_threshold or not toolrow_enabled:
            logger.info(f"RAG sufficient (coverage: {coverage:.2f}) or MCP disabled")
            return AnswerPayload(
                answer=rag_answer,
                citations=rag_citations,
                coverage=coverage,
                live_candidates=[],
                tool_invocations=[]
            )
        
        # Step 3: RAG coverage is low, invoke MCP
        logger.info(f"RAG coverage low ({coverage:.2f}), invoking MCP tools...")
        
        try:
            # Detect intent and canonicalize
            intent = await self.detect_intent(question)
            canonicalized = await self.canonicalize_query(question)
            
            # Route to appropriate tools
            tool_calls = await self.route_tools(intent, canonicalized)
            
            if not tool_calls:
                logger.info("No appropriate tools found for query")
                return AnswerPayload(
                    answer=rag_answer,
                    citations=rag_citations,
                    coverage=coverage,
                    live_candidates=[],
                    tool_invocations=[]
                )
            
            # Execute tools in parallel (respecting budget limits)
            max_calls = min(len(tool_calls), config.TOOLROW_MCP_MAX_CALLS_PER_ASK)
            limited_tool_calls = tool_calls[:max_calls]
            
            logger.info(f"Executing {len(limited_tool_calls)} MCP tool calls")
            mcp_results = await toolrow_mcp_manager.parallel_invoke(
                limited_tool_calls,
                timeout_ms=config.TOOLROW_MCP_TIMEOUT_MS
            )
            
            # Normalize results to EntityRecords
            live_candidates = await self._normalize_mcp_results(mcp_results, limited_tool_calls)
            
            # Synthesize final answer
            final_answer = await self._synthesize_answer(rag_answer, live_candidates, question)
            
            # Create live citations
            live_citations = self._create_live_citations(live_candidates, limited_tool_calls)
            
            # Combine all citations
            all_citations = rag_citations + live_citations
            
            logger.info(f"Research workflow completed with {len(live_candidates)} live results")
            return AnswerPayload(
                answer=final_answer,
                citations=all_citations,
                coverage=coverage,
                live_candidates=live_candidates,
                tool_invocations=limited_tool_calls
            )
            
        except Exception as e:
            logger.error(f"Error in MCP workflow: {e}")
            # Fallback to RAG-only answer
            return AnswerPayload(
                answer=rag_answer,
                citations=rag_citations,
                coverage=coverage,
                live_candidates=[],
                tool_invocations=[],
                errors=[str(e)]
            )
    
    async def _generate_rag_answer(
        self,
        question: str,
        documents: List[Dict[str, Any]],
        user_id: str,
        db_session: AsyncSession
    ) -> str:
        """Generate answer using RAG pipeline."""
        # This is a simplified version - in practice, you'd integrate with the full QNA agent
        if not documents:
            return "No relevant documents found."
        
        # Extract content from documents
        content_parts = []
        for doc in documents[:10]:  # Limit to top 10 documents
            content = doc.get("content", "")
            if content:
                content_parts.append(content[:500])  # Truncate for brevity
        
        if not content_parts:
            return "No content found in documents."
        
        # Simple answer generation (in practice, this would use an LLM)
        return f"Based on the available documents: {' '.join(content_parts[:3])}..."
    
    def _extract_document_citations(self, documents: List[Dict[str, Any]]) -> List[DocumentCitation]:
        """Extract citations from document results."""
        citations = []
        
        for doc in documents:
            if doc.get("id") and doc.get("title"):
                citation = DocumentCitation(
                    type="doc",
                    source_id=str(doc["id"]),
                    title=doc["title"],
                    excerpt=doc.get("content", "")[:200] + "..." if doc.get("content") else ""
                )
                citations.append(citation)
        
        return citations
    
    def _calculate_coverage(
        self,
        question: str,
        documents: List[Dict[str, Any]],
        citations: List[DocumentCitation]
    ) -> float:
        """Calculate coverage score using simple heuristics."""
        # Simple heuristic: coverage based on number of citations and content relevance
        if not citations:
            return 0.0
        
        # Base score from number of citations
        citation_score = min(len(citations) / 3.0, 1.0)  # Up to 3 citations = full score
        
        # Content relevance score (simplified)
        question_words = set(question.lower().split())
        relevance_scores = []
        
        for doc in documents[:5]:  # Check top 5 documents
            content = doc.get("content", "").lower()
            content_words = set(content.split())
            
            # Simple word overlap
            overlap = len(question_words.intersection(content_words))
            relevance = overlap / max(len(question_words), 1)
            relevance_scores.append(relevance)
        
        avg_relevance = sum(relevance_scores) / max(len(relevance_scores), 1) if relevance_scores else 0
        
        # Combine scores
        coverage = (citation_score * 0.6) + (avg_relevance * 0.4)
        return min(coverage, 1.0)
    
    async def _normalize_mcp_results(
        self,
        mcp_results: List[Dict[str, Any]],
        tool_calls: List[ToolCall]
    ) -> List[EntityRecord]:
        """Normalize MCP results to EntityRecord format."""
        normalized_results = []
        
        for i, result in enumerate(mcp_results):
            if "error" in result:
                logger.error(f"MCP tool {tool_calls[i].get('tool')} failed: {result['error']}")
                continue
            
            try:
                # Get the appropriate normalizer based on tool
                tool_name = tool_calls[i].get("tool", "")
                provider = self._extract_provider_from_tool(tool_name)
                
                # Use the appropriate normalizer
                normalizer = self._get_normalizer(provider)
                if normalizer:
                    entities = normalizer.normalize(result)
                    normalized_results.extend(entities)
                else:
                    logger.warning(f"No normalizer found for provider: {provider}")
                    
            except Exception as e:
                logger.error(f"Error normalizing MCP result: {e}")
        
        return normalized_results
    
    def _extract_provider_from_tool(self, tool_name: str) -> str:
        """Extract provider name from tool name."""
        # Map tool names to providers
        if "fda" in tool_name.lower():
            return "fda"
        elif "ct_gov" in tool_name.lower() or "clinicaltrials" in tool_name.lower():
            return "ct_gov"
        elif "pubmed" in tool_name.lower():
            return "pubmed"
        elif "sec" in tool_name.lower():
            return "sec"
        elif "who" in tool_name.lower():
            return "who"
        else:
            return "unknown"
    
    def _get_normalizer(self, provider: str):
        """Get the appropriate normalizer for a provider."""
        from app.toolrow_mcp.normalizers.fda import FDANormalizer
        
        normalizers = {
            "fda": FDANormalizer(),
            # Add other normalizers as they're implemented
        }
        
        return normalizers.get(provider)
    
    async def _synthesize_answer(
        self,
        rag_answer: str,
        live_candidates: List[EntityRecord],
        question: str
    ) -> str:
        """Synthesize final answer combining RAG and MCP results."""
        if not live_candidates:
            return rag_answer
        
        # Simple synthesis - in practice, this would use an LLM
        live_info = []
        for candidate in live_candidates[:5]:  # Limit to top 5
            title = candidate.get("title", "Unknown")
            summary = candidate.get("summary", "")
            if summary:
                live_info.append(f"{title}: {summary[:100]}...")
            else:
                live_info.append(title)
        
        if live_info:
            live_section = "\\n\\nAdditional live information:\\n" + "\\n".join(f"• {info}" for info in live_info)
            return rag_answer + live_section
        
        return rag_answer
    
    def _create_live_citations(
        self,
        live_candidates: List[EntityRecord],
        tool_calls: List[ToolCall]
    ) -> List[LiveCitation]:
        """Create citations for live MCP results."""
        citations = []
        
        for candidate in live_candidates:
            citation = LiveCitation(
                type="live",
                provider=candidate.get("provider", "unknown"),
                kind=candidate.get("kind", "unknown"),
                canonical_id=candidate.get("canonical_id", ""),
                title=candidate.get("title", "Unknown"),
                params_hash=self._hash_params(tool_calls),
                uri=candidate.get("uri")
            )
            citations.append(citation)
        
        return citations
    
    def _hash_params(self, tool_calls: List[ToolCall]) -> str:
        """Create a hash of tool parameters for caching."""
        import hashlib
        import json
        
        # Create a stable hash of all tool parameters
        params_str = json.dumps([call.get("params", {}) for call in tool_calls], sort_keys=True)
        return hashlib.md5(params_str.encode()).hexdigest()[:16]
