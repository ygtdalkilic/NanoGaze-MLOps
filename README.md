# NanoGaze MLOps

An AI agent pipeline that filters hallucinations from web search results. Powered by **Gemini**, backed by **MongoDB Atlas via MCP**, and built for the [Google Cloud Rapid Agent Hackathon](https://googlecloudrapidagenthackathon.devpost.com/).

---

## The Problem

AI agents that search the web and report findings can't be trusted blindly. Raw LLM output contains fabricated claims, unverifiable statistics, and low-credibility content mixed with real data. NanoGaze filters it automatically.

---

## How it works

```
Gemini (gemini-2.5-flash) — searches internet, scores credibility, queues findings
        │
        ▼
MongoDB Atlas: raw_queue          ← raw agent findings (via MCP)
        │
        ▼
Engine 1 — Trust Scoring
        │   scores every entry 0–100% across 5 auto-detected metrics
        │   threshold: 50% — below = eliminated
        │
        ▼
Engine 2 — Fact Validation
        │   validates IPs (public vs private/hallucinated)
        │   checks URL reachability
        │   flags low-credibility entries with no verifiable signals
        │
   ┌────┴────┐
   ▼         ▼
Verified   Eliminated (with reason)
        │
        ▼
MongoDB Atlas: safe_traffic / active_threats  ← results written back via MCP
        │
        ▼
Dashboard (localhost:8080)
├── Raw Report       — everything the agent found
├── Verified Report  — passed both engines
└── Eliminated Report — removed + reason why
```

---

## Engine 1 — Trust Scoring

Each entry is scored across 5 auto-detected metrics:

| Metric | What it measures |
|---|---|
| Validity | Fields are non-empty and correctly typed |
| Completeness | How many expected fields have data |
| Popularity | Source domain reliability |
| Discoverability | Title and body length/richness |
| Usage | How often this source appears in the dump |

Criteria are auto-detected from the data — no hardcoded rules, works for any domain.

---

## Engine 2 — Fact Validation

| Check | What it does |
|---|---|
| IP validation | Flags entries with only private/loopback IPs |
| URL reachability | Checks source URL returns a valid HTTP response |
| Credibility consistency | Flags low-credibility entries with zero supporting signals |

---

## Stack

| Layer | Technology |
|---|---|
| AI Agent | Gemini 2.5 Flash (Google Cloud) |
| Search | DuckDuckGo |
| Database | MongoDB Atlas |
| DB Integration | MongoDB MCP Server |
| Engine 1 | Custom trust scoring (auto-detected criteria) |
| Engine 2 | IP/URL validation + credibility consistency |
| Dashboard | Python HTTP server |

---

## Setup

**Requirements:** Python 3.13+, Node.js (for MongoDB MCP server)

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

Open `http://localhost:8080` — click **Run Pipeline** to process the queue.

To skip the agent and only run the pipeline:
```powershell
.venv\Scripts\python.exe run.py --skip-agent
```

---

## Project layout

```
src/
├── agent.py        # Gemini agent — searches, scores credibility, queues findings
├── engine_1.py     # trust scoring (auto-detected criteria)
├── engine_2.py     # fact validator (IP, URL, credibility consistency)
├── pipeline.py     # orchestrator — Engine 1 → Engine 2 → reports
├── reporter.py     # generates 3 HTML reports + history
├── dashboard.py    # web dashboard
└── mcp_client.py   # MongoDB MCP client

queries.txt         # search queries (one per line)
prompt.txt          # Gemini credibility assessment prompt
run.py              # single entry point

reports/            # generated at runtime
├── report_raw.html
├── report_verified.html
├── report_eliminated.html
└── history/        # auto-archived on every run
```

---

## MongoDB collections

| Collection | Contents |
|---|---|
| `raw_queue` | Raw agent findings pending pipeline |
| `safe_traffic` | Verified entries that passed both engines |
| `active_threats` | Eliminated entries with reason |

---

## Author

Yigit Dalkilic
