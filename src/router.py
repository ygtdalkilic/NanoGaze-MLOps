import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

PENDING_PATH = "data/pending_analysis.json"


def route_to_cloud_agent(anomalous_log: str, context_logs: list[str]):
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "anomaly": anomalous_log,
        "context": context_logs,
    }

    endpoint = os.getenv("CLOUD_AGENT_ENDPOINT")
    if endpoint:
        try:
            resp = requests.post(endpoint, json=payload, timeout=10)
            resp.raise_for_status()
            print(f"[ROUTER] Sent to cloud — status {resp.status_code}")
        except requests.exceptions.Timeout:
            print("[ROUTER] Cloud endpoint timed out — writing to pending file.")
            _write_pending(payload)
        except requests.exceptions.ConnectionError:
            print("[ROUTER] Cloud endpoint unreachable — writing to pending file.")
            _write_pending(payload)
        except requests.exceptions.HTTPError as e:
            print(f"[ROUTER] Cloud returned error: {e} — writing to pending file.")
            _write_pending(payload)
    else:
        print("[ROUTER] CLOUD_AGENT_ENDPOINT not set — writing to pending file.")
        _write_pending(payload)


def _write_pending(payload: dict):
    path = Path(PENDING_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError:
            existing = []
    existing.append(payload)
    path.write_text(json.dumps(existing, indent=2))
