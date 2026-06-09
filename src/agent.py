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

_api_key = os.getenv("GEMINI_API_KEY")
if _api_key:
    _client = genai.Client(api_key=_api_key)
else:
    _client = genai.Client(http_options=HttpOptions(api_version="v1"))

_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_max_results = int(os.getenv("AGENT_MAX_RESULTS", "5"))

_queries_file = Path(os.getenv("QUERIES_FILE", Path(__file__).parent.parent / "queries.txt"))
SEARCH_QUERIES = [l.strip() for l in _queries_file.read_text().splitlines() if l.strip()]

_prompt_file = Path(os.getenv("PROMPT_FILE", Path(__file__).parent.parent / "prompt.txt"))
_prompt_template = _prompt_file.read_text()

IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
STAT_PATTERN = re.compile(r'\b\d+(?:\.\d+)?%|\$\d[\d,.]*[BMK]?\b')


def analyze_with_llm(text: str) -> dict:
    max_chars = int(os.getenv("AGENT_MAX_CHARS", "1000"))
    prompt = _prompt_template.format(text=text[:max_chars])
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


async def _run(max_results_per_query=_max_results):
    total = 0
    async with MCPClient() as mcp:
        with DDGS() as ddgs:
            for query in SEARCH_QUERIES:
                print(f"[AGENT] Searching: {query}")
                try:
                    results = list(ddgs.text(query, max_results=max_results_per_query))
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
    asyncio.run(_run(max_results_per_query))


if __name__ == "__main__":
    run()
