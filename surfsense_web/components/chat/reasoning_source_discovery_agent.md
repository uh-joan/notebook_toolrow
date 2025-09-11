# Reasoning Upgrade for Source Discovery Agent (Cursor Plan)

> Goal: Turn your existing `SourceDiscoveryAgent` into a **reasoning agent** with deterministic retries, query expansion, tool chaining, and strict JSON outputs—without SequentialThinking or mcp-reasoner.

The plan below is indicative and might difer in some points from the real codebase. When this happens adapt accordingly.

---

## 0) Outcomes & Definition of Done

**The agent must:**

* Recover from empty or sparse results using **query expansion playbooks** (codes, synonyms, broader/narrower scopes, tool `suggest` endpoints).
* Chain tools (**nlm\_ct\_codes → fda\_info → ct\_gov\_studies → pubmed\_articles → sec\_edgar → who\_health**) when needed.
* Decide **parallel vs sequential** execution based on dependency.
* Return **strict JSON** with `answer`, `evidence[]`, `trace[]`, `limitations[]`, `next_best_actions[]`.
* Produce a **structured trace** of all attempts (tool, inputs, hits, decision).
* Include **configurable thresholds** for “too few / too many” and **timeouts**.
* Pass unit tests for: zero-hit recovery, overbroad narrowing, and complex multi-entity chaining.

---

## 1) File/Module Plan (additive; non-breaking)

```
surfsense_backend/app/agents/source_discovery/
  agent.py                          # extend with ReasoningOrchestrator entrypoint
  reasoning/
    __init__.py
    config.py                       # ReasoningConfig, thresholds, timeouts
    models.py                       # Pydantic: FinalResponse, TraceEvent, EvidenceItem, ToolQuery, ToolResult
    orchestrator.py                 # plan–act–observe–reflect loop
    playbooks.py                    # expansion & refinement strategies
    rankers.py                      # heuristic ranking of candidate queries/results
    adapters.py                     # thin wrappers around MCP tools (ct_gov_studies, fda_info, etc.)
    utils.py                        # guards: is_zero, too_few, too_many, dedupe, time-window helpers
    logging.py                      # structured logger (json), event factory
tests/
  test_reasoning_zero_hit.py
  test_reasoning_overbroad.py
  test_reasoning_chaining.py
  test_reasoning_strict_json.py
```

---

## 2) Data Models (Pydantic)

```python
# reasoning/models.py
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

class EvidenceItem(BaseModel):
    source: str                 # "ct_gov_studies" | "fda_info" | "pubmed_articles" | ...
    id: Optional[str] = None    # NCT, PMID, recall id, CIK, etc.
    title: Optional[str] = None
    url: Optional[str] = None
    meta: Dict[str, Any] = {}

class TraceEvent(BaseModel):
    step: str                   # "expand", "search", "refine", "chain"
    strategy: str               # "ICD10_map", "ct_suggest", "broaden_dates", ...
    tool: Optional[str] = None
    input: Dict[str, Any] = {}
    outcome: Dict[str, Any] = {}# {"hits":12,"status":"ok"} or {"error": "..."}
    reason: str                 # why next action chosen

class FinalResponse(BaseModel):
    answer: Dict[str, Any] = {}           # summary tailored to prompt
    evidence: List[EvidenceItem] = []
    trace: List[TraceEvent] = []
    limitations: List[str] = []
    next_best_actions: List[str] = []

class ToolQuery(BaseModel):
    tool: str
    params: Dict[str, Any]

class ToolResult(BaseModel):
    tool: str
    ok: bool
    hits: int
    data: Any
    error: Optional[str] = None
```

---

## 3) Config & Heuristics

```python
# reasoning/config.py
from pydantic import BaseModel

class ReasoningConfig(BaseModel):
    min_ok: int = 5               # too_few if <5
    max_ok: int = 500             # too_many if >500
    max_rounds: int = 3           # expansion/refinement cycles
    per_query_timeout_s: int = 20
    parallel_limit: int = 5
    default_years_back: int = 10  # initial trial search window
    broaden_years_back: int = 20  # on expand_up
    ranking_weights: dict = {
        "authority": 0.5, "recency": 0.3, "yield": 0.2
    }
```

---

## 4) Orchestrator Loop (plan–act–observe–reflect)

