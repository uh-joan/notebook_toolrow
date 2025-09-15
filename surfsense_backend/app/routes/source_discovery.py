"""
API routes for Source Discovery Agent
"""

import logging
import os
from typing import List, Optional, Dict, Any
from sqlalchemy import select
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, WebSocket, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import json
import uuid
import time
from collections import defaultdict
from langchain_core.messages import HumanMessage, AIMessage

from ..agents.source_discovery import create_discovery_agent, DiscoveryRequest, DiscoveryResult, SourceSuggestion
from ..agents.source_discovery.claude_agent import create_claude_discovery_agent
from ..toolrow_mcp.client import ToolrowMCPManager
from ..users import current_active_user, User
from ..db import get_async_session, Document, DocumentType, Chat, ChatType, SearchSpace
from ..tasks.document_processors.markdown_processor import add_received_markdown_file_document
from ..services.streaming_service import StreamingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/source-discovery", tags=["source-discovery"])


# Request/Response models for save-source endpoint
class SaveSourceRequest(BaseModel):
    """Request to save a discovered source to the knowledge base."""
    search_space_id: int
    source_suggestion: Dict[str, Any]  # The suggestion object from discovery results
    export_format: str = "markdown"  # markdown, csv, json, docx

# Request/Response models for save-answer endpoint
class SaveAnswerRequest(BaseModel):
    """Request to save a discovery final answer to the knowledge base."""
    search_space_id: int
    content: str  # The final answer content
    format: str = "md"  # md, docx, pdf
    title: str = "Discovery Answer"

class SaveAnswerResponse(BaseModel):
    """Response from saving a discovery answer."""
    success: bool
    message: str
    document_id: Optional[int] = None


class SaveSourceResponse(BaseModel):
    """Response from saving a discovered source."""
    success: bool
    message: str
    document_id: Optional[int] = None


# Request/Response models for format-response endpoint  
class FormatResponseRequest(BaseModel):
    """Request to format discovery results."""
    query: str
    suggestions: List[Dict[str, Any]]
    dataAnalysis: List[Dict[str, Any]]


class FormatResponseResponse(BaseModel):
    """Response with formatted discovery results."""
    formatted_response: str


async def _format_source_content(suggestion_data: Dict[str, Any], export_format: str) -> str:
    """Format source content based on export format."""
    metadata = suggestion_data.get("metadata", {})
    content = suggestion_data.get("content", "")
    content_preview = suggestion_data.get("content_preview", "")
    
    if export_format == "csv":
        # For structured data like ICD codes, convert to CSV format
        try:
            if content:
                # Try to parse JSON content for structured data
                json_data = json.loads(content)
                if isinstance(json_data, dict) and "results" in json_data:
                    results = json_data["results"]
                    if isinstance(results, list) and len(results) > 0:
                        # Create CSV from structured results
                        import csv
                        import io
                        output = io.StringIO()
                        
                        if isinstance(results[0], dict):
                            writer = csv.DictWriter(output, fieldnames=results[0].keys())
                            writer.writeheader()
                            writer.writerows(results)
                        else:
                            writer = csv.writer(output)
                            for row in results:
                                writer.writerow([row] if not isinstance(row, list) else row)
                        
                        return output.getvalue()
        except (json.JSONDecodeError, KeyError):
            pass
        
        # Fallback to simple content
        return content or content_preview
    
    elif export_format == "json":
        # Return raw JSON content
        return content or json.dumps({"preview": content_preview, "metadata": metadata})
    
    elif export_format == "docx":
        # Generate DOCX document content (will be converted to actual DOCX in processing)
        title = metadata.get("title", "Discovered Source")
        source_type = metadata.get("source_type", "unknown")
        relevance = metadata.get("relevance_score", 0.0)
        tags = metadata.get("tags", [])
        
        # Create structured content for DOCX conversion
        docx_content = {
            "title": title,
            "metadata": {
                "source_type": source_type,
                "relevance_score": relevance,
                "tags": tags,
                "export_format": "docx"
            },
            "content": content,
            "content_preview": content_preview
        }
        
        # Return JSON that will be processed into DOCX format
        return json.dumps(docx_content, indent=2)
    
    else:  # markdown (default)
        # Format as markdown document
        title = metadata.get("title", "Discovered Source")
        source_type = metadata.get("source_type", "unknown")
        relevance = metadata.get("relevance_score", 0.0)
        tags = metadata.get("tags", [])
        
        formatted = f"# {title}\n\n"
        formatted += f"**Source Type:** {source_type}\n"
        formatted += f"**Relevance Score:** {relevance:.2%}\n"
        
        if tags:
            formatted += f"**Tags:** {', '.join(tags)}\n"
        
        formatted += f"\n## Content\n\n"
        
        # Try to format content nicely if it's JSON
        try:
            if content:
                json_data = json.loads(content)
                if isinstance(json_data, dict) and "results" in json_data:
                    results = json_data["results"]
                    if isinstance(results, list):
                        for i, item in enumerate(results[:20], 1):  # Limit to first 20 items
                            if isinstance(item, dict):
                                formatted += f"### Item {i}\n\n"
                                for key, value in item.items():
                                    formatted += f"**{key}:** {value}\n"
                                formatted += "\n"
                            else:
                                formatted += f"- {item}\n"
                        
                        if len(results) > 20:
                            formatted += f"\n*... and {len(results) - 20} more items*\n"
                    else:
                        formatted += f"{json.dumps(json_data, indent=2)}\n"
                else:
                    formatted += f"```json\n{json.dumps(json_data, indent=2)}\n```\n"
            else:
                formatted += content_preview
        except json.JSONDecodeError:
            # Not JSON, use as-is
            formatted += content or content_preview
        
        return formatted


