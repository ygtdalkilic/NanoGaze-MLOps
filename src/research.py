import asyncio
import json
import os
import queue as qmod
import threading
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import agent
import engine_1
import engine_2
import reporter
from mcp_client import MCPClient

_sessions: dict[str, qmod.Queue] = {}
_current: dict = {}


def _generate_queries(goal: str) -> list[str]:
    prompt = (
        f'The user\'s research goal is:\n"{goal}"\n\n'
        "Generate exactly 4 focused web search queries that find information DIRECTLY answering this goal. "
        "Rules:\n"
        "- Stay tightly on-topic. Do not broaden to related-but-different subjects or tangents.\n"
        "- Reuse the key nouns and specific terminology from the goal in every query.\n"
        "- Make each query distinct (different angle of the same goal), not a reworded duplicate.\n"
        "Return only the 4 queries, one per line, no numbering, no bullets."
    )
    response = agent._client.models.generate_content(model=agent._model, contents=prompt)
    return [l.strip() for l in response.text.splitlines() if l.strip()][:5]


def _analyze(goal: str, text: str) -> dict:
    prompt = (
        f'Research goal: "{goal}"\n\n'
        f"Content to evaluate:\n{text[:1500]}\n\n"
        "First decide if this content is genuinely RELEVANT to the research goal (on-topic and useful for answering it). "
        "Then assess its CREDIBILITY.\n"
        "Respond with exactly these three lines and nothing else:\n"
        "relevant: yes | no\n"
        "credibility: high | medium | low\n"
        "reason: <one short sentence>"
    )
    response = agent._client.models.generate_content(model=agent._model, contents=prompt)
    raw = response.text
    relevant, credibility, reason = True, "unknown", raw
    for line in raw.splitlines():
        low = line.lower().strip()
        if low.startswith("relevant:"):
            relevant = "yes" in low.split(":", 1)[1]
        elif low.startswith("credibility:"):
            credibility = line.split(":", 1)[1].strip()
        elif low.startswith("reason:"):
            reason = line.split(":", 1)[1].strip()
    return {"relevant": relevant, "credibility": credibility, "reason": reason}


_MIN_DOMAINS = int(os.getenv("CORROBORATION_MIN_DOMAINS", "2"))


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def _corroborate(goal: str, docs: list) -> tuple[list, list]:
    listing = "\n\n".join(
        f"[{i + 1}] domain={_domain(d['url'])} | {d['title']}\n{d['body'][:500]}"
        for i, d in enumerate(docs[:12])
    )
    prompt = (
        f'Research goal: "{goal}"\n\n'
        f"Verified sources (each tagged [n] with its domain):\n{listing}\n\n"
        "Extract the key factual findings that answer the goal. For EACH finding, list the source numbers "
        "that explicitly support it. Separately, identify any findings where the sources CONTRADICT each other.\n"
        "Respond ONLY with JSON, no markdown, in this exact shape:\n"
        '{"findings":[{"claim":"<one sentence>","sources":[1,2]}],'
        '"contradictions":[{"claim":"<one sentence describing the disagreement>","sources":[3,4]}]}'
    )
    response = agent._client.models.generate_content(model=agent._model, contents=prompt)
    data = _parse_json(response.text)

    def domains_for(idxs):
        return {_domain(docs[i - 1]["url"]) for i in idxs if isinstance(i, int) and 1 <= i <= len(docs)}

    findings = []
    for f in data.get("findings", []):
        idxs = [i for i in f.get("sources", []) if isinstance(i, int) and 1 <= i <= len(docs)]
        doms = domains_for(idxs)
        findings.append({
            "claim": f.get("claim", "").strip(),
            "support": len(doms),
            "corroborated": len(doms) >= _MIN_DOMAINS,
            "urls": [docs[i - 1]["url"] for i in idxs],
        })
    contradictions = [c.get("claim", "").strip() for c in data.get("contradictions", []) if c.get("claim")]
    return [f for f in findings if f["claim"]], contradictions


def _confidence(findings: list) -> str:
    if not findings:
        return "low"
    ratio = sum(1 for f in findings if f["corroborated"]) / len(findings)
    return "high" if ratio >= 0.6 else "medium" if ratio >= 0.3 else "low"