```python
# reasoning/orchestrator.py
import asyncio
from .models import FinalResponse, TraceEvent
from .config import ReasoningConfig
from .utils import is_zero, too_few, too_many
from .playbooks import (
    propose_initial_steps, expand_alternatives, refine_query, finalize_answer
)
from .rankers import pick_best_result

class ReasoningOrchestrator:
    def __init__(self, adapters, config: ReasoningConfig):
        self.adapters = adapters   # dict of tool adapters
        self.config = config
        self.trace = []

    async def run(self, task: dict) -> FinalResponse:
        state = {"task": task, "working_terms": set(), "results": {}}
        steps = propose_initial_steps(task)
        rounds = 0

        for step in steps:
            result = await self._run_step(step, state)
            if is_zero(result):
                while rounds < self.config.max_rounds:
                    rounds += 1
                    alt_steps = expand_alternatives(step, state, self.config)
                    results = await self._run_parallel(alt_steps)
                    best = pick_best_result(results)
                    self._log("expand", step, best, reason="zero-hit recovery")
                    if not is_zero(best):
                        state = self._merge(best, state)
                        break
                continue

            if too_many(result, self.config):
                refined = refine_query(step, state, self.config)
                result2 = await self._run_step(refined, state)
                self._log("refine", refined, result2, reason="overbroad narrowing")
                state = self._merge(result2, state)
            else:
                state = self._merge(result, state)

        return finalize_answer(state, self.trace, self.config)

    async def _run_step(self, step, state):
        adapter = self.adapters[step["tool"]]
        res = await adapter.call(step["params"])
        self._log("search", step, res, reason="primary attempt")
        return res

    async def _run_parallel(self, steps):
        sem = asyncio.Semaphore(self.config.parallel_limit)
        async def run_one(s):
            async with sem:
                return await self._run_step(s, state={"parallel": True})
        return await asyncio.gather(*[run_one(s) for s in steps], return_exceptions=False)

    def _log(self, strategy, step, res, reason):
        self.trace.append(TraceEvent(
            step=step.get("name","search"),
            strategy=strategy,
            tool=step.get("tool"),
            input=step.get("params",{}),
            outcome={"hits": getattr(res, "hits", None), "ok": getattr(res,"ok",None)},
            reason=reason
        ))

    def _merge(self, res, state):
        # update working terms/evidence as needed; dedupe
        # attach by tool key
        return state
```

---

## 5) Tool Adapters (thin, typed, timeout-safe)

```python
# reasoning/adapters.py
import asyncio
from .models import ToolResult

class CtGovAdapter:
    def __init__(self, client, timeout_s:int):
        self.client = client; self.timeout_s = timeout_s

    async def call(self, params) -> ToolResult:
        try:
            data = await asyncio.wait_for(self.client.search(**params), timeout=self.timeout_s)
            return ToolResult(tool="ct_gov_studies", ok=True, hits=len(data or []), data=data)
        except Exception as e:
            return ToolResult(tool="ct_gov_studies", ok=False, hits=0, data=None, error=str(e))

# Repeat pattern for: ct_gov_studies.suggest, nlm_ct_codes.map, fda_info.lookup/recalls, pubmed_articles.search_advanced, sec_edgar.search_companies, who_health.get_health_data
```

> **Note:** If your current MCP wrappers are synchronous, wrap with `run_in_executor`. Always enforce `asyncio.wait_for` timeouts.

---

## 6) Playbooks (expansion & refinement)

```python
# reasoning/playbooks.py
from typing import List, Dict
from .utils import year_window

def propose_initial_steps(task: dict) -> List[Dict]:
    # broad-first trial search if condition present
    steps = []
    terms = extract_terms(task)        # disease, drug/device, sponsor, outcomes
    codes = []                         # filled later by expansion
    steps.append({
        "name":"initial_trials",
        "tool":"ct_gov_studies.search",
        "params":{
            "q": terms.free_text, "status": "any",
            "start_date_from": year_window(years_back=10)["from"]
        }
    })
    # If drug/device present, queue FDA lookup early to enrich synonyms
    if terms.asset:
        steps.append({
            "name":"fda_enrich",
            "tool":"fda_info.lookup",
            "params":{"query": terms.asset}
        })
    return steps

def expand_alternatives(step, state, cfg):
    # Branches: codes, synonyms, suggest(), broaden dates, drop filters
    t = state.get("working_terms", set())
    alts = []

    # 1) Map to codes (ICD-10, HPO, MeSH)
    if "codes_mapped" not in state:
        alts.append({
            "name":"code_map",
            "tool":"nlm_ct_codes.map",
            "params":{"terms": list(t)}
        })

    # 2) ct.gov suggest to normalize terminology
    alts.append({
        "name":"ct_suggest",
        "tool":"ct_gov_studies.suggest",
        "params":{"q": " ".join(t)}
    })

    # 3) Broaden date window
    alts.append({
        "name":"trials_broaden",
        "tool":"ct_gov_studies.search",
        "params":{
            "q":" ".join(t), "status":"any",
            "start_date_from": year_window(cfg.broaden_years_back)["from"]
        }
    })

    # 4) Switch to sponsor-only or product-code-only if available
    if state.get("sponsor_name"):
        alts.append({
            "name":"trials_sponsor_only",
            "tool":"ct_gov_studies.search",
            "params":{"q": state["sponsor_name"]}
        })

    if state.get("device_product_code"):
        alts.append({
            "name":"trials_device_code",
            "tool":"ct_gov_studies.search",
            "params":{"q": state["device_product_code"]}
        })

    return alts

def refine_query(step, state, cfg):
    # Narrow down: add phase, status, geo, outcome keywords
    narrowed = dict(step)
    narrowed["params"] = {**step["params"], **{
        "phase": "Phase 2,Phase 3",
        "status": "recruiting,active,completed",
    }}
    return narrowed

def finalize_answer(state, trace, cfg):
    # Build FinalResponse from state; summarize; attach evidence
    from .models import FinalResponse, EvidenceItem
    evidence = state.get("evidence", [])
    limitations = state.get("limitations", [])
    nba = state.get("next_best_actions", [])
    answer = state.get("summary", {})
    return FinalResponse(
        answer=answer,
        evidence=evidence,
        trace=trace,
        limitations=limitations,
        next_best_actions=nba
    )
```

