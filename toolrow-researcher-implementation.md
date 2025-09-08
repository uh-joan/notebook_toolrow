# Toolrow Researcher — RAG → MCP → “Add to Sources”

*A Cursor implementation plan *

> **Goal**
> In SurfSense, answer from selected **documents** first (RAG). If coverage is low and **Toolrow MCP** is enabled, call live public-data tools (FDA/ct.gov/PubMed/SEC/WHO). Show results with provenance and a one-click **“Add to Sources”** (Live or Snapshot).

---

## 0) Discovery (Cursor, explore the codebase first)

Create `toolrow-researcher-discovery.md` and jot findings.

* **Backend entrypoints**: search for `FastAPI`, `app = FastAPI`, `@app.get`, `uvicorn`, `celery`, `pgvector`.
* **RAG stack**: search `PGVector`, `embed`, `retriever`, `similarity_search`, `hybrid`.
* **Researcher UI**: search Next.js for `Researcher`, `Mode: Q&A`, `Select Connectors`, `Chunks`, `Documents`.
* **Ingestion/Indexing**: search `connector`, `document_ingest`, `embeddings`, `upload`.
* **Settings**: search `.env`, `BaseSettings`, `config`, `NEXT_PUBLIC_`.
* **Logs/telemetry**: search `logger`, `sentry`, `analytics`, `eventBus`.

Keep the plan below adaptable to real file paths you discover.

---

## 1) Feature flag & config

* **.env (backend)**

  ```
  TOOLROW_MCP_ENABLED=true
  TOOLROW_API_TOKEN=REDACTED
  TOOLROW_MCP_MAX_CALLS_PER_ASK=6
  TOOLROW_MCP_TIMEOUT_MS=30000
  ```

* **env.local (frontend)**

  ```
  NEXT_PUBLIC_TOOLROW_MCP_ENABLED=true
  ```

* **`backend/config/mcp_servers.json`** (checked-in, no secrets):

  ```json
  {
    "mcpServers": {
      "toolrow-gateway": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@uh-joan/toolrow-mcp-server"],
        "env": ["TOOLROW_API_TOKEN"]
      }
    }
  }
  ```

✅ *Acceptance*: flipping `TOOLROW_MCP_ENABLED=false` yields current RAG-only behavior.

---

## 2) DB migrations — unified sources

Create **`source_refs`** and **`notebook_sources`**.

```sql
-- 001_create_source_refs.sql
CREATE TABLE IF NOT EXISTS source_refs (
  id UUID PRIMARY KEY,
  mode TEXT CHECK (mode IN ('live','snapshot')) NOT NULL,
  provider TEXT NOT NULL,          -- fda | ct_gov | pubmed | sec | who | codes
  kind TEXT NOT NULL,              -- drug_label | trial | article | filing | indicator
  canonical_id TEXT,
  title TEXT,
  uri TEXT,
  params JSONB,                    -- for live queries
  artifacts JSONB,                 -- for snapshots [{type:'pdf|html|json|csv', path:'sandbox:/...'}]
  ttl_sec INT DEFAULT 86400,
  last_run TIMESTAMPTZ,
  hash TEXT,
  provenance JSONB,                -- {mcp_server, version, fetched_at}
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- 002_create_notebook_sources.sql
CREATE TABLE IF NOT EXISTS notebook_sources (
  id UUID PRIMARY KEY,
  notebook_id UUID NOT NULL,
  source_ref_id UUID NOT NULL REFERENCES source_refs(id) ON DELETE CASCADE,
  added_by UUID,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

✅ *Acceptance*: migrations apply; simple CRUD works.

---

## 3) MCP process manager (spawn `toolrow-gateway`)

Create `backend/toolrow_mcp/registry.py` & `client.py`.

* **registry.py**

  * Load `config/mcp_servers.json`.
  * Resolve env names to real values (e.g., `TOOLROW_API_TOKEN`).
  * Spawn with `subprocess.Popen` (stdio).
  * Health-check: on start, call `list_tools`; respawn on exit.

* **client.py** (sketch)

  ```python
  class ToolrowMCPClient:
      def __init__(self, proc): ...
      async def list_tools(self) -> list[dict]: ...
      async def invoke(self, tool: str, params: dict, timeout_ms: int) -> dict: ...
  ```

* **Dev inspector route**

  * `GET /api/toolrow/servers` → {name, status, tools\[]}
  * `POST /api/toolrow/restart/:name` (dev-only)

✅ *Acceptance*: server runs; `list_tools` returns Toolrow catalog.

---

## 4) Normalized entity model (backend types)

Create `backend/toolrow_mcp/types.py`:

```python
from typing import Literal, TypedDict, NotRequired, List, Dict

