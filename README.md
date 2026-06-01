# NanoGaze MLOps

An MLOps pipeline that solves LLM hallucination. A local AI agent searches the internet and dumps findings — the dual-engine architecture fact-checks and filters that dump so only verified, trustworthy data survives.

---

## The Problem

LLMs hallucinate. When an AI agent searches and reports findings, it may produce fake IPs, made-up CVE numbers, wrong threat levels, or fabricated claims. You can't trust the raw output. NanoGaze filters it.

---

## How it works

```
Phi-3 Mini (Ollama) — searches internet, dumps findings
        │
        ▼
MongoDB: raw_queue        ← raw AI findings
        │
        ▼
Engine 1 — noise filter (trust scoring, 5 metrics)
        │   scores every entry 0–100%
        │   threshold: 50% — below = eliminated
        │
        ▼
Engine 2 — fact validator
        │   cross-checks CVEs against NVD
        │   validates IPs (public vs private/hallucinated)
        │   checks URL reachability
        │   flags threat level inconsistencies
        │
   ┌────┴────┐
   ▼         ▼
Verified   Eliminated (with reason)
        │
        ▼
Dashboard (localhost:8080)
├── Raw Report       — everything the LLM found
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

Criteria are **auto-detected from the data itself** — no hardcoded rules. Works for any domain.

---

## Engine 2 — Fact Validation

| Check | What it does |
|---|---|
| CVE validation | Queries NVD API to verify CVE IDs exist |
| IP validation | Flags entries with only private/loopback IPs |
| URL reachability | Checks source URL returns a valid response |
| Threat consistency | Flags "high" threat claims with zero supporting signals |

---

## Stack

| Layer | Technology |
|---|---|
| AI Agent | DuckDuckGo Search + Ollama Phi-3 Mini |
| Engine 1 | Custom trust scoring (auto-detected criteria) |
| Engine 2 | NVD API + IP/URL validation |
| Database | MongoDB Atlas |
| Dashboard | Python HTTP server (localhost:8080) |
| Automation | GitHub Actions (manual trigger) |

---

## What you need

- Python 3.13+
- [Ollama](https://ollama.com) with `phi3:mini` pulled
- MongoDB Atlas free cluster
- `pip install -r requirements.txt`

---

## Getting started

```bash
git clone https://github.com/ygtdalkilic/NanoGaze-MLOps.git
cd NanoGaze-MLOps
pip install -r requirements.txt
```

```powershell
ollama pull phi3:mini
$env:MONGO_URI = "mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/"
```

---

## Run

**1. Run the AI agent** (searches internet, queues findings into MongoDB):
```powershell
& ".venv\Scripts\python.exe" src\agent.py
```

**2. Launch the dashboard** (runs both engines, shows reports):
```powershell
& ".venv\Scripts\python.exe" src\dashboard.py
```
Then open `http://localhost:8080` and click **Run Pipeline**.

---

## Project layout

```
src/
├── agent.py       # AI agent — DuckDuckGo + Phi-3 Mini
├── engine_1.py    # noise filter (trust scoring, auto-detected criteria)
├── engine_2.py    # fact validator (CVE, IP, URL, threat consistency)
├── pipeline.py    # orchestrator — Engine 1 → Engine 2 → reports
├── reporter.py    # generates 3 HTML reports
├── dashboard.py   # localhost:8080 dashboard
└── db_manager.py  # MongoDB connection

reports/           # generated at runtime (gitignored)
├── report_raw.html
├── report_verified.html
└── report_eliminated.html
```

---

## MongoDB collections

| Collection | Contents |
|---|---|
| `raw_queue` | Raw AI agent findings, pending pipeline |
| `safe_traffic` | Reserved |
| `active_threats` | Reserved |

---

## Author

Yigit Dalkilic