def _format_brief(goal: str, findings: list, contradictions: list) -> str:
    if not findings:
        return "No corroborated findings could be extracted from the verified sources."
    lines = [f"Confidence: {_confidence(findings).upper()} (based on cross-source corroboration)\n", "Key findings:"]
    for f in findings:
        tag = f"corroborated by {f['support']} independent sources" if f["corroborated"] else f"single-source ({f['support']})"
        lines.append(f"- {f['claim']}  [{tag}]")
    if contradictions:
        lines.append("\nConflicting claims (sources disagree):")
        for c in contradictions:
            lines.append(f"- {c}")
    return "\n".join(lines)


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def _aggregate_reputation(scored_docs: list) -> dict:
    agg: dict[str, dict] = {}
    for d in scored_docs:
        domain = _domain(d.get("url", ""))
        if not domain:
            continue
        cred = d.get("llm_analysis", {}).get("credibility", "unknown")
        a = agg.setdefault(domain, {"seen": 0, "high": 0, "medium": 0, "low": 0, "trust_sum": 0.0})
        a["seen"] += 1
        if cred in ("high", "medium", "low"):
            a[cred] += 1
        a["trust_sum"] += d.get("trust_score", 0)
    return agg


async def _run(goal: str, emit) -> dict:
    from ddgs import DDGS

    emit({"type": "progress", "msg": "Analyzing research goal with Gemini..."})
    queries = _generate_queries(goal)
    emit({"type": "queries", "msg": f"Generated {len(queries)} targeted queries", "queries": queries})

    timelimit = agent._load_timelimit()
    docs = []

    async with MCPClient() as mcp:
        with DDGS() as ddgs:
            for i, query in enumerate(queries):
                emit({"type": "search", "msg": f"Searching: {query}", "step": i + 1, "total": len(queries)})
                try:
                    results = list(ddgs.text(query, max_results=5, timelimit=timelimit))
                except Exception:
                    emit({"type": "progress", "msg": f"Search failed for: {query}"})
                    continue

                for r in results:
                    body = f"{r.get('title', '')} {r.get('body', '')}"
                    a = _analyze(goal, body)
                    if not a["relevant"]:
                        emit({"type": "result", "msg": f"{r.get('title', '')[:55]} → off-topic, skipped", "credibility": "low"})
                        continue
                    docs.append({
                        "source": "duckduckgo",
                        "query": query,
                        "url": r.get("href", ""),
                        "title": r.get("title", ""),
                        "body": r.get("body", ""),
                        "signals": agent._extract_signals(body),
                        "llm_analysis": {"credibility": a["credibility"], "reason": a["reason"]},
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "processed": True,
                    })
                    emit({"type": "result", "msg": f"{r.get('title', '')[:60]} → {a['credibility']}", "credibility": a["credibility"]})

        if not docs:
            empty = {"goal": goal, "queries": queries, "brief": "No search results were found. Try broadening your goal or changing the time filter.", "sources": [], "stats": {"total": 0, "verified": 0, "eliminated": 0}, "ts": datetime.now(timezone.utc).isoformat()}
            _current["session"] = empty
            _current["reputation"] = {}
            _current["saved"] = False
            emit({"type": "done", "msg": "No results found", "session": empty})
            return {}

        memory = {}
        for rec in await mcp.find_all("domain_reputation"):
            seen = rec.get("seen", 0)
            if seen:
                memory[rec["domain"]] = {"seen": seen, "avg_trust": round(rec.get("trust_sum", 0) / seen, 1)}

        emit({"type": "engine", "msg": f"Engine 1 — trust scoring {len(docs)} sources (using {len(memory)} learned domains)..."})
        e1_verified, e1_eliminated = engine_1.run(docs, memory)
        emit({"type": "engine", "msg": f"Engine 1 — {len(e1_verified)} passed, {len(e1_eliminated)} filtered (low trust)"})

        emit({"type": "engine", "msg": f"Engine 2 — fact-validating {len(e1_verified)} sources (IPs, URLs, consistency)..."})
        e2_verified, e2_eliminated = engine_2.run(e1_verified)
        emit({"type": "engine", "msg": f"Engine 2 — {len(e2_verified)} verified, {len(e2_eliminated)} eliminated (failed validation)"})

        for e in e1_eliminated:
            e["eliminated_by"] = "engine_1"
        for e in e2_eliminated:
            e["eliminated_by"] = "engine_2"
        all_eliminated = e1_eliminated + e2_eliminated

        emit({"type": "progress", "msg": "Writing this run's results to MongoDB (replacing previous)..."})
        await mcp.delete_all("safe_traffic")
        await mcp.delete_all("active_threats")
        if e2_verified:
            await mcp.insert_many("safe_traffic", e2_verified)
        if all_eliminated:
            await mcp.insert_many("active_threats", all_eliminated)

        reporter.generate(docs, e2_verified, all_eliminated)

        if e2_verified:
            emit({"type": "progress", "msg": "Cross-checking claims across independent sources..."})
            findings, contradictions = _corroborate(goal, e2_verified)
            brief = _format_brief(goal, findings, contradictions)
            corr = sum(1 for f in findings if f["corroborated"])
            emit({"type": "progress", "msg": f"Corroboration — {corr}/{len(findings)} findings backed by ≥{_MIN_DOMAINS} independent sources"})
        else:
            findings, contradictions = [], []
            brief = "No sources survived the dual-engine filter. Every result was flagged as low-trust or failed fact validation. Try broadening your goal or changing the time filter."

        session = {
            "goal": goal,
            "queries": queries,
            "brief": brief,
            "findings": findings,
            "contradictions": contradictions,
            "confidence": _confidence(findings),
            "sources": [
                {"url": d["url"], "title": d["title"], "credibility": d.get("llm_analysis", {}).get("credibility", "unknown"), "trust_score": d.get("trust_score", 0)}
                for d in e2_verified
            ],
            "stats": {"total": len(docs), "verified": len(e2_verified), "eliminated": len(all_eliminated)},
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        _current["session"] = session
        _current["reputation"] = _aggregate_reputation(e1_verified + e1_eliminated)
        _current["saved"] = False
        emit({"type": "done", "msg": "Research complete — click Save to History to keep it", "session": session})

    return session


def _drive(goal: str, emit):
    try:
        asyncio.run(_run(goal, emit))
    except BaseExceptionGroup as eg:
        real = [e for e in eg.exceptions if not isinstance(e, (GeneratorExit, RuntimeError))]
        emit({"type": "error", "msg": str(real[0]) if real else "Unknown error"})
    except Exception as e:
        emit({"type": "error", "msg": str(e)})


def start(goal: str) -> str:
    sid = str(uuid.uuid4())
    q: qmod.Queue = qmod.Queue()
    _sessions[sid] = q
    threading.Thread(target=lambda: _drive(goal, q.put), daemon=True).start()
    return sid


def stream(sid: str, send):
    q = _sessions.get(sid)
    if not q:
        send({"type": "error", "msg": "Session not found"})
        return
    while True:
        try:
            event = q.get(timeout=120)
            send(event)
            if event.get("type") in ("done", "error"):
                _sessions.pop(sid, None)
                break
        except qmod.Empty:
            send({"type": "ping"})


def run_sync(goal: str) -> dict:
    result = {}

    def capture(event):
        if event.get("type") == "done":
            result["session"] = event.get("session", {})
        elif event.get("type") == "error":
            result["error"] = event.get("msg", "Unknown error")

    _drive(goal, capture)
    return result.get("session") or {"error": result.get("error", "Research failed")}


async def _save(session: dict, reputation: dict) -> None:
    async with MCPClient() as mcp:
        await mcp.insert_many("research_sessions", [session])
        for domain, a in reputation.items():
            await mcp.upsert("domain_reputation", {"domain": domain}, {
                "$inc": {"seen": a["seen"], "high": a["high"], "medium": a["medium"], "low": a["low"], "trust_sum": a["trust_sum"]},
                "$set": {"last_seen": datetime.now(timezone.utc).isoformat()},
            })


def save_current() -> dict:
    if not _current.get("session"):
        return {"message": "No research to save — run one first"}
    if _current.get("saved"):
        return {"message": "Already saved to history"}
    try:
        asyncio.run(_save(_current["session"], _current.get("reputation", {})))
    except BaseExceptionGroup as eg:
        real = [e for e in eg.exceptions if not isinstance(e, (GeneratorExit, RuntimeError))]
        if real:
            return {"message": f"Error saving: {real[0]}"}
    _current["saved"] = True
    return {"message": "Saved to history"}


async def _get_collection(name: str) -> list:
    try:
        async with MCPClient() as mcp:
            return await mcp.find_all(name)
    except Exception:
        return []


def _fetch(name: str) -> list:
    try:
        return asyncio.run(_get_collection(name))
    except BaseExceptionGroup as eg:
        real = [e for e in eg.exceptions if not isinstance(e, (GeneratorExit, RuntimeError))]
        if real:
            raise real[0]
        return []


def get_history() -> list:
    return _fetch("research_sessions")


def get_reputation() -> list:
    rows = _fetch("domain_reputation")
    for r in rows:
        seen = r.get("seen", 0) or 1
        r["avg_trust"] = round(r.get("trust_sum", 0) / seen, 1)
    rows.sort(key=lambda r: (r.get("avg_trust", 0), r.get("seen", 0)), reverse=True)
    return rows
