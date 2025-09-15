# SourceBook Claude Discovery Agent - Product Requirements Document

**Version**: 1.0  
**Date**: September 11, 2025  
**Author**: Product Team  
**Status**: Approved for Development

---

## 🎯 Executive Summary

Replace the current discovery agent with a native Claude-powered solution leveraging Claude's advanced tool use capabilities, streaming responses, and built-in intelligence. This implementation will eliminate complex custom reasoning systems in favor of Claude's native strengths.

## 📋 Project Context

### Current State
- Custom discovery agent with complex reasoning orchestrator
- Multiple layers of tool adapters and strategy playbooks
- Heavy dependency on LangChain and custom MCP implementations
- ~3,000+ lines of custom reasoning code requiring maintenance

### Proposed Solution
- Native Claude tool use with Anthropic's Messages API
- Direct integration of Toolrow MCP tools as Claude tools
- Simplified architecture using Claude's built-in reasoning
- Streaming responses with real-time user feedback

## 🔧 Technical Architecture

### Core Components

#### 1. Claude Tool Integration
**Based on**: Tool use with Claude documentation

```python
# Native Claude tool definition
tools = [
    {
        "name": "ct_gov_studies",
        "description": "Search clinical trials from ClinicalTrials.gov. Use this for finding ongoing studies, trial statuses, recruitment information, and research protocols. Supports complex queries including condition names, intervention types, study phases, and geographic locations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query (e.g., 'diabetes trials recruiting in California')"
                },
                "pageSize": {
                    "type": "integer",
                    "description": "Number of results to return (1-100, default: 10)"
                },
                "status": {
                    "type": "string",
                    "enum": ["recruiting", "active", "completed", "any"],
                    "description": "Study recruitment status filter"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "nlm_ct_codes",
        "description": "Search medical coding systems including ICD-10-CM diagnosis codes, HCPCS procedure codes, MeSH terms, and clinical vocabularies. Essential for medical research, billing codes, and standardized medical terminology.",
        "input_schema": {
            "type": "object", 
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["icd-10-cm", "hcpcs", "mesh", "npi"],
                    "description": "Coding system to search"
                },
                "terms": {
                    "type": "string",
                    "description": "Search terms for medical codes"
                }
            },
            "required": ["method", "terms"]
        }
    }
    // ... Additional tools for FDA, PubMed, SEC, WHO
]
```

#### 2. Streaming Implementation
**Based on**: Fine-grained tool streaming documentation

```python
# Stream Claude responses with tool use
async def stream_discovery_response(query: str, tools: List[Dict]):
    async with anthropic.beta.messages.stream(
        model="claude-opus-4-1-20250805",
        max_tokens=4096,
        tools=tools,
        messages=[{"role": "user", "content": query}],
        betas=["fine-grained-tool-streaming-2025-05-14"]
    ) as stream:
        async for event in stream:
            if event.type == "content_block_delta":
                # Stream thinking and tool planning to user
                yield format_stream_event(event)
            elif event.type == "tool_use":
                # Execute tool and stream results
                yield await execute_tool_and_stream(event)
```

#### 3. Tool Execution Layer
**Based on**: How to implement tool use documentation

```python
class ClaudeToolExecutor:
    def __init__(self, toolrow_token: str):
        self.toolrow_token = toolrow_token
        self.tool_handlers = self._register_tool_handlers()
    
    async def execute_tool(self, tool_use: ToolUse) -> ToolResult:
        """Execute Claude's tool request and return formatted result"""
        handler = self.tool_handlers.get(tool_use.name)
        if not handler:
            return ToolResult(
                tool_use_id=tool_use.id,
                content="Tool not available",
                is_error=True
            )
        
        try:
            result = await handler.execute(tool_use.input)
            return ToolResult(
                tool_use_id=tool_use.id,
                content=self._format_tool_result(result, tool_use.name)
            )
        except Exception as e:
            return ToolResult(
                tool_use_id=tool_use.id,
                content=f"Tool execution error: {str(e)}",
                is_error=True
            )
```

#### 4. Advanced Features

