import os
import requests
from google.adk.agents import Agent

_BASE_URL = os.getenv("NANOGAZE_URL", "https://nanogaze-42024494530.us-central1.run.app")


def run_agent_search() -> dict:
    """Search the web for new content using Gemini and queue it into MongoDB for processing.
    Call this when the user wants to fetch fresh data or populate the pipeline."""
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
        "You are the NanoGaze orchestrator. Your job is to help users run and understand "
        "the hallucination filter pipeline.\n\n"
        "You have three tools:\n"
        "- run_agent_search: searches the web with Gemini and queues findings into MongoDB\n"
        "- run_hallucination_filter: processes the queue through Engine 1 (trust scoring) "
        "and Engine 2 (fact validation), writing verified results to safe_traffic and "
        "eliminated results to active_threats in MongoDB\n"
        "- save_report_to_history: archives the current reports\n\n"
        "When a user asks to run the full pipeline, call run_agent_search first, "
        "then run_hallucination_filter. Always report back what was found: "
        "how many entries were verified vs eliminated and why.\n\n"
        "Be concise and specific — tell the user exactly what the pipeline did."
    ),
    tools=[run_agent_search, run_hallucination_filter, save_report_to_history],
)
