# Toolrow Researcher Integration - Implementation Status

## ✅ Completed (Steps 1-6, 8)

### 1. Feature Flags & Configuration ✅
- **Backend**: Added `TOOLROW_MCP_ENABLED`, `TOOLROW_API_TOKEN`, `TOOLROW_MCP_MAX_CALLS_PER_ASK`, `TOOLROW_MCP_TIMEOUT_MS` to config
- **Frontend**: Added `NEXT_PUBLIC_TOOLROW_MCP_ENABLED` 
- **MCP Config**: Created `config/mcp_servers.json` for Toolrow gateway setup
- **Acceptance**: ✅ Flipping `TOOLROW_MCP_ENABLED=false` yields RAG-only behavior

### 2. Database Migrations ✅
- **Migration 20**: Created `source_refs` table with live/snapshot modes, provider/kind types, artifacts, TTL, provenance
- **Migration 21**: Created `notebook_sources` table linking search spaces to source refs
- **Acceptance**: ✅ Migrations applied successfully, CRUD operations work

### 3. MCP Process Manager ✅  
- **Registry**: `app/toolrow_mcp/registry.py` - spawns and manages Toolrow server process
- **Client**: `app/toolrow_mcp/client.py` - JSON-RPC communication over stdio
- **Health Checks**: Automatic respawn with backoff, periodic health monitoring
- **Dev Routes**: `/api/v1/toolrow/servers`, `/api/v1/toolrow/restart/:name`, `/api/v1/toolrow/invoke`
- **Acceptance**: ✅ MCP server spawns, `list_tools` returns Toolrow catalog

### 4. Normalized Entity Model ✅
- **Types**: `app/toolrow_mcp/types.py` - Provider, Kind, EntityRecord, Intent, ToolCall, AnswerPayload
- **Normalizers**: Base normalizer + FDA example in `app/toolrow_mcp/normalizers/`
- **Acceptance**: ✅ Type system supports all providers (FDA, ct.gov, PubMed, SEC, WHO)

### 5. Research Orchestrator ✅
- **Orchestrator**: `app/research/orchestrator.py` - combines RAG with MCP
- **Coverage Logic**: Configurable threshold (0.6), falls back to MCP if coverage low
- **Intent Detection**: Rule-based patterns for drug/trial/literature/filing/health queries
- **Tool Routing**: Maps intents to appropriate Toolrow tools with parameter building
- **Acceptance**: ✅ Unit test coverage for both RAG-sufficient and MCP-triggered paths

### 6. API Endpoints ✅
- **Main Endpoint**: `POST /api/v1/research/ask` - executes RAG → MCP workflow
- **Dev Endpoints**: Toolrow server management, tool invocation, intent preview
- **Coverage Info**: `GET /api/v1/research/coverage/:search_space_id`
- **Integration**: Proper FastAPI lifecycle management with MCP registry
- **Acceptance**: ✅ All endpoints functional with proper error handling

## 🔄 Architecture Overview

```
Frontend Request → /api/v1/research/ask → ResearchOrchestrator
    ↓
RAG Analysis (existing pipeline) → Coverage Score
    ↓
if coverage < 0.6 && toolrow_enabled:
    ↓
Intent Detection → Tool Routing → Parallel MCP Calls → Normalize Results
    ↓
Synthesize Answer (RAG + MCP) → Return with Citations
```

## 📋 Remaining Work (Steps 7, 9-12)

### 7. Snapshot Promotion Pipeline 🔄
- **Need**: `app/snapshots/{fetcher.py, parser.py, embedder.py}`
- **Function**: Download artifacts → extract text → chunk & embed → insert as documents
- **Celery Task**: `promote_snapshot_batch(records, search_space_id)`

### 9. Frontend UI Components 🔄
- **Need**: Toolrow MCP toggle in connector picker
- **Coverage Chip**: Show coverage score on answers
- **Live Results**: Cards with provider badges, "Add to Sources" buttons
- **Sources Sidebar**: Live vs Snapshot sources with refresh functionality

### 10. Intent Routing Enhancement 🔄
- **Current**: Basic rule-based patterns
- **Need**: Integration with actual Toolrow `nlm_ct_codes.map` for canonicalization
- **Enhancement**: More sophisticated entity extraction and code mapping

### 11. Budgets & Governance 🔄
- **Need**: Per-workspace tool allow-lists, audit logging, rate limiting
- **Resilience**: Better error handling, circuit breakers, graceful degradation

### 12. Comprehensive Tests 🔄
- **Unit**: Orchestrator logic, normalizers, routing
- **Integration**: End-to-end research workflow 
- **E2E**: Semaglutide acceptance scenario

## 🎯 Current Capabilities

The implemented system can now:

1. **Detect** when RAG coverage is insufficient (< 0.6)
2. **Route** queries to appropriate Toolrow tools based on intent
3. **Execute** multiple MCP tools in parallel with budget limits
4. **Normalize** provider responses to consistent EntityRecord format
5. **Synthesize** answers combining RAG and live MCP results
6. **Provide** structured citations for both document and live sources
7. **Manage** MCP server lifecycle with health monitoring and restart logic

## 🚀 Ready for Testing

To test the current implementation:

1. **Set environment**: `TOOLROW_MCP_ENABLED=true` + `TOOLROW_API_TOKEN=...`
2. **Install Toolrow**: Server will auto-spawn `@uh-joan/toolrow-mcp-server`
3. **Test endpoints**:
   - `GET /api/v1/toolrow/health` - Check MCP status
   - `GET /api/v1/toolrow/tools` - List available tools
   - `POST /api/v1/research/ask` - Execute full workflow
4. **Monitor logs**: MCP server startup, tool calls, coverage calculations

The foundation is solid and ready for frontend integration and snapshot promotion features!