**Parallel Tool Use**: Leverage Claude's native parallel tool capabilities
```python
# Claude automatically determines when to use multiple tools in parallel
tools_response = await client.messages.create(
    model="claude-opus-4-1-20250805",
    tools=all_available_tools,
    messages=[{
        "role": "user",
        "content": "Find ICD-10 codes for diabetes AND search for related clinical trials AND get FDA drug information"
    }]
)
# Claude may return multiple tool_use blocks simultaneously
```

**Tool Choice Control**: Force specific tool usage when needed
```python
# Force Claude to use a specific tool
response = await client.messages.create(
    model="claude-opus-4-1-20250805",
    tools=tools,
    tool_choice={"type": "tool", "name": "ct_gov_studies"},
    messages=[{"role": "user", "content": query}]
)
```

**JSON Mode for Structured Output**: Use tools for consistent response formatting
```python
format_tool = {
    "name": "format_discovery_response", 
    "description": "Format discovery results with citations and structured data",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "object"}},
            "follow_up_questions": {"type": "array", "items": {"type": "string"}}
        }
    }
}
```

## 🚀 Implementation Plan

### Phase 1: Core Claude Integration (Week 1-2)
**Priority**: P0

**Deliverables**:
- [ ] Claude API client setup with proper authentication
- [ ] Basic tool definition mapping from current MCP tools
- [ ] Simple query → Claude → tool execution → response flow
- [ ] Error handling and fallback mechanisms

**Success Criteria**:
- Single tool execution works end-to-end
- Streaming responses display in terminal
- Error states handled gracefully

### Phase 2: Multi-Tool Orchestration (Week 3)
**Priority**: P0

**Deliverables**:
- [ ] Parallel tool use implementation
- [ ] Tool chaining for complex queries
- [ ] Response formatting and citation generation
- [ ] Memory/conversation history integration

**Success Criteria**:
- Complex queries like "diabetes trials and codes" work automatically
- Citations and structured responses generated
- Follow-up questions maintain context

### Phase 3: Advanced Features (Week 4)
**Priority**: P1

**Deliverables**:
- [ ] Token-efficient tool use integration
- [ ] Fine-grained streaming optimization
- [ ] Advanced prompting for discovery tasks
- [ ] Performance monitoring and optimization

**Success Criteria**:
- Reduced token usage and improved latency
- High-quality discovery responses
- Performance metrics within target thresholds

### Phase 4: UI Integration & Polish (Week 5)
**Priority**: P1

**Deliverables**:
- [ ] Frontend integration with new Claude agent
- [ ] Streaming terminal updates
- [ ] Save to documents functionality
- [ ] Testing and quality assurance

**Success Criteria**:
- Seamless UI experience matching current discovery agent
- All existing features preserved
- User feedback indicates improved performance

## 📊 Technical Specifications

### Architecture Principles

1. **Claude-Native**: Leverage Claude's built-in reasoning rather than custom logic
2. **Streaming-First**: Real-time user feedback throughout discovery process
3. **Tool-Centric**: Each data source is a well-defined Claude tool
4. **Minimal Custom Code**: Reduce maintenance burden by using Claude capabilities

### API Integration

**Model Selection**:
- **Primary**: `claude-opus-4-1-20250805` for complex multi-tool scenarios
- **Secondary**: `claude-sonnet-4-20250514` for performance-critical queries
- **Fallback**: `claude-3-7-sonnet-20250219` with token-efficient tools

**Required Beta Headers**:
```
anthropic-beta: fine-grained-tool-streaming-2025-05-14
```

**Tool Configuration**:
```python
class ClaudeDiscoveryConfig:
    max_tokens: int = 4096
    temperature: float = 0.1
    top_p: float = 0.9
    tools: List[ToolDefinition] = field(default_factory=lambda: [
        # Clinical Trials
        get_ct_gov_tool_definition(),
        # Medical Codes  
        get_nlm_codes_tool_definition(),
        # FDA Information
        get_fda_tool_definition(),
        # PubMed Literature
        get_pubmed_tool_definition(),
        # WHO Health Data
        get_who_tool_definition(),
        # SEC Financial Data
        get_sec_tool_definition(),
        # Response Formatting
        get_format_tool_definition()
    ])
```

### Prompt Engineering