---

## 7) Ranking Heuristic

```python
# reasoning/rankers.py
def pick_best_result(results):
    # results: List[ToolResult]
    # Score by authority > recency > yield
    def score(r):
        if not r.ok: return -1
        # example heuristic: authority by tool
        auth = {"nlm_ct_codes":3,"fda_info":3,"ct_gov_studies":2,"pubmed_articles":2,"sec_edgar":2,"who_health":1}.get(r.tool,1)
        recency = extract_recency_signal(r.data)  # implement per tool
        yield_ = min(getattr(r,"hits",0), 100) / 100
        return 0.5*auth + 0.3*recency + 0.2*yield_
    return max(results, key=score, default=None)
```

---

## 8) Utils

```python
# reasoning/utils.py
from datetime import date, timedelta

def is_zero(res): return (not res) or (getattr(res,"hits",0) == 0)
def too_few(res, cfg): return getattr(res,"hits",0) < cfg.min_ok
def too_many(res, cfg): return getattr(res,"hits",0) > cfg.max_ok

def year_window(years_back:int):
    # naive helper: return first day from N years back
    return {"from": f"{date.today().year - years_back}-01-01"}

def dedupe(items, key=lambda x: x): 
    seen=set(); out=[]
    for it in items:
        k=key(it)
        if k in seen: continue
        seen.add(k); out.append(it)
    return out
```

---

## 9) Integrate with Existing Agent

* **agent.py**

  * Inject the orchestrator and adapters in your agent’s main `run()` (or equivalent) method.
  * Preserve existing simple search path behind a **feature flag** `REASONING_ENABLED=true`.
  * Ensure final return uses `FinalResponse.model_dump()` (strict JSON).

```python
# agent.py (snippet)
from .reasoning.orchestrator import ReasoningOrchestrator
from .reasoning.config import ReasoningConfig
from .reasoning.adapters import CtGovAdapter, PubMedAdapter, FdaAdapter, CodesAdapter, SecAdapter, WhoAdapter

class SourceDiscoveryAgent:
    def __init__(self, tool_clients, cfg=None):
        self.reasoning = ReasoningOrchestrator(
            adapters={
                "ct_gov_studies.search": CtGovAdapter(tool_clients.ct, timeout_s=20),
                "ct_gov_studies.suggest": CtGovAdapter(tool_clients.ct_suggest, timeout_s=10),
                "nlm_ct_codes.map": CodesAdapter(tool_clients.codes, timeout_s=10),
                "fda_info.lookup": FdaAdapter(tool_clients.fda, timeout_s=20),
                "pubmed_articles.search_advanced": PubMedAdapter(tool_clients.pubmed, timeout_s=20),
                "sec_edgar.search_companies": SecAdapter(tool_clients.sec, timeout_s=20),
                "who_health.get_health_data": WhoAdapter(tool_clients.who, timeout_s=20),
            },
            config=cfg or ReasoningConfig()
        )

    async def run(self, task: dict):
        return await self.reasoning.run(task)
```

---

## 10) Testing (Pytest)

1. **Zero-hit recovery**

* Input: “closed-loop insulin for type 2 diabetes” with an intentionally over-narrow filter.
* Expect: expansion via `nlm_ct_codes` (ICD-10 E11), `ct_gov_studies.suggest`, broadened window; `hits >= min_ok`; `trace` includes recovery steps.