async def _create_docx_content(json_content: str, title: str, metadata: Dict[str, Any]) -> str:
    """Convert structured JSON content to DOCX-style formatted content."""
    try:
        # Parse the JSON content created for DOCX
        docx_data = json.loads(json_content)
        
        # Extract data
        doc_title = docx_data.get("title", title)
        doc_metadata = docx_data.get("metadata", {})
        content = docx_data.get("content", "")
        content_preview = docx_data.get("content_preview", "")
        
        # Create a structured text format that can be easily converted to DOCX
        # For now, we'll create a rich text format that includes formatting cues
        docx_formatted = f"""DOCUMENT_TITLE: {doc_title}

METADATA_SECTION:
Source Type: {doc_metadata.get('source_type', 'unknown')}
Relevance Score: {doc_metadata.get('relevance_score', 0.0):.2%}
Tags: {', '.join(doc_metadata.get('tags', []))}
Export Format: DOCX
Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}

CONTENT_SECTION:
"""
        
        # Add content with proper formatting
        if content:
            try:
                # Try to format JSON content nicely
                json_data = json.loads(content)
                if isinstance(json_data, dict) and "results" in json_data:
                    results = json_data["results"]
                    if isinstance(results, list):
                        docx_formatted += "STRUCTURED_DATA:\n\n"
                        for i, item in enumerate(results[:50], 1):  # Limit to first 50 items for DOCX
                            if isinstance(item, dict):
                                docx_formatted += f"Item {i}:\n"
                                for key, value in item.items():
                                    docx_formatted += f"  {key}: {value}\n"
                                docx_formatted += "\n"
                            else:
                                docx_formatted += f"  {i}. {item}\n"
                        
                        if len(results) > 50:
                            docx_formatted += f"\n[Additional {len(results) - 50} items not shown in document]\n"
                    else:
                        docx_formatted += f"DATA_CONTENT:\n{json.dumps(json_data, indent=2)}\n"
                else:
                    docx_formatted += f"RAW_DATA:\n{json.dumps(json_data, indent=2)}\n"
            except json.JSONDecodeError:
                # Not JSON, use as-is
                docx_formatted += f"CONTENT:\n{content}\n"
        else:
            docx_formatted += f"PREVIEW:\n{content_preview}\n"
        
        return docx_formatted
        
    except Exception as e:
        logger.error(f"❌ Error creating DOCX content: {e}")
        # Fallback to simple format
        return f"DOCUMENT: {title}\n\nCONTENT:\n{json_content}"


async def _process_discovered_source_document(
    content: str,
    title: str,
    search_space_id: int,
    export_format: str,
    metadata: Dict[str, Any],
    user_id: uuid.UUID
):
    """Process discovered source as a document (background task)."""
    # Import here to avoid circular imports
    from ..db import async_session_maker

    async with async_session_maker() as db_session:
        try:
            # Use DISCOVERED_SOURCE type for all discovery-based documents
            document_type = DocumentType.DISCOVERED_SOURCE

            # If DOCX format, convert structured content to actual DOCX
            if export_format == "docx":
                content = await _create_docx_content(content, title, metadata)

            # Create document entry
            new_document = Document(
                title=title,
                search_space_id=search_space_id,
                user_id=user_id,
                content=content,
                content_hash=str(hash(content)),
                document_type=document_type,
                json_metadata=metadata
            )

            db_session.add(new_document)
            await db_session.commit()
            await db_session.refresh(new_document)

            logger.info(f"📄 Saved discovered source as document {new_document.id}: {title}")

            # TODO: Add to chunking/indexing queue if needed

            return new_document.id

        except Exception as e:
            logger.error(f"❌ Error processing discovered source document: {e}")
            await db_session.rollback()
            return None


async def save_discovery_chat(
    user_query: str,
    assistant_response: str,
    search_space_id: int,
    selected_tools: List[str],
    discovery_data: dict,
    user: User,
    session: AsyncSession
) -> Optional[int]:
    """Save discovery conversation to chat history"""
    logger.info(f"🚨 SAVE_DISCOVERY_CHAT CALLED - Creating new chat for query: {user_query[:50]}...")
    try:
        # Create messages in the same format as researcher agent
        messages = [
            {
                "id": str(uuid.uuid4()),
                "role": "user",
                "content": user_query,
                "timestamp": time.time()
            },
            {
                "id": str(uuid.uuid4()),
                "role": "assistant", 
                "content": assistant_response,
                "data": discovery_data,
                "timestamp": time.time()
            }
        ]
        
        # Create chat title from user query (truncate if too long)
        title = user_query[:50] + "..." if len(user_query) > 50 else user_query
        
        # Create chat record
        chat = Chat(
            type=ChatType.DISCOVERY,
            title=title,
            initial_connectors=selected_tools,  # Store selected tools
            messages=messages,
            search_space_id=search_space_id
        )
        
        session.add(chat)
        await session.commit()
        await session.refresh(chat)
        
        logger.info(f"💾 Saved discovery chat {chat.id}: {title}")
        return chat.id
        
    except Exception as e:
        logger.error(f"❌ Failed to save discovery chat: {e}")
        await session.rollback()
        return None

# Simple rate limiting - in production, use Redis or a proper rate limiting service
_rate_limit_cache = defaultdict(list)
_rate_limit_window = 60  # 1 minute window
_rate_limit_max_requests = 10  # 10 requests per minute per user

def check_rate_limit(user_id: str) -> bool:
    """Check if user has exceeded rate limit for discovery requests."""
    now = time.time()
    user_requests = _rate_limit_cache[user_id]
    
    # Remove old requests outside the window
    user_requests[:] = [req_time for req_time in user_requests if now - req_time < _rate_limit_window]
    
    # Check if under limit
    if len(user_requests) >= _rate_limit_max_requests:
        return False
    
    # Add current request
    user_requests.append(now)
    return True


