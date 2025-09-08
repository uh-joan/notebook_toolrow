# Toolrow Researcher Discovery

## Backend Entrypoints

### FastAPI Application Structure
- **Main app**: `surfsense_backend/main.py` - Entry point
- **App initialization**: `surfsense_backend/app/app.py` - FastAPI app setup
- **Routes**: `surfsense_backend/app/routes/` - API endpoints
  - `chats_routes.py` - Chat functionality
  - `documents_routes.py` - Document management
  - `search_spaces_routes.py` - Search space management
  - `llm_config_routes.py` - LLM configuration
  - `podcasts_routes.py` - Podcast features
  - `logs_routes.py` - Logging endpoints

### Database & RAG Stack
- **Database**: `surfsense_backend/app/db.py` - SQLAlchemy models with pgvector
- **Retrievers**: `surfsense_backend/app/retriver/`
  - `chunks_hybrid_search.py` - Chunk-level hybrid search
  - `documents_hybrid_search.py` - Document-level hybrid search
- **Embeddings**: Configured via `EMBEDDING_MODEL` in config (mixedbread-ai/mxbai-embed-large-v1)
- **Vector store**: PostgreSQL with pgvector extension

### Research & Agent Architecture
- **Agents**: `surfsense_backend/app/agents/`
  - `researcher/` - Current research agent implementation
    - `graph.py` - LangGraph workflow
    - `nodes.py` - Research nodes
    - `state.py` - State management
    - `qna_agent/` - Q&A specific agent
  - `podcaster/` - Podcast generation agent

### Configuration & Services
- **Config**: `surfsense_backend/app/config/__init__.py` - Main configuration
- **Services**: `surfsense_backend/app/services/`
  - `llm_service.py` - LLM management
  - `docling_service.py` - Document processing
  - `query_service.py` - Query processing
  - `reranker_service.py` - Result reranking

## Frontend Architecture

### Next.js Structure
- **Main app**: `surfsense_web/app/` - Next.js 13+ app router
- **Components**: `surfsense_web/components/`
  - `chat/` - Chat interface components
  - `settings/` - Settings management
  - `sidebar/` - Navigation sidebar

### Research UI
- **Dashboard**: `surfsense_web/app/dashboard/` - Main research interface
  - `[search_space_id]/` - Space-specific views
  - `researcher/` - Research workflow UI
- **Hooks**: `surfsense_web/hooks/` - React hooks for API integration
  - `useChat.ts` - Chat functionality
  - `use-documents.ts` - Document management
  - `use-llm-configs.ts` - LLM configuration

## Current Research Flow
1. User selects documents in research interface
2. Query sent to `/api/v1/chat` endpoint in `chats_routes.py`
3. Request processed by `stream_connector_search_results` function
4. Research agent graph workflow initiated:
   - `reformulate_user_query` → `handle_qna_workflow` (for QNA mode)
   - RAG retrieval using `fetch_relevant_documents` function
   - Hybrid search across chunks and documents using existing retrievers
   - QNA agent processes documents and generates response with citations
5. Streaming response returned to frontend chat interface

## Key Current Implementation Details
- **Main API endpoint**: `POST /api/v1/chat` handles research queries
- **Graph workflow**: Uses LangGraph with conditional routing based on research mode
- **Document retrieval**: `fetch_relevant_documents` in `researcher/nodes.py` 
- **QNA processing**: Separate QNA agent with reranking and answer generation
- **Streaming**: Real-time streaming of research progress and results
- **User selections**: Can include specific document IDs in context

## Integration Points for Toolrow MCP

### Backend
- Need to add MCP process manager alongside existing services
- Research orchestrator should extend current agent architecture
- New database tables for source_refs and notebook_sources
- API endpoints for MCP integration and source management

### Frontend  
- Extend research UI with MCP toggle and live results
- Add source management sidebar
- Coverage indicators and add-to-sources functionality

## Key Files to Modify
- `surfsense_backend/app/routes/chats_routes.py` - Add research/ask endpoint
- `surfsense_backend/app/agents/researcher/` - Extend with MCP integration
- `surfsense_web/app/dashboard/[search_space_id]/researcher/` - UI enhancements
- Database migrations in `surfsense_backend/alembic/versions/`

## Environment Configuration
- Backend: `.env` file already exists with LLM and database config
- Frontend: `.env` file exists with public variables
- Both ready for Toolrow MCP configuration additions
