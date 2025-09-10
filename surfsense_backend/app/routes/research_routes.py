"""Research API routes using the original researcher agent workflow."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.db import SearchSpace, User, get_async_session
from app.users import current_active_user
from app.utils.check_ownership import check_ownership

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research", tags=["research"])


class ResearchAskRequest(BaseModel):
    """Request model for research ask endpoint."""
    question: str
    selected_source_ids: List[int] = []
    search_space_id: int


class ResearchAskResponse(BaseModel):
    """Response model for research ask endpoint."""
    answer: str
    citations: List[dict] = []  # Basic citations from original researcher
    errors: List[str] = []


@router.post("/ask", response_model=ResearchAskResponse)
async def research_ask(
    request: ResearchAskRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Execute original researcher workflow using pure RAG over existing documents.
    
    This endpoint uses the same researcher agent as the chat interface,
    but returns a structured response instead of streaming.
    """
    try:
        logger.info(f"Research request from user {user.id}: {request.question[:100]}...")
        
        # Check if user owns the search space
        await check_ownership(session, SearchSpace, request.search_space_id, user)
        
        # Use the original researcher workflow
        from app.tasks.stream_connector_search_results import stream_connector_search_results
        
        # Collect all streaming output
        full_answer = ""
        async for chunk in stream_connector_search_results(
            user_query=request.question,
            user_id=str(user.id),
            search_space_id=request.search_space_id,
            session=session,
            research_mode="QNA",  # Use QNA mode for direct answers
            selected_connectors=[],  # Only use selected documents
            langchain_chat_history=[],
            search_mode_str="CHUNKS",
            document_ids_to_add_in_context=request.selected_source_ids,
        ):
            full_answer += chunk
        
        # For now, return simplified response (could be enhanced to extract citations)
        response = ResearchAskResponse(
            answer=full_answer.strip(),
            citations=[],  # Could extract from the full_answer if needed
            errors=[]
        )
        
        logger.info(f"Original research workflow completed")
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


