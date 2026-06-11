import os
import requests
from google.adk.agents import Agent

_BASE_URL = os.getenv("NANOGAZE_URL", "https://nanogaze-42024494530.us-central1.run.app")


def run_research(goal: str) -> dict:
    """Run a full verified-research mission for a user's goal. This is the primary tool.
    Gemini generates targeted search queries, searches the web, runs every source through a
    dual-engine hallucination filter (Engine 1 trust scoring, Engine 2 fact validation), and
    synthesizes a research brief from only the verified sources. Everything is stored in MongoDB.
    Returns the brief, verified sources with trust scores, and verified/eliminated counts.
    Call this whenever the user asks a research question or wants verified information on a topic."""
    try:
        resp = requests.post(f"{_BASE_URL}/research/sync", json={"goal": goal}, timeout=600)
        return resp.json()
    except Exception as e:
        return {"message": f"Error: {e}"}


def run_agent_search() -> dict:
    """Search the web with Gemini and queue findings into MongoDB without filtering.
    Lower-level than run_research. Call this only when the user explicitly wants to fetch
    raw data without running the full filter-and-synthesize mission."""
    try:
        resp = requests.get(f"{_BASE_URL}/agent", timeout=300)
        return resp.json()
    except Exception as e:
        return {"message": f"Error: {e}"}


def run_hallucination_filter() -> dict:
    """Run the dual-engine hallucination filter pipeline over queued MongoDB data.
    Engine 1 scores trust, Engine 2 validates facts. Returns verified vs eliminated counts.
    Call this after run_agent_search, or when the user wants to process existing queued data."""
    try:
        resp = requests.get(f"{_BASE_URL}/run", timeout=300)
        return resp.json()
    except Exception as e:
        return {"message": f"Error: {e}"}


def save_report_to_history() -> dict:
    """Save the current pipeline reports to the history archive in MongoDB.
    Call this when the user wants to preserve the current results."""
    try:
        resp = requests.get(f"{_BASE_URL}/save", timeout=30)
        return resp.json()
    except Exception as e:
        return {"message": f"Error: {e}"}


root_agent = Agent(
    name="nanogaze_agent",
    model="gemini-2.5-flash",
    description=(
        "NanoGaze MLOps agent — filters hallucinations from web search results "
        "using a dual-engine pipeline backed by MongoDB Atlas."
    ),
    instruction=(
        "You are the NanoGaze orchestrator. You help users get verified, hallucination-free "
        "answers to research questions.\n\n"
        "Your primary tool is run_research(goal): given a research goal, it generates search "
        "queries, searches the web, filters every source through Engine 1 (trust scoring) and "
        "Engine 2 (fact validation), and synthesizes a brief from only the verified sources — "
        "all stored in MongoDB. Use this for almost every request.\n\n"
        "Lower-level tools, only when explicitly asked:\n"
        "- run_agent_search: queue raw findings without filtering\n"
        "- run_hallucination_filter: process whatever is already queued\n"
        "- save_report_to_history: archive current reports\n\n"
        "When a user asks anything researchable, call run_research with a clear goal. Then "
        "report the brief, how many sources were verified vs eliminated, and cite the verified "
        "source URLs. Be concise and specific."
    ),
    tools=[run_research, run_agent_search, run_hallucination_filter, save_report_to_history],
)
