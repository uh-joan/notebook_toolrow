Got it. I read through your `SourceDiscoveryAgent` and the prompts it sends. Here’s a tight diagnosis of why it “doesn’t perform well,” plus copy-paste prompt upgrades and small code changes you can hand to Cursor.

---

# What this agent is trying to do (and where it slips)

**Intended flow**

1. Detect query complexity → choose “sequential agentic” vs “direct” path.
2. Use an LLM to **pick tools**.
3. Use an LLM to **build params** per tool (schema-aware).
4. Invoke tools → **rank** + summarize results → emit suggestions and terminal events.

**Main failure modes**

1. **Unconstrained LLM outputs** → non-JSON, extra prose, or wrong keys (despite some cleanup).
2. **Vague selection prompt** → over-selects or under-selects tools; doesn’t privilege the *single* best tool strongly enough.
3. **Param-extraction prompt is generic** → misses enum values, required fields, date/location normalization, and tool-specific quirks.
4. **Result ranking is arbitrary** (`estimated_value` hardcoded) → weak prioritization and noisy summaries.
5. **Sequential mode isn’t truly orchestrated** → the “think” call streams thoughts but doesn’t standardize a plan or enforce tool I/O chaining.
6. **Alt-terms generation is generic** → not grounded in the code systems your tools already expose (e.g., MeSH/HPO/ICD synonyms).
7. **Serial execution** → tools run one by one; slow and brittle under latency.
8. **Weak metrics/guardrails** → no budget/timeouts per step, no retries/backoff policy surface, no deterministic settings.
9. **Complexity classifier is keyword-y** → misroutes many realistic queries.

---

# “Cursor-ready” improvements

PHASE 1

## 1) Lock LLMs to structured JSON (no prose)

* Wherever you call `llm.ainvoke`, set: temperature=0 (or provider’s deterministic mode), `response_format={"type":"json_object"}` (OpenAI-style) or equivalent.
* Wrap **every** prompt with a final hard line:
  **“Return ONLY valid JSON. No markdown fences. No commentary.”**
* Add a 1-shot example with valid JSON for each prompt type.

## 2) Better tool selection: ranked, single-first, with reasons

**Replace** your `tool_analysis_prompt` with this (copy-paste):

```text
You are selecting the MINIMUM set of tools needed to answer a single user query.

USER_QUERY: "<{request.query}>"
FOCUS_AREAS: <{request.focus_areas or "None"}>
FILTERS: <{request.filters or "None"}>

AVAILABLE_TOOLS (name → purpose):
<{json.dumps([{"name": t.get("name"), "description": t.get("description","")} for t in self.available_tools])}>

RULES (critical):
- Prefer EXACTLY ONE tool if it can deliver the core answer. Only add a second tool if it provides a DIFFERENT data type (e.g., trials + literature).
- Map intents deterministically:
  • Codes (ICD/LOINC/RxTerms/NPI) → nlm_ct_codes only
  • Clinical trials → ct_gov_studies only
  • FDA drugs/devices/recalls/labels → fda_info only
  • Biomedical literature → pubmed_articles only
  • Company filings/financials → sec_edgar only
  • WHO indicators → who_health only
- If multiple tools match, rank by: (1) exact fit to intent, (2) coverage breadth, (3) freshness. Pick the top-1.
- If nothing is a good fit, return [].

OUTPUT (JSON ONLY):
{
  "primary": "tool_name_or_null",
  "secondaries": ["tool_name"]  // different data type only, else []
}
Return ONLY JSON.
```

**Why this works:** pushes the LLM to **rank** and **explain via structure**, but still enforces single-tool bias.

In code: if `primary` is present, ignore `secondaries` unless the query explicitly asks cross-modal data (e.g., “trials + recent papers”).

## 3) Schema-driven param builder (with enums + examples)

**Replace** `_build_ai_params` prompt with this (copy-paste):

```text
Extract parameters for the following TOOL using ONLY its schema.

USER_QUERY: "<{request.query}>"

TOOL:
- name: <{tool_name}>
- description: <{tool_description}>
- parameters:
<{json.dumps(param_details or available_parameters)}>

STRICT RULES:
1) Use ONLY keys that exist in the schema. If you don't have a confident value, DROP the key.
2) For enum fields, choose a value from the enum list. If none fits, omit the field.
3) Normalize common fields:
   - status → one of ["recruiting","not-yet-recruiting","active-not-recruiting","completed"] if the query hints; else omit.
   - location/country/region → normalize to ISO country (e.g., "United States") or WHO region codes if schema expects them.
   - time windows → prefer absolute years ("2019:2024") if the query says "last 5 years".
4) Never paste the full query into any parameter.
5) Keep values compact (strings or simple lists). No explanations.

OUTPUT (JSON ONLY): { "<param>": "<value>", ... }
Return ONLY JSON.
```