class DiscoveryRequestAPI(BaseModel):
    """API request model for source discovery"""
    query: str
    discovery_mode: Optional[str] = "BASIC"  # Discovery complexity level
    focus_areas: Optional[List[str]] = None
    filters: Optional[dict] = None
    max_sources: Optional[int] = 50
    export_format: Optional[str] = "json"


class DiscoveryStatusResponse(BaseModel):
    """Response for discovery status"""
    status: str
    message: str
    tools_available: int


class SaveSourceRequest(BaseModel):
    """Request model for saving a discovered source"""
    search_space_id: int
    source_suggestion: dict  # SourceSuggestion as dict
    export_format: Optional[str] = "markdown"  # "markdown", "csv", "json"


class SaveSourceResponse(BaseModel):
    """Response for source saving"""
    success: bool
    message: str
    document_id: Optional[int] = None
    export_path: Optional[str] = None


class BulkSaveRequest(BaseModel):
    """Request model for bulk saving multiple sources"""
    search_space_id: int
    source_suggestions: List[dict]  # List of SourceSuggestion as dict
    export_format: Optional[str] = "markdown"
    combine_into_single_document: Optional[bool] = False


class FormatResponseRequest(BaseModel):
    """Request model for AI-powered response formatting"""
    query: str
    suggestions: List[dict]
    dataAnalysis: List[dict]
    metadata: dict


class FormatResponseResponse(BaseModel):
    """Response model for formatted discovery results"""
    formatted_response: str


@router.get("/status", response_model=DiscoveryStatusResponse)
async def get_discovery_status():
    """Get the status of the source discovery service."""
    try:
        # Initialize MCP manager to check tool availability
        mcp_manager = ToolrowMCPManager()
        
        available_tools = await mcp_manager.list_available_tools()
        tool_count = len(available_tools)
        
        return DiscoveryStatusResponse(
            status="ready" if tool_count > 0 else "limited",
            message=f"Source discovery ready with {tool_count} tools available",
            tools_available=tool_count
        )
    
    except Exception as e:
        logger.error(f"Error checking discovery status: {e}")
        return DiscoveryStatusResponse(
            status="error",
            message=f"Service unavailable: {str(e)}",
            tools_available=0
        )


@router.get("/export-formats")
async def get_available_export_formats(
    user=Depends(current_active_user)
):
    """
    Get available export formats for discovery results.
    """
    try:
        # Create a temporary agent to get export formats
        agent = SourceDiscoveryAgent()
        mcp_manager = ToolrowMCPManager()
        await agent.initialize(mcp_manager)
        
        formats = agent.result_processor.get_available_export_formats()
        
        return {
            "available_formats": formats,
            "format_descriptions": {
                "json": "Structured JSON data for API consumption",
                "csv": "Spreadsheet-compatible comma-separated values",
                "markdown": "Human-readable markdown format",
                "pdf": "Professional PDF report with charts and tables",
                "excel": "Excel workbook with multiple sheets and charts",
                "powerpoint": "PowerPoint presentation for sharing",
                "docx": "Microsoft Word document for editing"
            }
        }
    except Exception as e:
        logger.error(f"Failed to get export formats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get export formats: {str(e)}")


@router.get("/cache-stats")
async def get_cache_statistics(
    user=Depends(current_active_user)
):
    """
    Get cache statistics and performance metrics.
    """
    try:
        # Create a temporary agent to get cache stats
        agent = SourceDiscoveryAgent()
        mcp_manager = ToolrowMCPManager()
        await agent.initialize(mcp_manager)
        
        stats = agent.cache_manager.get_cache_stats()
        
        return {
            "cache_statistics": stats,
            "cache_recommendations": {
                "hit_rate_target": "70%+",
                "current_performance": "good" if float(stats["hit_rate"].rstrip('%')) > 70 else "needs_improvement",
                "suggestions": [
                    "Use similar queries to benefit from caching",
                    "Cache is most effective for repeated complex queries",
                    "Clear cache if data seems outdated"
                ] if float(stats["hit_rate"].rstrip('%')) < 70 else [
                    "Cache is performing well",
                    "Continue using similar query patterns"
                ]
            }
        }
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get cache stats: {str(e)}")


@router.post("/discover", response_model=DiscoveryResult)
async def discover_sources(
    request: DiscoveryRequestAPI,
    user=Depends(current_active_user),
    db_session=Depends(get_async_session)
):
    """
    Discover new sources based on a query.
    
    This endpoint uses MCP tools to find live data sources that could be
    added to the knowledge base, such as:
    - Active clinical trials
    - FDA drug information  
    - Recent research papers
    - Regulatory documents
    """
    try:
        # Rate limiting check
        if not check_rate_limit(str(user.id)):
            raise HTTPException(
                status_code=429, 
                detail=f"Rate limit exceeded. Maximum {_rate_limit_max_requests} requests per {_rate_limit_window} seconds."
            )
        # Convert API request to internal format
        discovery_request = DiscoveryRequest(
            query=request.query,
            user_id=user.id,
            discovery_mode=request.discovery_mode,
            focus_areas=request.focus_areas,
            filters=request.filters,
            max_sources=request.max_sources,
            export_format=request.export_format
        )
        
        # Initialize discovery agent
        agent = SourceDiscoveryAgent()
        
        # Initialize MCP manager
        mcp_manager = ToolrowMCPManager()
        await agent.initialize(mcp_manager)
        
        # Execute discovery
        logger.info(f"🔍 Starting source discovery for user {user.id}: {request.query}")
        result = await agent.discover_sources(discovery_request, db_session)
        
        logger.info(f"✅ Discovery completed: {result.total_found} sources found")
        return result
    
    except Exception as e:
        logger.error(f"❌ Source discovery failed: {e}")
        raise HTTPException(status_code=500, detail=f"Discovery failed: {str(e)}")


