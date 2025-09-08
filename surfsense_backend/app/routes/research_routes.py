"""Research API routes integrating RAG with Toolrow MCP."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.db import SearchSpace, User, get_async_session
from app.research.orchestrator import ResearchOrchestrator
from app.toolrow_mcp.types import AnswerPayload, Citation, EntityRecord, ToolCall
from app.users import current_active_user
from app.utils.check_ownership import check_ownership

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research", tags=["research"])


class ResearchAskRequest(BaseModel):
    """Request model for research ask endpoint."""
    question: str
    selected_source_ids: List[int] = []
    toolrow_enabled: bool = True
    search_space_id: int


class ResearchAskResponse(BaseModel):
    """Response model for research ask endpoint."""
    answer: str
    citations: List[dict]  # Using dict for flexible citation types
    coverage: float
    live_candidates: List[dict] = []
    tool_invocations: List[dict] = []
    errors: List[str] = []


@router.post("/ask", response_model=ResearchAskResponse)
async def research_ask(
    request: ResearchAskRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Execute research workflow combining RAG and Toolrow MCP.
    
    This endpoint:
    1. Performs RAG search on selected documents
    2. Calculates coverage score
    3. If coverage is low and Toolrow is enabled, calls MCP tools
    4. Synthesizes final answer with citations
    """
    try:
        logger.info(f"Research request from user {user.id}: {request.question[:100]}...")
        
        # Check if user owns the search space
        await check_ownership(session, SearchSpace, request.search_space_id, user)
        
        # Check if Toolrow MCP is enabled
        toolrow_enabled = request.toolrow_enabled and config.TOOLROW_MCP_ENABLED
        
        if not toolrow_enabled:
            logger.info("Toolrow MCP disabled, using RAG-only mode")
        
        # Create orchestrator and execute research workflow
        orchestrator = ResearchOrchestrator()
        
        result = await orchestrator.rag_then_mcp(
            question=request.question,
            document_ids=request.selected_source_ids,
            user_id=str(user.id),
            search_space_id=request.search_space_id,
            db_session=session,
            toolrow_enabled=toolrow_enabled
        )
        
        # Convert result to response format
        response = ResearchAskResponse(
            answer=result.get("answer", ""),
            citations=result.get("citations", []),
            coverage=result.get("coverage", 0.0),
            live_candidates=result.get("live_candidates", []),
            tool_invocations=result.get("tool_invocations", []),
            errors=result.get("errors", [])
        )
        
        logger.info(f"Research completed: {len(response.citations)} citations, "
                   f"{len(response.live_candidates)} live results, "
                   f"coverage: {response.coverage:.2f}")
        
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions (like permission errors)
        raise
    except Exception as e:
        logger.error(f"Error in research ask: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Research request failed: {str(e)}"
        )


@router.get("/coverage/{search_space_id}")
async def get_coverage_info(
    search_space_id: int,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Get information about RAG coverage for a search space."""
    try:
        # Check ownership
        await check_ownership(session, SearchSpace, search_space_id, user)
        
        # Get basic statistics about the search space
        from sqlalchemy import func, select
        from app.db import Document, Chunk
        
        # Count documents and chunks
        doc_count_query = select(func.count(Document.id)).where(
            Document.search_space_id == search_space_id
        )
        doc_count_result = await session.execute(doc_count_query)
        doc_count = doc_count_result.scalar() or 0
        
        chunk_count_query = select(func.count(Chunk.id)).join(Document).where(
            Document.search_space_id == search_space_id
        )
        chunk_count_result = await session.execute(chunk_count_query)
        chunk_count = chunk_count_result.scalar() or 0
        
        return {
            "search_space_id": search_space_id,
            "document_count": doc_count,
            "chunk_count": chunk_count,
            "toolrow_enabled": config.TOOLROW_MCP_ENABLED,
            "coverage_threshold": 0.6  # Could be made configurable
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting coverage info: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get coverage info: {str(e)}"
        )


@router.get("/intent-preview")
async def preview_intent(
    question: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Preview intent detection and tool routing for a question (development)."""
    try:
        if not config.TOOLROW_MCP_ENABLED:
            raise HTTPException(
                status_code=503,
                detail="Toolrow MCP is not enabled"
            )
        
        orchestrator = ResearchOrchestrator()
        
        # Detect intent
        intent = await orchestrator.detect_intent(question)
        
        # Canonicalize query
        canonicalized = await orchestrator.canonicalize_query(question)
        
        # Route to tools
        tool_calls = await orchestrator.route_tools(intent, canonicalized)
        
        return {
            "question": question,
            "intent": intent,
            "canonicalized": canonicalized,
            "tool_calls": tool_calls
        }
        
    except Exception as e:
        logger.error(f"Error in intent preview: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Intent preview failed: {str(e)}"
        )