2. **Overbroad narrowing**

* Input: “cancer” with no constraints.
* Expect: first search `too_many`, then refine (phase/status); final hits within `[min_ok, max_ok]`.

3. **Chaining**

* Input: “recent recalls for cardiac monitoring implants and related trials + literature.”
* Expect: `fda_info.lookup/recalls` → device product codes → trials → PubMed; `evidence` aggregates NCT/PMID/recall ids.

4. **Strict JSON & trace completeness**

* Validate `FinalResponse` against Pydantic; ensure `trace` has entries for each attempt with reasons.

---

## 11) Config & Feature Flags

* `REASONING_ENABLED=true`
* Thresholds via env or config file:

  * `MIN_OK`, `MAX_OK`, `MAX_ROUNDS`, `PARALLEL_LIMIT`, `TIMEOUT_S`
* Logging verbosity:

  * `REASONING_LOG_LEVEL=INFO|DEBUG`
  * `REASONING_TRACE_SAMPLING=1.0` (fraction to keep)

---

## 12) Observability

* Structured JSON logs per `TraceEvent`.
* Emit counters:

  * `zero_hit_recoveries_count`
  * `overbroad_refinements_count`
  * `avg_rounds_to_success`
  * `timeouts_count`
* Add `X-Reasoning-Trace-Id` to tie logs for a single run.

---

## 13) Example Output (strict JSON)

```json
{
  "answer": {
    "summary": "Found 18 Phase II/III trials for AID systems in Type 2 diabetes (last 10y). No FDA device recalls specific to model X; two MDR events noted for product code 'MDS'. Three recent PubMed reviews summarize outcomes and safety.",
    "key_points": ["Top sponsors: ...", "Primary completion windows: ..."]
  },
  "evidence": [
    {"source":"ct_gov_studies","id":"NCT01234567","title":"..."},
    {"source":"fda_info","id":"recall_ABC123","meta":{"product_code":"MDS"}},
    {"source":"pubmed_articles","id":"PMID:38900123","title":"..."}
  ],
  "trace": [
    {"step":"initial_trials","strategy":"search","tool":"ct_gov_studies.search","input":{"q":"closed loop insulin type 2","status":"any","start_date_from":"2015-01-01"},"outcome":{"hits":0,"ok":true},"reason":"primary attempt"},
    {"step":"code_map","strategy":"expand","tool":"nlm_ct_codes.map","input":{"terms":["type 2 diabetes"]},"outcome":{"hits":3,"ok":true},"reason":"zero-hit recovery"},
    {"step":"ct_suggest","strategy":"expand","tool":"ct_gov_studies.suggest","input":{"q":"AID E11"},"outcome":{"hits":12,"ok":true},"reason":"normalize terminology"},
    {"step":"trials_broaden","strategy":"expand","tool":"ct_gov_studies.search","input":{"q":"AID E11","status":"any","start_date_from":"2005-01-01"},"outcome":{"hits":27,"ok":true},"reason":"broaden window"},
    {"step":"refine","strategy":"refine","tool":"ct_gov_studies.search","input":{"phase":"Phase 2,Phase 3","status":"recruiting,active,completed"},"outcome":{"hits":18,"ok":true},"reason":"overbroad narrowing"}
  ],
  "limitations": ["MDR data may lag; EU MDR not queried."],
  "next_best_actions": ["Query EMA/EUDAMED when available", "Cross-check payer coverage for device codes"]
}
```

---

## 14) Implementation Order (Cursor Tasks)

1. **Scaffold** `reasoning/` package (models, config, utils).
2. Build **adapters** with timeouts; wire to existing MCP clients.
3. Implement **orchestrator** loop with trace logging.
4. Add **playbooks** (expand/refine/finalize).
5. Add **ranker** and simple scoring heuristic.
6. Integrate into `agent.py` behind `REASONING_ENABLED`.
7. **Tests**: add four pytest files; ensure green.
8. Add **observability** counters + structured logs.
9. Tune thresholds from defaults after first runs.

---

## 15) Notes & Guardrails

* **Determinism:** sort candidate expansions and use stable ranking to keep outputs reproducible.
* **Cancellation:** cancel pending parallel tasks once a sufficiently good result has been chosen.
* **Safety:** redact PII if surfaced from SEC/WHO queries; respect tool rate limits (add jitter).
* **Performance:** cache `nlm_ct_codes.map` and `ct_gov_studies.suggest` results for session.

---

This plan keeps everything **in-agent**, LS\&H-aware, and production-friendly. Paste the scaffolding, wire your existing tool clients into the adapters, and you’re off.