**System Prompt Template**:
```
You are SourceBook Discover, an expert research assistant specializing in finding and analyzing information from authoritative sources including clinical trials, medical codes, FDA databases, PubMed literature, and regulatory filings.

When a user asks for information:
1. Analyze their query to determine the most relevant data sources
2. Use available tools to gather comprehensive information 
3. Present findings with proper citations and source attribution
4. Suggest meaningful follow-up questions for deeper exploration

For complex queries requiring multiple data sources, use parallel tool calls to gather information efficiently. Always provide source URLs and metadata when available.

Available research databases:
- Clinical Trials (ClinicalTrials.gov)
- Medical Codes (ICD-10-CM, MeSH, HCPCS) 
- FDA Drug/Device Information
- PubMed Scientific Literature
- WHO Health Statistics
- SEC Financial Filings

Guidelines:
- Prioritize authoritative, primary sources
- Include publication dates and study phases for clinical research
- Provide direct links to source materials
- Format responses for easy scanning and reference
- Generate relevant follow-up questions to guide further research
```

**User Query Processing**:
```python
def enhance_user_query(query: str, conversation_history: List[Message]) -> str:
    """Enhance user query with context and search strategy guidance"""
    context = extract_conversation_context(conversation_history)
    
    enhanced_prompt = f"""
    Query: {query}
    
    Context from previous conversation: {context}
    
    Please search for comprehensive information using the most appropriate tools. 
    Use parallel searches when information spans multiple databases.
    Provide detailed citations and suggest related areas for exploration.
    """
    
    return enhanced_prompt
```

### Tool Definitions

**Medical Research Tools**:
- `ct_gov_studies`: Clinical trials search and filtering
- `nlm_ct_codes`: Medical coding systems (ICD-10, MeSH, HCPCS)
- `pubmed_articles`: Scientific literature search
- `fda_drug_info`: FDA drug and device information

**Regulatory & Financial Tools**:
- `sec_filings`: SEC financial document search
- `who_health_data`: WHO global health statistics

**Utility Tools**:
- `format_response`: Structure final output with citations
- `generate_follow_ups`: Create contextual next questions

### Response Format Specification

**Structured Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "description": "Clear, descriptive title for the search results"
    },
    "summary": {
      "type": "string", 
      "description": "Executive summary of key findings"
    },
    "sources": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "title": {"type": "string"},
          "source_type": {"type": "string"},
          "url": {"type": "string"},
          "metadata": {"type": "object"}
        }
      }
    },
    "key_findings": {
      "type": "array",
      "items": {"type": "string"}
    },
    "follow_up_questions": {
      "type": "array", 
      "items": {"type": "string"}
    },
    "search_strategy": {
      "type": "string",
      "description": "Explanation of search approach used"
    }
  }
}
```

## 🎛️ Configuration & Environment

### Required Environment Variables
```bash
# Claude API
ANTHROPIC_API_KEY=your_api_key_here

# Toolrow Integration  
TOOLROW_API_TOKEN=your_toolrow_token_here

# Feature Flags
CLAUDE_DISCOVERY_ENABLED=true
FINE_GRAINED_STREAMING=true
TOKEN_EFFICIENT_TOOLS=true