@router.get("/tools")
async def list_available_tools():
    """List all available MCP tools for source discovery."""
    try:
        mcp_manager = ToolrowMCPManager()
        
        tools = await mcp_manager.list_available_tools()
        
        # Format for easier consumption
        formatted_tools = []
        for tool in tools:
            formatted_tools.append({
                "name": tool.get("name", "unknown"),
                "description": tool.get("description", ""),
                "category": _categorize_tool(tool.get("name", "")),
                "parameters": list(tool.get("inputSchema", {}).get("properties", {}).keys())
            })
        
        return {
            "total_tools": len(formatted_tools),
            "tools": formatted_tools
        }
    
    except Exception as e:
        logger.error(f"Error listing tools: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list tools: {str(e)}")


def _categorize_tool(tool_name: str) -> str:
    """Categorize a tool based on its name."""
    name_lower = tool_name.lower()
    
    if "clinical" in name_lower or "trial" in name_lower:
        return "clinical_trials"
    elif "fda" in name_lower:
        return "regulatory"
    elif "pubmed" in name_lower or "research" in name_lower:
        return "research"
    elif "sec" in name_lower:
        return "financial"
    elif "who" in name_lower:
        return "health_organization"
    else:
        return "general"


# Example usage endpoints for testing

@router.post("/discover/clinical-trials")
async def discover_clinical_trials(
    condition: str,
    status: str = "recruiting",
    user=Depends(current_active_user),
    db_session=Depends(get_async_session)
):
    """
    Quick endpoint to discover clinical trials for a specific condition.
    
    Example: POST /api/source-discovery/discover/clinical-trials
    Body: {"condition": "obesity", "status": "recruiting"}
    """
    query = f"clinical trials for {condition}"
    if status != "all":
        query += f" that are {status}"
    
    request = DiscoveryRequestAPI(
        query=query,
        focus_areas=["clinical_trials"],
        filters={"status": status},
        max_sources=20
    )
    
    return await discover_sources(request, user, db_session)


@router.post("/discover/fda-drugs")
async def discover_fda_drugs(
    condition: str,
    user=Depends(current_active_user),
    db_session=Depends(get_async_session)
):
    """
    Quick endpoint to discover FDA-approved drugs for a condition.
    
    Example: POST /api/source-discovery/discover/fda-drugs
    Body: {"condition": "obesity"}
    """
    request = DiscoveryRequestAPI(
        query=f"FDA approved drugs for {condition}",
        focus_areas=["regulatory"],
        max_sources=15
    )
    
    return await discover_sources(request, user, db_session)


