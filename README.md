# NanoGaze MLOps

A goal-driven research agent that returns **verified, hallucination-free** answers. You give it a research goal; it plans the searches, runs every source through a dual-engine hallucination filter, and synthesizes a cited brief from only what survives.

Powered by **Gemini 2.5 Flash**, backed by **MongoDB Atlas via MCP**, built for the [Google Cloud Rapid Agent Hackathon](https://googlecloudrapidagenthackathon.devpost.com/) — **MongoDB track**.

---

## The Problem

AI agents that search the web and report findings can't be trusted blindly. Raw LLM output mixes fabricated claims, dead links, fake IPs, non-existent CVEs, and unverifiable statistics in with real data. NanoGaze filters it automatically and only synthesizes an answer from sources that pass.

---

## What it does

You type a research goal. The agent then:

```
1. PLAN      Gemini turns your goal into targeted search queries
2. SEARCH    DuckDuckGo fetches sources (recency filter configurable)
3. SCORE     Each source gets a Gemini credibility read
4. ENGINE 1  Trust scoring — 4 auto-detected metrics, drops low-trust sources
5. ENGINE 2  Fact validation — IPs, URL reachability, CVEs, consistency
6. SYNTHESIZE  Gemini writes a brief from ONLY the verified survivors
7. REMEMBER  Per-domain reputation accumulates in MongoDB across sessions
```

Everything streams live to the dashboard, and every artifact — raw sources, verified, eliminated, the brief, domain reputation — is stored in MongoDB Atlas through the MCP server.

---

## Why this is an agent, not a chatbot

- **It plans** — query generation is goal-dependent and non-deterministic, not a fixed list
- **It uses tools** — web search, a dual-engine filter, and MongoDB through MCP
- **It acts** — writes verified/eliminated sets to MongoDB, generates reports, exports briefs
- **It remembers** — domain reputation is long-term memory that improves trust judgments over time
- **You stay in control** — editable prompt, queries, recency filter, and a live view of every step

---

## Architecture

```
                       Research Goal
                            │
                            ▼
              Gemini — generates search queries
                            │
                            ▼
                  DuckDuckGo web search
                            │
                            ▼
            Gemini — per-source credibility read
                            │
                            ▼
   MongoDB Atlas (via MCP): raw_queue ── reports/report_raw.html
                            │
                            ▼
              Engine 1 — Trust Scoring (0–100%)
                 completeness · validity · reputation · richness
                            │
                            ▼
              Engine 2 — Fact Validation
                 IP sanity · URL reachability · CVE lookup · consistency
                            │
                   ┌────────┴────────┐
                   ▼                 ▼
              safe_traffic      active_threats        ← MongoDB via MCP
                   │                 │
                   ▼                 ▼
              Gemini — synthesizes verified brief
                            │
                            ▼
         research_sessions + domain_reputation        ← MongoDB via MCP
```

---

## Two ways to run it

**1. Dashboard** (`localhost:8080`) — type a goal in the Research tab, watch the pipeline stream live, get a cited brief with verified sources. Tabs: Research · Raw Data · Verified · Eliminated · History · Reputation · Prompt.

**2. Google ADK agent** (`adk web`) — chat with the agent; its primary tool `run_research(goal)` calls the same hosted pipeline on Cloud Run. Same mission, conversational entry point.

---

## Engine 1 — Trust Scoring

| Metric | What it measures |
|---|---|
| Completeness | How many expected fields have data |
| Validity | URL well-formed, title/body substantive |
| Reputation | Source domain reliability |
| Richness | Title and body length/depth |

Weighted into a 0–100% trust score; below `ENGINE1_THRESHOLD` (default 50) is eliminated. Criteria are auto-detected — domain-agnostic.

## Engine 2 — Fact Validation

| Check | What it does |
|---|---|
| IP validation | Flags entries with only private/loopback IPs |
| URL reachability | Confirms the source URL returns a valid response |
| CVE lookup | Verifies any CVE mentioned exists in the NVD database |
| Credibility consistency | Flags low-credibility entries with zero supporting signals |

---

## Stack

| Layer | Technology |
|---|---|
| Reasoning / synthesis | Gemini 2.5 Flash (Google) |
| Agent framework | Google ADK (Agent Builder) |
| Search | DuckDuckGo |
| Database | MongoDB Atlas |
| DB integration | **MongoDB MCP Server** |
| Engine 1 | Trust scoring (auto-detected criteria) |
| Engine 2 | IP/URL/CVE validation + consistency |
| Dashboard | Python HTTP server + SSE live stream |
| Hosting | Google Cloud Run |

---

## Setup

**Requirements:** Python 3.13+, Node.js 20+ (for the MongoDB MCP server)

```bash
git clone https://github.com/ygtdalkilic/NanoGaze-MLOps.git
cd NanoGaze-MLOps
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
npm install -g mongodb-mcp-server
```

Copy `.env.example` to `.env` and fill in your keys:

```env
GEMINI_API_KEY=your_key_here
MONGO_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/
```

---

## Run

```powershell
.venv\Scripts\python.exe run.py
```

Open `http://localhost:8080`, go to the **Research** tab, type a goal, and hit **Start Research**.

To run the ADK agent instead:

```powershell
adk web .
```

---

## Project layout

```
src/
├── agent.py        # Gemini search + per-source credibility analysis
├── research.py     # goal → queries → search → dual-engine → brief (live streamed)
├── engine_1.py     # trust scoring (auto-detected criteria)
├── engine_2.py     # fact validator (IP, URL, CVE, consistency)
├── pipeline.py     # standalone queue processor (Engine 1 → Engine 2 → reports)
├── reporter.py     # generates the 3 HTML reports + history
├── dashboard.py    # HTTP server, SSE stream, all endpoints
├── mcp_client.py   # MongoDB MCP client (find/insert/delete/upsert)
└── config_store.py # MongoDB-backed config (prompt, queries, recency)

agent_builder/
└── agent.py        # Google ADK agent — run_research is the headline tool

templates/
└── dashboard.html  # dashboard UI (extracted from Python)

prompt.txt          # default Gemini credibility prompt (overridable in UI)
queries.txt         # default search queries (overridable in UI)
run.py              # entry point — starts the dashboard
Dockerfile          # Cloud Run image (Python + Node + MCP server)
```

---

## MongoDB collections

| Collection | Contents |
|---|---|
| `raw_queue` | Raw agent findings pending the pipeline |
| `safe_traffic` | Verified entries that passed both engines |
| `active_threats` | Eliminated entries with the reason why |
| `research_sessions` | Every research run: goal, queries, brief, sources, stats |
| `domain_reputation` | Per-domain credibility accumulated across all sessions |
| `config` | Editable prompt, queries, and recency filter |

---

## Author

Yigit Dalkilic
