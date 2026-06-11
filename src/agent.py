import asyncio
import re
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from google import genai
from google.genai.types import HttpOptions
from ddgs import DDGS

sys.path.insert(0, os.path.dirname(__file__))
from mcp_client import MCPClient
import config_store

_api_key = os.getenv("GEMINI_API_KEY")
if _api_key:
    _client = genai.Client(api_key=_api_key)
else:
    _client = genai.Client(http_options=HttpOptions(api_version="v1"))

_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_max_results = int(os.getenv("AGENT_MAX_RESULTS", "5"))

_queries_file = Path(os.getenv("QUERIES_FILE", Path(__file__).parent.parent / "queries.txt"))
_prompt_file = Path(os.getenv("PROMPT_FILE", Path(__file__).parent.parent / "prompt.txt"))

IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
STAT_PATTERN = re.compile(r'\b\d+(?:\.\d+)?%|\$\d[\d,.]*[BMK]?\b')


def _load_prompt() -> str:
    default = _prompt_file.read_text() if _prompt_file.exists() else ""
    return config_store.get("prompt", default)


def _load_queries() -> list[str]:
    default = _queries_file.read_text() if _queries_file.exists() else ""
    raw = config_store.get("queries", default)
    return [l.strip() for l in raw.splitlines() if l.strip()]


def analyze_with_llm(text: str) -> dict:
    max_chars = int(os.getenv("AGENT_MAX_CHARS", "1000"))
    prompt = _load_prompt().format(text=text[:max_chars])
    response = _client.models.generate_content(model=_model, contents=prompt)
    raw = response.text
    credibility = "unknown"
    reason = raw
    for line in raw.splitlines():
        if line.lower().startswith("credibility:"):
            credibility = line.split(":", 1)[1].strip()
        elif line.lower().startswith("reason:"):
            reason = line.split(":", 1)[1].strip()
    return {"credibility": credibility, "reason": reason}


def _extract_signals(text: str) -> dict:
    return {
        "ips": IP_PATTERN.findall(text),
        "statistics": STAT_PATTERN.findall(text),
        "length": len(text),
        "has_claims": any(w in text.lower() for w in ["according to", "study shows", "researchers found", "data shows", "report says"]),
    }


_TIMELIMIT_LABELS = {"d": "past 24h", "w": "past week", "m": "past month", "y": "past year", "": "all time"}


def _load_timelimit() -> str | None:
    val = config_store.get("timelimit", "w")
    return val if val in ("d", "w", "m", "y") else None


async def _run(max_results_per_query=_max_results):
    queries = _load_queries()
    timelimit = _load_timelimit()
    label = _TIMELIMIT_LABELS.get(timelimit or "", "all time")
    print(f"[AGENT] Time filter: {label}")
    total = 0
    async with MCPClient() as mcp:
        with DDGS() as ddgs:
            for query in queries:
                print(f"[AGENT] Searching: {query}")
                try:
                    results = list(ddgs.text(query, max_results=max_results_per_query, timelimit=timelimit))
                except Exception as e:
                    print(f"[AGENT] Search failed for '{query}': {e}")
                    continue

                docs = []
                for r in results:
                    body = f"{r.get('title', '')} {r.get('body', '')}"
                    llm = analyze_with_llm(body)
                    print(f"[AGENT] {r.get('title', '')[:60]} → credibility={llm['credibility']}")
                    docs.append({
                        "source": "duckduckgo",
                        "query": query,
                        "url": r.get("href", ""),
                        "title": r.get("title", ""),
                        "body": r.get("body", ""),
                        "signals": _extract_signals(body),
                        "llm_analysis": llm,
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "processed": False,
                    })

                if docs:
                    await mcp.insert_many("raw_queue", docs)
                    total += len(docs)
                    print(f"[AGENT] Dumped {len(docs)} results into raw_queue")

    print(f"[AGENT] Done. Total documents queued: {total}")


def run(max_results_per_query=_max_results):
    try:
        asyncio.run(_run(max_results_per_query))
    except BaseExceptionGroup as eg:
        real = [e for e in eg.exceptions if not isinstance(e, (GeneratorExit, RuntimeError))]
        if real:
            raise real[0]


if __name__ == "__main__":
    run()