**Code tweak:** after parsing, **validate against the schema**:

* Remove unknown keys.
* For enums, discard out-of-set values.
* Plug defaults (e.g., `limit`, `num_results`) centrally, not inside the LLM.

## 4) Deterministic complexity routing

Replace `_is_complex_query` with:

* a tiny **intent parser** that extracts: `{entities:[], want: ["codes"|"trials"|"fda"|"papers"|"sec"|"who"], modifiers:{status, location, timeframe}}`.
* Consider complex if **(a)** more than one *want*, **or (b)** presence of conditionals (“then”, “compare”), **or (c)** explicit chaining (“use X to find Y”).
* Otherwise direct mode.

(You can keep your keyword list but gate with the parser result.)

## 5) True orchestration in sequential mode

Your current sequential flow streams “thoughts” but doesn’t enforce a plan. Use a **two-step plan**:

**Plan prompt (first call):**

```text
Plan a short tool-chaining workflow.

USER_QUERY: "<{request.query}>"
TOOLS: <{[t["name"] for t in tools_info]}>

OUTPUT (JSON ONLY):
{
  "steps": [
    {"tool": "tool_name", "params": {"k":"v"}, "why": "short reason"},
    ...
  ],
  "stop_condition": "describe what success looks like in the results"
}
Return ONLY JSON.
```

* Validate each step (schema) locally.
* Then **execute steps** in order; for each result, call a **refine prompt** (optional) that can update next-step params based on previous output (also JSON-only).

This gives you *reliable* chaining without free-form “think”.

## 6) Alternative terms grounded in codes

Instead of a generic synonym prompt, **use your own tools**:

* If the selected tool is trials or literature:

  * First call `nlm_ct_codes` with `method: search_codes` (or equivalent) for MeSH/ICD synonyms for the main condition.
  * Build a list of 2–3 **grounded** alternatives from returned preferred labels/synonyms.
* Only if codes tool fails, fall back to the LLM synonym prompt (still JSON-only).

## 7) Parallelize tool calls and retries

* Change `_execute_discovery_tools` to build `tasks = [invoke(tool) ...]` and `await asyncio.gather(*tasks, return_exceptions=True)`.
* Add an exponential backoff on transient network errors (HTTP 5xx, timeouts) with a **max overall wall clock** per discovery (e.g., 20s).

## 8) Real scoring & ranking

Replace fixed `estimated_value` with a simple composite:

```
score = w1*authority + w2*freshness + w3*query_intent_match + w4*result_density
```

* **authority**: fda=1.0, ctgov=0.9, pubmed=0.8, who=0.8, sec=0.8, nlm=0.75 (tuneable)
* **freshness**: 1.0 if result has date within requested window; else decay by months.
* **intent\_match**: 1.0 if tool equals inferred intent; 0.6 if secondary.
* **density**: log(1+items) normalized.

Attach `metadata.relevance_score = intent_match` and set `estimated_value = score`.

## 9) Tighten terminal events & metrics

* Emit per-phase timings (ms), token usage (if available), and counts.
* Include **selected plan** and **final params** as JSON in the terminal stream for reproducibility.
* Add `trace_id` per run.

## 10) Safer fallbacks

* If tool selection LLM fails → rule-based mapping (you already have it).
* If param builder fails → schema-aware deterministic heuristics (you already have some) but add minimal safe defaults (e.g., no `status` unless explicit).

---

# Drop-in prompt replacements (final)

### A) Tool selection (ranked)

*(use in `_analyze_and_select_tools`)*

```text
... [prompt from section 2 above] ...
```

### B) Param extraction (schema-aware)

*(use in `_build_ai_params`)*

```text
... [prompt from section 3 above] ...
```

### C) Sequential planning (agentic path)

*(use in `_build_sequential_mcp_request` BEFORE execution)*