Provider = Literal['fda','ct_gov','pubmed','sec','who','codes']
Kind = Literal['drug_label','trial','article','filing','indicator']

class Artifact(TypedDict):
    type: Literal['pdf','html','json','csv']
    path: str
    uri: NotRequired[str]

class EntityRecord(TypedDict, total=False):
    provider: Provider
    kind: Kind
    canonical_id: str
    title: str
    uri: str
    summary: str
    metadata: Dict
    artifacts: List[Artifact]
```

Add per-provider **normalizers** in `backend/toolrow_mcp/normalizers/`.

---

## 5) Research orchestrator (RAG → MCP)

Create `backend/research/orchestrator.py`:

* `rag_answer(q, doc_ids) -> (answer, citations, coverage)`
* `detect_intent(q) -> Intent` (rule-based v1)
* `canonicalize(q) -> codes/IDs` using Toolrow `nlm_ct_codes.map`
* `route_tools(intent) -> [ToolCall]`
* `rag_then_mcp(q, docs, toolrow_enabled) -> AnswerPayload`

**Coverage heuristic v1**

* If ≥2 citations **and** cross-encoder/score ≥ 0.6 → RAG sufficient.
* Else → call MCP.

**Pseudocode**

```python
ans, cites, cov = rag_answer(q, selected_docs)
if cov >= 0.6 or not toolrow_enabled:
    return {answer: ans, citations: cites, coverage: cov}

intent = detect_intent(q)
params = canonicalize(q)
tools  = route_tools(intent)
hits   = await parallel_invoke(toolrow_client, tools, params)