@router.post("/save-source", response_model=SaveSourceResponse)
async def save_discovered_source(
    request: SaveSourceRequest,
    user: User = Depends(current_active_user),
    db_session: AsyncSession = Depends(get_async_session),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Save a discovered source to the knowledge base as a document.
    
    Supports different export formats:
    - markdown: Save as structured markdown document  
    - csv: Save structured data (ICD codes, etc.) as CSV
    - json: Save raw JSON data
    - docx: Save as structured DOCX document with formatting
    """
    try:
        # Parse the source suggestion
        suggestion_data = request.source_suggestion
        metadata = suggestion_data.get("metadata", {})
        content = suggestion_data.get("content", "")
        
        # Check ownership of search space
        from ..utils.check_ownership import check_ownership  
        from ..db import SearchSpace
        await check_ownership(db_session, SearchSpace, request.search_space_id, user)
        
        # Determine title and content based on source type and format
        source_type = metadata.get("source_type", "unknown")
        tool_tags = metadata.get("tags", [])
        title = metadata.get("title", "Discovered Source")
        
        # Generate formatted content based on export format
        formatted_content = await _format_source_content(
            suggestion_data, request.export_format
        )
        
        # Create document metadata
        document_metadata = {
            "source_type": source_type,
            "discovery_tool": tool_tags[0] if tool_tags else "unknown",
            "export_format": request.export_format,
            "relevance_score": metadata.get("relevance_score", 0.0),
            "discovery_timestamp": str(uuid.uuid4())  # Unique identifier for this discovery
        }
        
        # Add to document processing queue
        background_tasks.add_task(
            _process_discovered_source_document,
            formatted_content,
            title,
            request.search_space_id,
            request.export_format,
            document_metadata,
            user.id
        )
        
        return SaveSourceResponse(
            success=True,
            message=f"Source '{title}' queued for processing as {request.export_format}",
            document_id=None  # Will be set after processing
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to save source: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save source: {str(e)}")


@router.post("/save-answer", response_model=SaveAnswerResponse)
async def save_discovery_answer(
    request: SaveAnswerRequest,
    user: User = Depends(current_active_user),
    db_session: AsyncSession = Depends(get_async_session),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Save a discovery final answer to the knowledge base as a document.
    
    Supports different formats:
    - md: Save as markdown document  
    - docx: Save as DOCX document
    - pdf: Save as PDF document
    """
    try:
        # Check ownership of search space
        from ..utils.check_ownership import check_ownership  
        from ..db import SearchSpace
        await check_ownership(db_session, SearchSpace, request.search_space_id, user)
        
        # Create document metadata
        document_metadata = {
            "source_type": "discovery_answer",
            "export_format": request.format,
            "discovery_timestamp": str(uuid.uuid4()),
            "created_by": "source_discovery_agent"
        }
        
        # Use the markdown processor to add the document
        background_tasks.add_task(
            add_received_markdown_file_document,
            session=db_session,
            file_name=f"{request.title}.{request.format}",
            file_in_markdown=request.content,
            search_space_id=request.search_space_id,
            user_id=user.id
        )
        
        return SaveAnswerResponse(
            success=True,
            message=f"Discovery answer '{request.title}' queued for processing as {request.format.upper()}",
            document_id=None  # Will be set after processing
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to save discovery answer: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save discovery answer: {str(e)}")


@router.post("/format-response", response_model=FormatResponseResponse)
async def format_discovery_response(
    request: FormatResponseRequest,
    user: User = Depends(current_active_user),
    db_session: AsyncSession = Depends(get_async_session)
):
    """
    Use AI to intelligently format discovery results based on data characteristics.
    This replaces hardcoded formatting logic with flexible AI-powered formatting.
    """
    try:
        from ..services.llm_service import get_user_llm_instance, LLMRole
        
        # Get the user's LLM instance for formatting
        llm = await get_user_llm_instance(db_session, str(user.id), LLMRole.FAST)
        
        # Analyze the data characteristics
        data_summary = []
        for analysis in request.dataAnalysis:
            tool_name = analysis.get('tool', 'unknown')
            data_size = analysis.get('dataSize', 0)
            has_structured = analysis.get('hasStructuredData', False)
            sample_data = analysis.get('sampleData', [])
            
            data_summary.append(f"- {tool_name}: {data_size} items, structured: {has_structured}")
            if sample_data and len(sample_data) > 0:
                data_summary.append(f"  Sample: {sample_data[0] if sample_data else 'N/A'}")
        
        # Create AI formatting prompt
        formatting_prompt = f"""
        Format a discovery response for this query: "{request.query}"
        
        DATA CHARACTERISTICS:
        {chr(10).join(data_summary)}
        
        GUIDELINES:
        1. For small datasets (≤50 items): Show ALL items with clear formatting
        2. For medium datasets (51-200): Show first 15-20 with summary of total
        3. For large datasets (>200): Show first 10 with clear indication of total
        4. For ICD codes: Use "**CODE** - Description" format
        5. For clinical trials: Include title, status, phase
        6. For research papers: Include title, authors, journal
        7. For FDA data: Include drug name, approval status, date
        
        RESPONSE STRUCTURE:
        - Start with conversational intro based on query type
        - Present data in appropriate format (list, table, summary)
        - Add context about data source and reliability
        - End with source breakdown and call-to-action
        
        Make the response conversational, informative, and appropriately detailed based on the data size.
        Always include: "💡 **Click 'Save to Documents' below to add these results to your knowledge base.**"
        
        Raw suggestions data: {json.dumps(request.suggestions, indent=2)[:2000]}...
        """
        
        # Get AI-formatted response
        response = await llm.ainvoke(formatting_prompt)
        formatted_text = response.content.strip()
        
        # Add source breakdown
        if request.suggestions:
            formatted_text += "\n\n**Sources used:**\n"
            for suggestion in request.suggestions:
                metadata = suggestion.get('metadata', {})
                tool_name = 'unknown tool'
                for tag in metadata.get('tags', []):
                    if tag in ['nlm_ct_codes', 'pubmed_articles', 'ct_gov_studies', 'fda_info']:
                        tool_name = tag.replace('_', ' ').upper()
                        break
                
                relevance = int((metadata.get('relevance_score', 0.6) * 100))
                formatted_text += f"• {tool_name}: {relevance}% relevance\n"
        
        # Ensure call-to-action is present
        if "Click 'Save to Documents'" not in formatted_text:
            formatted_text += "\n💡 **Click 'Save to Documents' below to add these results to your knowledge base.**"
        
        return FormatResponseResponse(formatted_response=formatted_text)
        
    except Exception as e:
        logger.error(f"AI formatting failed: {e}")
        # Return a basic fallback response
        return FormatResponseResponse(
            formatted_response=f"I found {len(request.suggestions)} relevant sources for your query. "
                              "The data is available for review and can be saved to your knowledge base."
        )


@router.post("/claude-chat")
async def claude_discovery_chat_stream(
    request: Request,
    user=Depends(current_active_user),
    db_session=Depends(get_async_session)
):
    """
    Claude-powered discovery chat endpoint with streaming support.
    Uses Claude's native tool use capabilities for more intelligent discovery.
    """
    try:
        # Parse the request body
        body = await request.json()
        messages = body.get("messages", [])
        data = body.get("data", {})
        
        # Debug: Log request data to understand what the frontend sends
        logger.info(f"🔍 [CLAUDE-CHAT] Request data keys: {list(data.keys())}")
        logger.info(f"🔍 [CLAUDE-CHAT] Messages count: {len(messages)}")  
        logger.info(f"🔍 [CLAUDE-CHAT] Data content: {data}")
        logger.info(f"🚨 DEBUG: THIS IS UPDATED CODE - ENHANCED FOLLOW-UP DETECTION ACTIVE")
        
        # Get the latest user message
        if not messages:
            raise HTTPException(status_code=400, detail="No messages provided")
        
        latest_message = messages[-1]
        if latest_message["role"] != "user":
            raise HTTPException(status_code=400, detail="Latest message must be from user")
        
        query = latest_message["content"]
        search_space_id = int(data.get("search_space_id")) if data.get("search_space_id") else None
        
        if not search_space_id:
            raise HTTPException(status_code=400, detail="search_space_id is required")
        
        # Enhanced follow-up detection - check multiple indicators
        conversation_id = data.get("conversation_id") or data.get("conversationId") or data.get("chatId")
        is_follow_up_by_id = conversation_id is not None
        is_follow_up_by_history = len(messages) > 1
        
        # Additional checks for follow-up detection
        assistant_messages = [msg for msg in messages if msg.get("role") == "assistant"]
        is_follow_up_by_assistant_presence = len(assistant_messages) > 0
        
        # Check for recent conversations by same user (within last 10 minutes)
        from datetime import datetime, timedelta
        recent_time = datetime.utcnow() - timedelta(minutes=10)
        recent_chats = await db_session.execute(
            select(Chat)
            .join(SearchSpace)
            .where(
                SearchSpace.user_id == user.id,
                Chat.search_space_id == search_space_id,
                Chat.type == ChatType.DISCOVERY,
                Chat.created_at > recent_time
            ).order_by(Chat.created_at.desc()).limit(1)
        )
        recent_chat = recent_chats.scalars().first()
        is_follow_up_by_timing = recent_chat is not None
        
        logger.info(f"🔍 [CLAUDE-CHAT] Follow-up indicators:")
        logger.info(f"  - conversation_id present: {is_follow_up_by_id} (value: {conversation_id})")
        logger.info(f"  - message history > 1: {is_follow_up_by_history} ({len(messages)} messages)")
        logger.info(f"  - has assistant messages: {is_follow_up_by_assistant_presence} ({len(assistant_messages)} assistant msgs)")
        logger.info(f"  - recent chat exists: {is_follow_up_by_timing} (recent chat: {recent_chat.id if recent_chat else None})")
        
        is_follow_up = is_follow_up_by_id or is_follow_up_by_history or is_follow_up_by_assistant_presence or is_follow_up_by_timing
        
        # Process conversation history
        conversation_history = messages[:-1]
        
        logger.info(f"🤖 Starting Claude discovery for user {user.id}: {query}")
        if conversation_history:
            logger.info(f"💭 Conversation history: {len(conversation_history)} previous messages")
        
        async def claude_event_generator():
            try:
                # Get user's API tokens
                from .toolrow_settings_routes import get_user_toolrow_token
                toolrow_api_token = await get_user_toolrow_token(str(user.id), db_session)
                anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
                
                # Initialize Claude Discovery Agent
                agent = await create_claude_discovery_agent(
                    db_session=db_session,
                    user_id=str(user.id),
                    toolrow_api_token=toolrow_api_token,
                    anthropic_api_key=anthropic_api_key
                )
                
                # Convert conversation history to expected format
                chat_history = []
                for msg in conversation_history:
                    if msg["role"] == "user":
                        chat_history.append(HumanMessage(content=msg["content"]))
                    elif msg["role"] == "assistant":
                        chat_history.append(AIMessage(content=msg["content"]))
                
                # Extract conversation session ID if available
                conversation_id = data.get("conversation_id")
                if conversation_id:
                    session_id = str(conversation_id)
                else:
                    session_id = None
                
                # Stream Claude's discovery response
                full_response = ""
                async for chunk in agent.discover_sources(query, session_id=session_id, chat_history=chat_history):
                    if chunk.strip():
                        full_response += chunk
                        # Send each chunk as streaming content
                        yield f"0:{json.dumps(chunk)}\n"
                
                # Send follow-up questions if available
                follow_up_questions = agent.get_follow_up_questions()
                if follow_up_questions:
                    streaming_service = StreamingService()
                    yield streaming_service.format_further_questions_delta(follow_up_questions)
                
                # Send completion data
                completion_data = {
                    "finishReason": "stop",
                    "usage": {"promptTokens": 0, "completionTokens": 0, "totalTokens": 0},
                    "data": {
                        "claude_powered": True,
                        "tool_count": len(agent.available_tools),
                        "response_length": len(full_response)
                    }
                }
                yield f"d:{json.dumps(completion_data)}\n"
                
                # Use the enhanced follow-up detection from above
                if not is_follow_up:
                    chat_id = await save_discovery_chat(
                        user_query=query,
                        assistant_response=full_response,
                        search_space_id=search_space_id,
                        selected_tools=["claude_discovery"],
                        discovery_data=completion_data['data'],
                        user=user,
                        session=db_session
                    )
                    logger.info(f"💾 New discovery conversation saved as chat {chat_id}")
                else:
                    logger.info(f"🔄 Follow-up detected - not creating new chat:")
                    logger.info(f"  - by conversation_id: {is_follow_up_by_id}")
                    logger.info(f"  - by message history: {is_follow_up_by_history}")
                    logger.info(f"  - by assistant presence: {is_follow_up_by_assistant_presence}")
                
                logger.info(f"✅ Claude discovery completed for user {user.id}")
                
            except Exception as e:
                logger.error(f"❌ Claude discovery failed: {e}")
                error_msg = f"Claude discovery error: {str(e)}"
                yield f"0:{json.dumps(error_msg)}\n"
                
            finally:
                # Cleanup
                if 'agent' in locals():
                    await agent.cleanup()
        
        response = StreamingResponse(
            claude_event_generator(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "x-vercel-ai-data-stream": "v1"
            }
        )
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Claude discovery endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Claude discovery failed: {str(e)}")


@router.post("/chat")
async def discovery_chat_stream(
    request: Request,
    user=Depends(current_active_user),
    db_session=Depends(get_async_session)
):
    """
    Streaming chat endpoint for discovery, compatible with @ai-sdk/react useChat.
    This mimics the researcher agent's streaming approach.
    """
    try:
        # Parse the request body
        body = await request.json()
        messages = body.get("messages", [])
        data = body.get("data", {})
        
        # Debug: Log all requests to /chat endpoint
        logger.info(f"🔍 [CHAT-ENDPOINT] Request data keys: {list(data.keys())}")
        logger.info(f"🔍 [CHAT-ENDPOINT] Messages count: {len(messages)}")
        logger.info(f"🔍 [CHAT-ENDPOINT] Data content: {data}")
        logger.info(f"🚨 DEBUG: /CHAT ENDPOINT REQUEST - ENHANCED FOLLOW-UP DETECTION ACTIVE")
        
        # Get the latest user message
        if not messages:
            raise HTTPException(status_code=400, detail="No messages provided")
        
        latest_message = messages[-1]
        if latest_message["role"] != "user":
            raise HTTPException(status_code=400, detail="Latest message must be from user")
        
        query = latest_message["content"]
        search_space_id = int(data.get("search_space_id")) if data.get("search_space_id") else None
        selected_tools = data.get("selected_tools", [])
        discovery_mode = data.get("discovery_mode", "BASIC")  # Get discovery mode from frontend
        max_sources = data.get("max_sources", 20)
        
        if not search_space_id:
            raise HTTPException(status_code=400, detail="search_space_id is required")
        
        # Process conversation history for memory checks (keep raw messages)
        conversation_history = messages[:-1]  # All except current message, keep original format
        
        logger.info(f"🔍 Starting streaming discovery for user {user.id}: {query}")
        logger.info(f"🎯 Discovery Mode: {discovery_mode} | Tools: {selected_tools or 'AI Selection'}")
        if conversation_history:
            logger.info(f"💭 Conversation history: {len(conversation_history)} previous messages")
        
        async def event_generator():
            mcp_manager = None
            try:
                # Get user's ToolRow token from database
                from .toolrow_settings_routes import get_user_toolrow_token
                toolrow_api_token = await get_user_toolrow_token(str(user.id), db_session)
                
                # Initialize the new mcp-use discovery agent with token
                agent = await create_discovery_agent(db_session, str(user.id), toolrow_api_token)
                
                # Create a streaming service for the new agent
                terminal_idx = 1
                
                def stream_terminal_event(event_type, message, details=None):
                    nonlocal terminal_idx
                    event_data = {
                        "id": terminal_idx,
                        "text": message,
                        "type": event_type,
                        "timestamp": int(time.time() * 1000),
                        "details": details
                    }
                    terminal_idx += 1
                    annotation = {"type": "TERMINAL_INFO", "data": event_data}
                    return f"8:[{json.dumps(annotation)}]\n"
                
                # Stream discovery using the new mcp-use agent with enhanced logging
                yield stream_terminal_event("info", "🚀 Initializing enhanced discovery agent with verbose MCP logging...")
                
                full_response = ""
                final_response_parts = []
                step_counter = 1
                
                # Convert messages to format expected by the agent
                chat_history = []
                for msg in messages[:-1]:  # Exclude the latest message as it's the current query
                    if msg["role"] == "user":
                        chat_history.append(HumanMessage(content=msg["content"]))
                    elif msg["role"] == "assistant":
                        chat_history.append(AIMessage(content=msg["content"]))
                
                logger.info(f"🔗 Passing {len(chat_history)} previous messages to discovery agent")
                
                # Extract conversation session ID for Claude discovery agent
                conversation_id = data.get("conversation_id")
                session_id = str(conversation_id) if conversation_id else None
                
                # Separate terminal events from final content
                terminal_content = ""
                final_content_started = False
                
                async for chunk in agent.discover_sources(query, session_id=session_id, chat_history=chat_history):
                    if chunk.strip():
                        chunk_lower = chunk.lower()
                        
                        # Check if this is final formatted content (structured response patterns)
                        is_final_content = (
                            chunk.startswith("# ") or  # Main title heading 
                            chunk.startswith("## ") or  # Section headings
                            chunk.startswith("### ") or  # Subsection headings
                            "Summary" in chunk or
                            "Key Categories" in chunk or
                            "Context & Reliability" in chunk or
                            "Next Steps" in chunk or
                            chunk.startswith("- **") or  # Structured list items
                            chunk.startswith("**") or  # Bold text sections
                            final_content_started
                        )
                        if is_final_content:
                            final_content_started = True
                            full_response += chunk
                            final_response_parts.append(chunk)
                            continue
                        
                        # This is terminal content - only send to terminal, not final response
                        terminal_content += chunk
                        
                        # Enhanced terminal events with better categorization
                        if any(indicator in chunk_lower for indicator in ["🚀", "initializing", "starting"]):
                            yield stream_terminal_event("info", f"Step {step_counter}: {chunk.strip()}")
                            step_counter += 1
                        elif any(indicator in chunk_lower for indicator in ["✅", "complete", "found", "success"]):
                            yield stream_terminal_event("success", chunk.strip())
                        elif any(indicator in chunk_lower for indicator in ["🧠", "analyzing", "🤖", "agent", "tool"]):
                            yield stream_terminal_event("info", chunk.strip())
                        elif any(indicator in chunk_lower for indicator in ["📡", "execution", "mcp", "verbose"]):
                            yield stream_terminal_event("progress", chunk.strip())
                        elif any(indicator in chunk_lower for indicator in ["⚠️", "warning", "limited"]):
                            yield stream_terminal_event("warning", chunk.strip())
                        elif any(indicator in chunk_lower for indicator in ["❌", "error", "failed"]):
                            yield stream_terminal_event("error", chunk.strip())
                        elif len(chunk.strip()) > 20:  # Substantial content
                            # Show content without "Processing:" prefix and better truncation
                            clean_chunk = chunk.strip()
                            if len(clean_chunk) > 100:
                                yield stream_terminal_event("progress", f"{clean_chunk[:100]}...")
                            else:
                                yield stream_terminal_event("progress", clean_chunk)
                
                # Create a mock result for compatibility
                class MockResult:
                    def __init__(self):
                        self.total_found = 0
                        self.processing_time_ms = 1000
                        self.suggestions = []
                        self.terminal_events = []
                        self.reasoning_steps = []
                
                result = MockResult()
                
                # Parse response for any structured data
                if "found" in full_response.lower():
                    import re
                    numbers = re.findall(r'\d+', full_response)
                    if numbers:
                        result.total_found = int(numbers[0])
                
                yield stream_terminal_event("success", f"✅ Discovery completed: {result.total_found} sources found")
                
                # Send terminal auto-collapse annotation
                collapse_annotation = {
                    "type": "TERMINAL_COLLAPSE", 
                    "data": {"auto_collapse": True}
                }
                yield f"8:[{json.dumps(collapse_annotation)}]\n"
                
                # Use the full response from the agent as the final content
                # If separation didn't work (no structured content detected), use a meaningful fallback
                if not full_response.strip():
                    final_content = f"I searched for '{query}' using {len(available_tools) if 'available_tools' in locals() else 'multiple'} research tools. Please check the Discovery Process Terminal above for detailed execution steps."
                else:
                    final_content = full_response.strip()
                
                # Ensure final_content is always a string and not empty
                if not isinstance(final_content, str):
                    final_content = str(final_content)
                
                if not final_content or final_content.strip() == "":
                    final_content = f"I found {result.total_found if result else 0} sources for your query: {query}"
                
                # Debug logging
                logger.info(f"🔍 Final content length: {len(final_content)}")
                logger.info(f"🔍 Final content preview: {final_content[:200]}...")
                
                
                # Send final content as text chunk (same as researcher agent)
                logger.info(f"🔍 Sending text chunk: {final_content[:100]}...")
                yield f"0:{json.dumps(final_content)}\n"
                
                # Send follow-up questions using StreamingService (same as researcher agent)
                follow_up_questions = agent.get_follow_up_questions()
                if follow_up_questions:
                    logger.info(f"🤔 Sending {len(follow_up_questions)} follow-up questions")
                    streaming_service = StreamingService()
                    yield streaming_service.format_further_questions_delta(follow_up_questions)
                
                # Send completion data with all the discovery metadata
                completion_data = {
                    "finishReason": "stop",
                    "usage": {"promptTokens": 0, "completionTokens": 0, "totalTokens": 0},
                    "data": {
                        "terminal_events": result.terminal_events if result else [],
                        "suggestions": [s.dict() for s in result.suggestions] if result and result.suggestions else [],
                        "reasoning_steps": result.reasoning_steps if result and result.reasoning_steps else [],
                        "total_found": int(result.total_found) if result else 0,
                        "processing_time_ms": int(result.processing_time_ms) if result else 0
                    }
                }
                yield f"d:{json.dumps(completion_data)}\n"
                
                logger.info(f"🚀 Final content sent as text chunk: {len(final_content)} chars, {len(completion_data['data']['suggestions'])} suggestions")
                
                # Save discovery conversation to chat history 
                # Only if no conversation_id provided (new conversation)
                disable_auto_save = data.get("disable_auto_save", False)
                
                # Use enhanced follow-up detection for /chat endpoint too
                chat_has_assistant = len([m for m in messages if m.get("role") == "assistant"]) > 0
                
                # Check for recent conversations by same user (within last 10 minutes)
                from datetime import datetime, timedelta
                recent_time = datetime.utcnow() - timedelta(minutes=10)
                recent_chats = await db_session.execute(
                    select(Chat)
                    .join(SearchSpace)
                    .where(
                        SearchSpace.user_id == user.id,
                        Chat.search_space_id == search_space_id,
                        Chat.type == ChatType.DISCOVERY,
                        Chat.created_at > recent_time
                    ).order_by(Chat.created_at.desc()).limit(1)
                )
                recent_chat = recent_chats.scalars().first()
                
                chat_is_follow_up = conversation_id is not None or len(messages) > 1 or chat_has_assistant or recent_chat is not None
                
                logger.info(f"🔍 [CHAT] Follow-up detection:")
                logger.info(f"  - conversation_id present: {conversation_id is not None} (value: {conversation_id})")
                logger.info(f"  - message history > 1: {len(messages) > 1} ({len(messages)} messages)")
                logger.info(f"  - has assistant messages: {chat_has_assistant}")
                logger.info(f"  - recent chat exists: {recent_chat is not None} (recent chat: {recent_chat.id if recent_chat else None})")
                logger.info(f"  - is_follow_up result: {chat_is_follow_up}")
                
                if not disable_auto_save and not chat_is_follow_up:
                    try:
                        chat_id = await save_discovery_chat(
                            user_query=query,
                            assistant_response=final_content,
                            search_space_id=search_space_id,
                            selected_tools=selected_tools,
                            discovery_data=completion_data['data'],
                            user=user,
                            session=db_session
                        )
                        if chat_id:
                            logger.info(f"💾 New discovery conversation saved as chat {chat_id}")
                    except Exception as e:
                        logger.error(f"❌ Failed to save discovery chat: {e}")
                else:
                    logger.info(f"🔄 [CHAT] Follow-up detected - not creating new chat")
                
                logger.info(f"✅ Streaming discovery completed for user {user.id}")
                
            except Exception as e:
                logger.error(f"❌ Streaming discovery failed: {e}")
                error_response = {
                    "role": "assistant", 
                    "content": f"Sorry, I encountered an error during discovery: {str(e)}"
                }
                yield f"0:{json.dumps(error_response)}\n"
            finally:
                # No cleanup needed for ToolrowMCPManager
                pass
        
        response = StreamingResponse(
            event_generator(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
        
        # Add the header that researcher agent uses for AI SDK compatibility
        response.headers["x-vercel-ai-data-stream"] = "v1"
        return response
        
    except Exception as e:
        logger.error(f"❌ Discovery chat endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Discovery chat failed: {str(e)}")