```text
You are an orchestration planner. Build a minimal step-by-step plan to answer the query with available tools.

USER_QUERY: "<{request.query}>"
TOOLS: <{[t["name"] for t in tools_info]}>

CONSTRAINTS:
- Max 5 steps.
- Prefer one tool unless chaining adds a NEW data type.
- All params must match each tool's schema.

OUTPUT (JSON ONLY):
{
  "steps": [
    {"tool": "tool_name", "params": {...}, "why": "1 sentence"}
  ],
  "stop_condition": "1 sentence"
}
Return ONLY JSON.
```

### D) Alternative terms (fallback only)

```text
Generate up to 3 alternative clinical terms for: "<{original_query}>"
Return ONLY a JSON array of short strings (max 3). No commentary.
```

---

# Minimal code changes (tell Cursor)

1. **Determinism everywhere**

   * Set `temperature=0`, `top_p=1`, and JSON response mode for all LLM calls.
   * Add a `parse_json_strict(str) -> dict` that errors on trailing prose; include one retry with a short “You returned invalid JSON; fix and return JSON only.” system nudge.

2. **Parallel execution**

   * Refactor `_execute_discovery_tools` to run with `asyncio.gather` + per-task timeout + 2 retries (backoff 0.5s → 1.5s).

3. **Schema validation**

   * After `_build_ai_params`, run a validator that:

     * drops unknown keys,
     * enforces enums,
     * coerces numbers/ints from strings,
     * fills standard `limit/num_results` centrally.

4. **Ranking**

   * Implement the composite score and replace hardcoded `estimated_value`.

5. **Sequential planning**

   * Split sequential mode into: `plan = llm.plan(...)` → validate → execute steps → (optional) `llm.refine(next_step, prev_result_excerpt)` if you want adaptivity.

6. **Alt terms via codes**

   * If the chosen tool is `ct_gov_studies` or `pubmed_articles`, first try `nlm_ct_codes` to fetch synonyms; only then fallback to LLM synonyms.

7. **Telemetry**

   * Add per-phase durations, number of tools executed, number of items found, final selected sources, and emit as a final JSON terminal event.

---

# Quick acceptance tests (run locally)

| Query                                            | Expected primary tool | Expected key params                                                                                                   |
| ------------------------------------------------ | --------------------- | --------------------------------------------------------------------------------------------------------------------- |
| “ICD-10 codes for obesity”                       | `nlm_ct_codes`        | `{"terms":"obesity"}`                                                                                                 |
| “Recruiting semaglutide trials in US”            | `ct_gov_studies`      | `{"condition":"semaglutide" (or “obesity/diabetes” per schema), "status":"recruiting", "location":"United States"}`   |
| “Recent FDA label updates for tirzepatide”       | `fda_info`            | `{"search_type":"label","search_term":"tirzepatide"}`                                                                 |
| “GSK 10-K revenue by segment (last 5 years)”     | `sec_edgar`           | `{"method":"get_company_concept" or frames pipeline, "cik_or_ticker":"GSK", "taxonomy":"us-gaap", "tag":"Revenues"}`  |
| “Type 2 diabetes prevalence EU vs US since 2015” | `who_health`          | `{"method":"get_cross_table","indicator_code":<T2D code>,"countries":"USA,DEU,FRA,ITA,ESP,GBR", "years":"2015:2025"}` |

If any test returns prose or non-JSON from the LLM prompts, fix the JSON enforcement first—it’s the #1 reliability lever.


Phase 2
Awesome — here’s a **Cursor-ready add-on plan** that *only* implements the three flagged upgrades:

* **(A)** Sequential routing flag (incl. streaming path)
* **(B)** Strict-JSON LLM I/O (deterministic + retry)
* **(C)** Parallel tool execution with timeout/backoff + per-tool timing

---

# 1) Add a `force_sequential` flag & route it in both paths

**File:** `types.py`

```diff
 class DiscoveryRequest(BaseModel):
     query: str
     user_id: str
     focus_areas: Optional[List[str]] = None
     filters: Optional[Dict[str, Any]] = None
     max_sources: Optional[int] = 20
     discovery_mode: Optional[str] = "BASIC"
     export_format: Optional[str] = None
     conversation_history: Optional[List[str]] = None
+    # Explicitly force the agentic sequential MCP path
+    force_sequential: bool = False
```

**File:** `source_discovery_agent.py` (class `SourceDiscoveryAgent`)

```diff
 async def discover_sources(self, request: DiscoveryRequest, db_session=None) -> DiscoveryResult:
     ...
-    is_complex_query = self._is_complex_query(request.query)
-    if is_complex_query:
+    use_seq = request.force_sequential or self._is_complex_query(request.query)
+    if use_seq:
         self._add_terminal_event("info", "🧠 Complex query detected - using agentic sequential reasoning...")
         return await self._run_sequential_mcp_workflow(request, db_session, start_time)
     else:
         ...
```