return {
  answer: synthesize(ans, hits),
  citations: cites,
  coverage: cov,
  liveCandidates: hits,
  toolInvocations: tools
}
```

✅ *Acceptance*: unit tests cover both branches.

---

## 6) Snapshot promotion pipeline

Create `backend/snapshots/{fetcher.py, parser.py, embedder.py}`.

* Given `EntityRecord` → resolve canonical URIs (label HTML/PDF, NCT page, SEC filing, PubMed abstract/PMCID).
* Download to `/mnt/data/snapshots/...`.
* Extract clean text (PDF → HTML/text).
* Chunk & embed via existing PGVector pipeline.
* Insert `source_refs` (mode=`snapshot`) + `notebook_sources` link.

Add Celery task: `promote_snapshot_batch(records, notebook_id)`.

✅ *Acceptance*: FDA label/NCT entities become searchable RAG docs.

---

## 7) API endpoints (FastAPI)

* `POST /api/research/ask`

  ```json
  {
    "question": "any other drug in the market in the US for obesity?",
    "selected_source_ids": ["..."],
    "toolrow_enabled": true,
    "notebook_id": "..."
  }
  ```

  **Response**

  ```json
  {
    "answer":"...",
    "citations":[{"type":"doc","source_id":"..."},{"type":"live","provider":"fda","params_hash":"..."}],
    "coverage":0.22,
    "liveCandidates":[
      {"provider":"fda","kind":"drug_label","canonical_id":"NDA215866","title":"Zepbound","uri":"..."}
    ],
    "toolInvocations":[{"tool":"fda_info.labels.search","params":{"indication":"obesity","region":"US"}}]
  }
  ```

* `GET /api/toolrow/servers`

* `POST /api/toolrow/invoke` → `{tool, params}`

* `POST /api/sources/add_live` → `{provider, kind, params, ttl_sec, notebook_id}`

* `POST /api/sources/promote_snapshot` → `{entity_records:[...], notebook_id}`

* `POST /api/sources/refresh/{source_id}` → `{delta:{added,removed,changed}, new_hash}`

* `GET /api/sources/by_notebook/{notebook_id}`

**Caching**
Redis key: `mcp:{tool}:{hash(normalized_params)}` with provider-specific TTL (trials 6–12h; labels 24h; PubMed 24–48h; SEC 24h; WHO 1–7d).

---

## 8) Researcher UI (Next.js)

* **Connector picker**: add **Toolrow MCP** toggle. Sub-pane lists enabled tools (FDA/ct.gov/PubMed/SEC/WHO/Codes) from `/api/toolrow/servers`.
* **Coverage chip** on each answer (e.g., `Coverage: 0.83`).
* If coverage < threshold and MCP enabled:

  * Render **Live Results** list (cards) with provider badge, title, canonical ID.
  * Actions:

    * **Add all to Sources** split-button:

      * **Live** → save query (params+TTL)
      * **Snapshot** → download artifacts & embed
    * Per-row **Add** with same split.
* **Sources sidebar** (per notebook)

  * **Documents (Snapshots)** and **Live**
  * Live: **Refresh** button, last run, **Diff** chip (e.g., “+1 label update”)
  * Snapshots: “View PDF/HTML”; included in **Documents** scope.

**New components**

* `components/research/CoverageChip.tsx`
* `components/research/LiveResultsList.tsx`
* `components/research/SourcesSidebar.tsx`
* `components/research/AddToSourcesSplitButton.tsx`

**Provenance chips**

* `[Doc: Semaglutide report.pdf]`
* `[Live: Toolrow • fda_info.labels.search (US, obesity)]`

---

## 9) Intent → Tool routing (v1 rules)

Create `backend/research/routing.py`:

* “marketed/approved drugs in US/EU for *condition*”
  → `nlm_ct_codes.map` (condition → codes)
  → `fda_info.labels.search {indication_codes, region:"US", marketed:true}`

* “active/phase 2/3 trials”
  → `ct_gov_studies.search {condition_codes?, drug?, phase?, status?}`

* “recent literature / reviews (last 24 mo)”
  → `pubmed_articles.search_advanced {query, filters}`

* “company filings”
  → `sec_edgar.search {cik?, q, form}`

* “burden/epi”
  → `who_health.query {indicator_id, countries, years}`

---

## 10) Budgets, governance, resilience

* **Budgets**: `TOOLROW_MCP_MAX_CALLS_PER_ASK`, concurrent call cap; graceful fallback to RAG-only with a UI notice.
* **Allow-lists**: per workspace, which Toolrow tools can run.
* **Audit log**: tool name, params hash, latency, record count, user.
* **Respawn**: back-off 1→2→5s; periodic `list_tools` healthcheck.
* **Redaction**: never log tokens; scrub sensitive params.

---

## 11) Tests

* **Unit**

  * Orchestrator coverage logic
  * Routing maps → expected Toolrow tool
  * MCP client timeouts/retries
  * Snapshot promotion (artifact → embed)

* **Integration**

  * `/api/research/ask` RAG-sufficient path
  * `/api/research/ask` low coverage → MCP results → Add to Sources (Live & Snapshot)

* **E2E**

  * Semaglutide story:

    1. Q1 answered from doc with citations.
    2. Q2 triggers MCP; list \~6 drugs; **Add all** as Live & Snapshot.
    3. Re-ask → cites labels; **Refresh** live source → see **Diff** if changed.

---

## 12) Telemetry & UX polish

* Emit `research.ask` events `{coverage, took_ms, tool_calls, cached}`.
* Per tool call: `{provider, latency_ms, cached, records}`.
* Progressive render of MCP results; skeleton loaders; retry toasts.

---

## 13) Rollout plan

* **Phase 1**: ct.gov + PubMed, private beta.
* **Phase 2**: FDA drugs/devices + Snapshot promotion.
* **Phase 3**: SEC + WHO.
* **Phase 4**: Auto `nlm_ct_codes` mapping by default.

Keep the feature flag on during rollout.

---

## 14) Developer PR checklist

* [ ] FF & config (envs + `mcp_servers.json`)
* [ ] DB migrations (`source_refs`, `notebook_sources`)
* [ ] MCP registry + client; dev inspector route
* [ ] Orchestrator (RAG→MCP) + coverage scorer
* [ ] API: `/research/ask`, `/toolrow/*`, `/sources/*`
* [ ] Snapshot promotion (fetch→embed)
* [ ] Researcher UI (toggle, live results, add-to-sources, sidebar)
* [ ] Caching/budgets/audit
* [ ] Tests: unit/integration/E2E
* [ ] Docs: `docs/toolrow-researcher.md` (+ schemas dump)

---

## 15) Done criteria (semaglutide acceptance)

* Q1 (“what year approved in US for diabetes?”) returns from **selected document** with citations and `Coverage ≥ 0.6`.
* Q2 (“any other drug in the market in the US for obesity?”) triggers **Toolrow MCP**; UI lists \~6 drugs with provider badges.
* Clicking **Add all to Sources**:

  * **Live**: saves the FDA query (TTL 24h) with **Refresh/Diff** available.
  * **Snapshot**: downloads label artifacts, embeds them; they appear in **Documents** scope and are citable.
* Re-ask shows citations to new label sources; **Refresh** later yields diffs if labels changed.

---

## 16) Notes on the `toolrow-gateway` spawn

* The backend spawns the MCP server as:

  * `command: npx`
  * `args: ["-y", "@uh-joan/toolrow-mcp-server"]`
  * `env: { TOOLROW_API_TOKEN }` (loaded from process env)
* Prefer **lazy startup** (on first use); provide a dev toggle for **eager start**.
* Expose schemas via **Dev Inspector** (`/dev/toolrow`) to explore tools & params interactively.

---

Paste this file as `toolrow-researcher-implementation.md`, run migrations, enable the flag, and use the Dev Inspector to validate `toolrow-gateway` before wiring the Researcher UI.
