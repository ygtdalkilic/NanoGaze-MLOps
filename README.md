# NanoGaze MLOps

A goal-driven research agent that returns **verified, corroborated** answers. You give it a research goal; it plans the searches, runs every source through a dual-engine hallucination filter, cross-checks each finding across independent sources, and returns a confidence-rated brief from only what survives.

Powered by **Gemini 2.5 Flash**, backed by **MongoDB Atlas via MCP**, built for the [Google Cloud Rapid Agent Hackathon](https://googlecloudrapidagenthackathon.devpost.com/) — **MongoDB track**.

---

## The Problem

AI agents that search the web and report findings can't be trusted blindly. Raw LLM output mixes fabricated claims, dead links, fake IPs, non-existent CVEs, and unverifiable statistics in with real data. NanoGaze filters it automatically and only synthesizes an answer from sources that pass.

---

## What it does

You type a research goal. The agent then:

```
1. PLAN       Gemini turns your goal into tightly-scoped search queries
2. SEARCH     DuckDuckGo fetches sources (recency filter configurable)
3. RELEVANCE  Gemini drops off-topic results before they're scored
4. CREDIBILITY  Each on-topic source gets a Gemini credibility read
5. ENGINE 1   Trust scoring — 4 metrics + learned reputation, drops low-trust sources
6. ENGINE 2   Fact validation — IPs, URL reachability, CVEs, consistency
7. CORROBORATE  Findings cross-checked across independent sources; contradictions flagged
8. REMEMBER   Per-domain reputation accumulates in MongoDB (only on save)
```

Everything streams live to the dashboard. Each research run is ephemeral — it shows only that run's data — and is persisted to History + reputation memory only when you click **Save to History**. Every artifact is stored in MongoDB Atlas through the MCP server.

---

## Why this is an agent, not a chatbot

- **It plans** — query generation is goal-dependent and non-deterministic, not a fixed list
- **It uses tools** — web search, a dual-engine filter, corroboration, and MongoDB through MCP
- **It acts** — writes verified/eliminated sets to MongoDB, generates reports, exports briefs
- **It remembers** — domain reputation is long-term memory that feeds back into trust scoring
- **It verifies** — claims are confirmed across independent sources, not taken from one source's word
- **You stay in control** — editable prompt, queries, recency filter, explicit save, and a live view of every step

---

## Architecture

```
                       Research Goal
                            │
                            ▼
              Gemini — generates scoped search queries
                            │
                            ▼
                  DuckDuckGo web search
                            │
                            ▼
        Gemini — relevance + credibility read (off-topic dropped)
                            │
                            ▼
              Engine 1 — Trust Scoring (0–100%)
                 completeness · validity · learned reputation · richness
                            │
                            ▼
              Engine 2 — Fact Validation
                 IP sanity · URL reachability · CVE lookup · consistency
                            │
                   ┌────────┴────────┐
                   ▼                 ▼
              safe_traffic      active_threats        ← MongoDB via MCP
                   │
                   ▼
   Gemini — cross-source corroboration (count independent domains
            per claim, flag single-source, detect contradictions)
                            │
                            ▼
                   Confidence-rated brief
                            │
                            ▼   (only on Save to History)
         research_sessions + domain_reputation        ← MongoDB via MCP
                                    │
                                    └──── feeds back into Engine 1 reputation
```

---

## Two ways to run it

**1. Dashboard** (`localhost:8080`) — type a goal in the Research tab, watch the pipeline stream live, get a cited brief with verified sources. Tabs: Research · Raw Data · Verified · Eliminated · History · Reputation · Prompt.

**2. Google ADK agent** (`adk web`) — chat with the agent; its primary tool `run_research(goal)` calls the same hosted pipeline on Cloud Run. Same mission, conversational entry point.

---

## Engine 1 — Trust Scoring

| Metric | Weight | What it measures |
|---|---|---|
| Completeness | 35% | How many expected fields have data |
| Validity | 30% | URL well-formed, title/body substantive |
| Reputation | 20% | Source domain reliability |
| Richness | 15% | Title and body length/depth |

Weighted into a 0–100% trust score; below `ENGINE1_THRESHOLD` (default 50) is eliminated. **Reputation is learned** — once a domain has been seen `REPUTATION_MIN_SAMPLES` times, its score blends the static allowlist with its actual track record from `domain_reputation`, so the system sharpens its judgments the more it's used.

## Engine 2 — Fact Validation

| Check | What it does |
|---|---|
| IP validation | Flags entries with only private/loopback IPs |
| URL reachability | Confirms the source URL returns a valid response |
| CVE lookup | Verifies any CVE mentioned exists in the NVD database |
| Credibility consistency | Flags low-credibility entries with zero supporting signals |

## Corroboration — the truth layer

Engines 1 and 2 confirm a source is *well-formed and not obviously fabricated* — they don't prove its claims are *true*. Corroboration closes that gap: Gemini extracts the key findings from the surviving sources and, for each, counts how many **independent domains** support it.

- A claim backed by ≥ `CORROBORATION_MIN_DOMAINS` (default 2) independent domains is marked **corroborated**
- Single-source claims are explicitly **flagged**, not hidden
- Direct disagreements between sources are surfaced as **contradictions**
- Overall **confidence** (high/medium/low) is derived from the share of corroborated findings

This is what separates "this source looks credible" from "this claim is independently confirmed."

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
├── research.py     # goal → queries → relevance → dual-engine → corroboration → brief (live streamed)
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
| `research_sessions` | Saved research runs: goal, queries, brief, findings + corroboration, contradictions, confidence, sources, stats |
| `domain_reputation` | Per-domain credibility accumulated across saved sessions; feeds back into Engine 1 |
| `config` | Editable prompt, queries, and recency filter |

---

## Author

Yigit Dalkilic