# Performance Tuning
CLAUDE_MAX_TOKENS=4096
CLAUDE_TEMPERATURE=0.1
CLAUDE_TIMEOUT_SECONDS=120
```

### Tool Configuration
```json
{
  "toolrow_mcp_tools": {
    "ct_gov_studies": {
      "timeout": 30,
      "max_retries": 2,
      "description_enhancement": "Include specific examples of query types and expected result formats"
    },
    "nlm_ct_codes": {
      "timeout": 20,
      "max_retries": 2, 
      "supported_methods": ["icd-10-cm", "hcpcs", "mesh", "npi"]
    }
  }
}
```

## 🔍 Quality Assurance

### Testing Strategy

**Unit Tests**:
- Tool definition validation
- Error handling scenarios
- Response formatting accuracy

**Integration Tests**:
- End-to-end query workflows
- Multi-tool orchestration
- Streaming response integrity

**Performance Tests**:
- Latency benchmarks vs. current agent
- Token usage optimization
- Concurrent request handling

**User Experience Tests**:
- Response quality evaluation
- Citation accuracy verification
- Follow-up question relevance

### Success Metrics

**Performance KPIs**:
- Response latency < 10 seconds for simple queries
- Token usage reduction of 15%+ vs. current implementation
- 95%+ uptime and error handling

**Quality KPIs**:
- User satisfaction score > 4.5/5
- Citation accuracy > 98%
- Follow-up question relevance > 90%

**Technical KPIs**:
- Code complexity reduction > 60%
- Maintenance effort reduction > 50%
- API error rate < 1%

## 🔒 Security & Compliance

### Data Protection
- All queries and responses logged for debugging
- Sensitive information filtering in tool responses
- User data privacy compliance (GDPR, CCPA)

### API Security
- Rate limiting per user and total system
- API key rotation and secure storage
- Request/response size limits

### Tool Safety
- Input validation for all tool parameters
- Output sanitization for XSS prevention
- Timeout controls for tool execution

## 📈 Monitoring & Observability

### Metrics Collection
```python
@dataclass
class ClaudeDiscoveryMetrics:
    query_count: int
    avg_response_time: float
    token_usage: Dict[str, int]
    tool_usage_stats: Dict[str, int]
    error_rates: Dict[str, float]
    user_satisfaction: float
```

### Logging Strategy
```python
logger.info("Claude discovery query", extra={
    "user_id": user.id,
    "query": query[:100],  # Truncated for privacy
    "tools_used": [tool.name for tool in tools_used],
    "response_time_ms": response_time,
    "token_usage": response.usage.to_dict(),
    "success": True
})
```

## 🚧 Migration Strategy

### Phase 1: Parallel Deployment
- Deploy Claude agent alongside existing reasoning agent
- Feature flag to route specific users to Claude implementation
- A/B testing with quality metrics comparison

### Phase 2: Gradual Rollout
- Migrate low-risk queries first (simple, single-tool)
- Monitor performance and user feedback
- Iterative improvement based on real usage

### Phase 3: Full Migration
- Switch all traffic to Claude agent
- Remove legacy reasoning system code
- Archive old implementation for reference

### Rollback Plan
- Immediate rollback capability via feature flag
- Legacy system maintained during migration period
- Automated monitoring to trigger rollback if needed

## 📋 Dependencies & Risks

### External Dependencies
- **Anthropic API**: Core functionality dependent on service availability
- **Toolrow MCP**: Tool execution layer must remain stable
- **Network Connectivity**: Reliable internet for API calls

### Technical Risks
- **API Rate Limits**: Claude API usage limits may constrain scalability
- **Token Costs**: Higher usage could increase operational costs
- **Model Changes**: Anthropic model updates might affect behavior

### Mitigation Strategies
- **Caching**: Implement intelligent response caching
- **Fallback Systems**: Maintain simple discovery agent as backup
- **Cost Monitoring**: Real-time token usage tracking and alerting
- **Performance Testing**: Extensive load testing before deployment

## 🎯 Success Criteria

### Must-Have (P0)
- [ ] Feature parity with current discovery agent
- [ ] Response time ≤ current implementation
- [ ] Zero regression in search result quality
- [ ] Successful integration with existing UI

### Should-Have (P1)  
- [ ] 15%+ improvement in response quality
- [ ] 20%+ reduction in code complexity
- [ ] Streaming responses with real-time feedback
- [ ] Enhanced follow-up question generation

### Could-Have (P2)
- [ ] Token usage optimization
- [ ] Advanced query understanding
- [ ] Multi-language support
- [ ] Voice input compatibility

---

## 🔄 Next Steps

1. **Technical Review**: Architecture validation with engineering team
2. **Resource Allocation**: Assign development team and timeline
3. **Environment Setup**: Claude API access and development environment
4. **Prototype Development**: Build basic proof-of-concept
5. **Stakeholder Approval**: Final sign-off from product and engineering leadership

---

**Document Approval**:
- [ ] Product Manager: ________________
- [ ] Engineering Lead: ________________  
- [ ] Technical Architect: ________________
- [ ] Project Manager: ________________

**Last Updated**: September 11, 2025
