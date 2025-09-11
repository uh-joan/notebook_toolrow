# Reasoning Source Discovery Agent

A sophisticated reasoning system that transforms the Source Discovery Agent into an intelligent research assistant capable of query expansion, result refinement, and adaptive tool chaining.

## 🧠 Overview

The reasoning system implements a **plan-act-observe-reflect** loop that:

- **Analyzes queries** to determine optimal search strategies
- **Recovers from zero hits** using expansion playbooks  
- **Refines overbroad results** using intelligent filtering
- **Chains tools** for complex multi-step research workflows
- **Provides comprehensive tracing** of all reasoning steps
- **Outputs strict JSON** with evidence and limitations

## 🏗️ Architecture

```
reasoning/
├── models.py          # Pydantic models (FinalResponse, TraceEvent, etc.)
├── config.py          # Configuration and thresholds
├── orchestrator.py    # Core reasoning engine
├── adapters.py        # Tool adapters with timeout handling
├── playbooks.py       # Query expansion/refinement strategies
├── rankers.py         # Result ranking and selection
├── utils.py           # Helper functions
└── logging.py         # Structured logging and metrics
```

## 🚀 Quick Start

### Enable Reasoning Mode

Set the environment variable to enable reasoning:

**Reasoning is enabled by default** for optimal user experience.

To disable reasoning (not recommended):
```bash
export REASONING_ENABLED=false
```

Or programmatically:

```python
from surfsense_backend.app.agents.source_discovery.agent import create_discovery_agent

agent = await create_discovery_agent(
    db_session=session,
    user_id="user123", 
    reasoning_enabled=True
)

async for chunk in agent.discover_sources("diabetes clinical trials"):
    print(chunk, end='', flush=True)
```

### Configuration

Configure via environment variables:

```bash
export REASONING_MIN_OK=5           # Minimum acceptable results
export REASONING_MAX_OK=500         # Maximum before refinement
export REASONING_MAX_ROUNDS=3       # Max expansion/refinement rounds
export REASONING_QUERY_TIMEOUT=20   # Per-tool timeout (seconds)
export REASONING_PARALLEL_LIMIT=5   # Max parallel tool executions
export REASONING_LOG_LEVEL=INFO     # Logging verbosity
```

## 🎯 Key Features

### 1. Smart Query Analysis

```python
# Automatically classifies queries and determines strategy
query_analysis = QueryAnalysis(
    query_type="trials",           # trials, codes, drugs, literature
    intent="high_precision",       # precision vs recall optimization  
    complexity="moderate",         # simple, moderate, complex
    suggested_tools=["ct_gov_studies", "nlm_ct_codes"]
)
```

### 2. Zero-Hit Recovery

When searches return no results:

- **Code Mapping**: Maps conditions to ICD-10/HCPCS codes
- **Term Suggestions**: Uses ct.gov suggest API for normalization
- **Synonym Expansion**: Adds medical synonyms and related terms
- **Temporal Broadening**: Expands search time windows
- **Cross-Tool Search**: Tries alternative databases

### 3. Overbroad Refinement

When searches return too many results:

- **Phase Filtering**: Focus on Phase 2/3 trials
- **Status Filtering**: Active/recruiting studies only
- **Geographic Filtering**: Location-based constraints
- **Temporal Narrowing**: Recent studies only
- **Precision Search**: Exact phrase matching

### 4. Tool Chaining

Automated multi-step workflows:

- **Drug → Trials**: FDA lookup → related clinical trials
- **Condition → Codes → Trials**: Disease mapping → ICD codes → trials
- **Trials → Literature**: Clinical studies → research publications

### 5. Comprehensive Tracing

Every reasoning step is logged:

```json
{
  "step": "expand",
  "strategy": "code_mapping", 
  "tool": "nlm_ct_codes",
  "input": {"terms": "diabetes"},
  "outcome": {"hits": 5, "codes": ["E11", "E10"]},
  "reason": "Zero hits - expanding with medical codes"
}
```

## 📊 Output Format

The reasoning system returns strict JSON:

```json
{
  "answer": {
    "summary": "Found 18 Phase II/III trials for diabetes treatment",
    "total_sources": 18,
    "search_rounds": 2,
    "strategies_used": ["code_mapping", "phase_refinement"]
  },
  "evidence": [
    {
      "source": "ct_gov_studies",
      "id": "NCT12345",
      "title": "Semaglutide in Type 2 Diabetes",
      "url": "https://clinicaltrials.gov/ct2/show/NCT12345",
      "meta": {"phase": "Phase 3", "status": "recruiting"}
    }
  ],
  "trace": [
    {
      "step": "search",
      "strategy": "initial_search", 
      "tool": "ct_gov_studies",
      "reason": "Primary trials search"
    }
  ],
  "limitations": ["Search limited to last 10 years"],
  "next_best_actions": ["Try broader search terms", "Include Phase 1 trials"],
  "query_analysis": { /* analysis details */ },
  "total_duration_ms": 2340,
  "success": true
}
```

## 🔧 Configuration Options

### ReasoningConfig

```python
config = ReasoningConfig(
    min_ok=5,                    # Minimum results threshold
    max_ok=500,                  # Maximum results threshold  
    max_rounds=3,                # Max expansion/refinement rounds
    per_query_timeout_s=20,      # Individual tool timeout
    total_timeout_s=120,         # Total session timeout
    parallel_limit=5,            # Max parallel executions
    enable_caching=True,         # Enable result caching
    enable_parallel_execution=True,  # Enable parallel tools
    enable_query_expansion=True,     # Enable expansion strategies
    enable_result_refinement=True,   # Enable refinement strategies
    ranking_weights={
        "authority": 0.5,        # Tool reliability weight
        "recency": 0.3,          # Temporal relevance weight
        "yield": 0.2             # Result quantity weight
    }
)
```

## 📈 Performance & Monitoring

### Structured Logging

All operations are logged in JSON format:

```python
from surfsense_backend.app.agents.source_discovery.reasoning import configure_reasoning_logging

configure_reasoning_logging(level="INFO", format_json=True)
```

### Metrics Collection

Performance metrics are automatically collected:

- `zero_hit_recoveries_count`
- `overbroad_refinements_count` 
- `avg_rounds_to_success`
- `timeout_failures_count`
- `tool_execution_count`

### Trace Correlation

All logs include a trace ID for request correlation:

```json
{
  "event_type": "reasoning_session_start",
  "trace_id": "abc123ef", 
  "user_id": "user123",
  "query": "diabetes trials"
}
```

## 🧪 Testing

Comprehensive test suite covering:

- **Zero-hit recovery** scenarios
- **Overbroad refinement** scenarios  
- **Tool chaining** workflows
- **JSON schema validation**
- **Integration testing**

Run tests:

```bash
cd tests/reasoning
python run_tests.py                    # All tests
python run_tests.py zero_hit_recovery  # Specific suite
```

## 🔄 Fallback Behavior

The reasoning system includes robust fallback mechanisms:

1. **Initialization Failure**: Falls back to simple search mode
2. **Tool Timeouts**: Continues with available tools
3. **Expansion Failures**: Returns partial results with limitations
4. **Configuration Errors**: Uses sensible defaults

## 🎛️ Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REASONING_ENABLED` | `true` | Enable reasoning mode |
| `REASONING_MIN_OK` | `5` | Minimum acceptable results |
| `REASONING_MAX_OK` | `500` | Maximum before refinement |
| `REASONING_MAX_ROUNDS` | `3` | Max expansion rounds |
| `REASONING_QUERY_TIMEOUT` | `20` | Tool timeout (seconds) |
| `REASONING_TOTAL_TIMEOUT` | `120` | Session timeout (seconds) |
| `REASONING_PARALLEL_LIMIT` | `5` | Max parallel tools |
| `REASONING_LOG_LEVEL` | `INFO` | Logging level |
| `REASONING_ENABLE_CACHING` | `true` | Enable result caching |
| `REASONING_EMIT_METRICS` | `true` | Emit performance metrics |

## 🚨 Error Handling

The system handles errors gracefully:

- **Tool failures**: Continue with remaining tools
- **Timeouts**: Return partial results  
- **Network errors**: Retry with backoff
- **Invalid responses**: Log and continue
- **Configuration errors**: Use defaults

## 🔮 Future Enhancements

Planned improvements:

- **Machine Learning**: Learn from user feedback to improve ranking
- **Advanced Caching**: Semantic similarity-based cache matching
- **Custom Playbooks**: User-defined expansion strategies
- **Real-time Adaptation**: Dynamic threshold adjustment
- **Multi-language Support**: International medical terminology

---

**The reasoning system transforms simple keyword searches into intelligent research workflows, providing users with comprehensive, well-sourced answers backed by transparent reasoning traces.**