**Also enable sequential in streaming:**

```diff
 async def astream_discovery(self, request: DiscoveryRequest, db_session):
     start_time = time.time()
     ...
-    # Sequential reasoning
-    yield self._create_terminal_event("info", "🧠 Analyzing query with sequential reasoning...")
-    await self._sequential_reasoning_analysis(request, db_session)
-    yield self._create_terminal_event("success", f"🧠 Sequential reasoning completed with {len(self.reasoning_steps)} steps")
+    use_seq = request.force_sequential or self._is_complex_query(request.query)
+    if use_seq:
+        yield self._create_terminal_event("info", "🧠 Agentic (sequential MCP) path selected")
+        try:
+            result = await self._run_sequential_mcp_workflow(request, db_session, start_time)
+            yield self._create_terminal_event("success", f"🎯 Agentic workflow completed with {result.total_found} sources")
+            yield result
+            return
+        except Exception as e:
+            yield self._create_terminal_event("warning", f"⚠️ Sequential MCP failed, falling back to direct tools: {e}")
+            # Fall through to direct path
+
+    # Direct path continues below
+    yield self._create_terminal_event("info", "🧠 Analyzing query with sequential reasoning...")
+    await self._sequential_reasoning_analysis(request, db_session)
+    yield self._create_terminal_event("success", f"🧠 Sequential reasoning completed with {len(self.reasoning_steps)} steps")
```

---

# 2) Enforce **strict JSON** for all LLM calls (deterministic + retry)

**File:** `source_discovery_agent.py`

Add helpers near the top of the class:

````python
def _parse_json_strict(self, s: str):
    s = s.strip()
    if s.startswith("```"):
        # Hard reject fenced code to avoid partial parsing risks
        raise ValueError("Markdown fences not allowed")
    data = json.loads(s)
    if not isinstance(data, (dict, list)):
        raise ValueError("JSON must be an object or array")
    return data

async def _llm_json(self, llm, prompt: str, max_retries: int = 1):
    """Call LLM expecting JSON only; deterministic + one retry if invalid."""
    suffix = "\n\nReturn ONLY valid JSON. No markdown fences. No commentary."
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            # If your LLM supports params, force deterministic mode here
            # e.g., await llm.ainvoke(prompt + suffix, temperature=0, top_p=1)
            response = await llm.ainvoke(prompt + suffix)
            content = getattr(response, "content", response)
            return self._parse_json_strict(content)
        except Exception as e:
            last_err = e
            # Minimal corrective retry
            prompt = (
                "Your last output was not valid JSON. Fix it and return ONLY valid JSON for the same task.\n\n"
                + prompt
            )
    raise last_err
````

### Use it in **tool selection**:

Replace inside `_analyze_and_select_tools`:

```diff
- response = await llm.ainvoke([HumanMessage(content=tool_analysis_prompt)])
- content = response.content.strip()
- ... parse with json.loads ...
- selected_tool_names = json.loads(content)
+ data = await self._llm_json(llm, tool_analysis_prompt, max_retries=1)
+ # Accept both: ["tool1","tool2"] OR {"primary": "...", "secondaries":[...]}
+ if isinstance(data, list):
+     selected_tool_names = data
+ else:
+     primary = data.get("primary")
+     secondaries = data.get("secondaries", [])
+     selected_tool_names = [t for t in [primary, *secondaries] if t]
```

### Use it in **AI param building**:

Replace inside `_build_ai_params`:

```diff
- response = await llm.ainvoke(prompt)
- response_text = response.content.strip()
- ... clean code fences ...
- ai_params = json.loads(response_text)
+ data = await self._llm_json(llm, prompt, max_retries=1)
+ ai_params = data if isinstance(data, dict) else {}
```

*(Keep your schema validation right after this: drop unknown keys, enforce enums, add central `limit` etc.)*

---

# 3) Run discovery tools **in parallel** with timeout/backoff + per-tool timing

**File:** `source_discovery_agent.py`

Replace `_execute_discovery_tools` with a parallel version:

```diff
 async def _execute_discovery_tools(self, tools, request: DiscoveryRequest, db_session) -> List[Dict[str, Any]]:
-    if not self.mcp_manager:
-        logger.error("No MCP manager available")
-        return []
-
-    results = []
-
-    for tool in tools:
-        ...
-        # serial invocation
-        ...
-    self._add_terminal_event("success", f"📋 Tools execution complete: {len(results)}/{len(tools)} tools returned data")
-    return results
+    if not self.mcp_manager:
+        logger.error("No MCP manager available")
+        return []
+
+    sem = asyncio.Semaphore(4)  # cap concurrency
+    results: List[Dict[str, Any]] = []
+
+    async def run_tool(tool: Dict[str, Any]) -> Optional[Dict[str, Any]]:
+        tool_name = tool.get("name")
+        if not tool_name:
+            return None
+        attempts = 0
+        max_attempts = 3
+        backoff = 0.6
+        start = time.time()
+        try:
+            async with sem:
+                # Build params once (outside retry unless you want to rebuild every time)
+                params = await self._build_tool_params(tool, request, db_session)
+                if not params:
+                    logger.warning(f"⚠️ No params for {tool_name}")
+                    return None
+                # Show methods if available
+                available_methods = tool.get("methods", [])
+                if available_methods:
+                    self._add_terminal_event("info", f"🎯 Available methods for {tool_name}: {available_methods}")
+
+                while attempts < max_attempts:
+                    attempts += 1
+                    try:
+                        self._add_terminal_event("info", f"🔧 Invoking {tool_name} (attempt {attempts}) with params: {params}")
+                        # Hard per-call timeout (e.g., 30s)
+                        result = await asyncio.wait_for(
+                            self.mcp_manager.invoke_toolrow_tool(tool_name, params, timeout_ms=30000),
+                            timeout=35
+                        )
+                        result_summary = self._summarize_mcp_result(result)
+                        self._add_terminal_event("info", f"✅ {tool_name} result: {result_summary}")
+
+                        if result and not self._is_error_result(result):
+                            if self._has_meaningful_results(result):
+                                self._add_terminal_event("success", f"✅ {tool_name}: SUCCESS - data retrieved")
+                                duration = int((time.time() - start) * 1000)
+                                logger.info(f"{tool_name} done in {duration}ms")
+                                return {"tool": tool_name, "params": params, "result": result, "duration_ms": duration}
+                            else:
+                                # Try alternative terms once per tool if empty
+                                self._add_terminal_event("info", f"🔄 {tool_name}: No results, trying alternative terms…")
+                                alt = await self._try_alternative_terms(tool, request, db_session)
+                                if alt:
+                                    duration = int((time.time() - start) * 1000)
+                                    return {**alt, "duration_ms": duration}
+                                break
+                        else:
+                            self._add_terminal_event("warning", f"⚠️ {tool_name}: Empty or error-like response")
+                    except (asyncio.TimeoutError) as te:
+                        self._add_terminal_event("warning", f"⏱️ {tool_name} timed out (attempt {attempts})")
+                    except Exception as e:
+                        self._add_terminal_event("warning", f"⚠️ {tool_name} error on attempt {attempts}: {e}")
+
+                    if attempts < max_attempts:
+                        await asyncio.sleep(backoff)
+                        backoff *= 1.8
+        finally:
+            pass
+        self._add_terminal_event("warning", f"⚠️ {tool_name}: No usable data after {attempts} attempt(s)")
+        return None
+
+    tasks = [run_tool(t) for t in tools]
+    task_results = await asyncio.gather(*tasks, return_exceptions=True)
+
+    for r in task_results:
+        if isinstance(r, dict):
+            results.append(r)
+        elif isinstance(r, Exception):
+            logger.warning(f"Tool task failed with exception: {r}")
+
+    self._add_terminal_event("success", f"📋 Tools execution complete: {len(results)}/{len(tools)} tools returned data")
+    return results
```

---

## Smoke tests you (or Cursor) should run

1. **Sequential flag works in both paths**

* Call `discover_sources(..., force_sequential=True)` → see “🧠 Agentic (sequential MCP) path selected”.
* Call `astream_discovery(..., force_sequential=True)` → same message in stream + final result.

2. **Strict JSON**

* Temporarily sabotage the LLM to return fenced JSON → verify retry fixes it or hard-fails with a clear error.
* Ensure `_analyze_and_select_tools` accepts both `["tool"]` and `{"primary": "...", "secondaries":[...]}`.

3. **Parallel exec**

* With 3–5 tools available, confirm they run concurrently (wall time << sum of individual times).
* See per-tool attempt/timing terminal events and overall success count.