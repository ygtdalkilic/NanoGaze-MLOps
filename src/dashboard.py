import sys
import os
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, os.path.dirname(__file__))

from http.server import HTTPServer, BaseHTTPRequestHandler
import agent
import pipeline
import reporter
import config_store
import research

REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "reports"))
TEMPLATE = Path(__file__).parent.parent / "templates" / "dashboard.html"


def load_reports():
    raw_html = (REPORTS_DIR / "report_raw.html").read_text(encoding="utf-8") if (REPORTS_DIR / "report_raw.html").exists() else "<p>No data yet. Run the pipeline first.</p>"
    verified_html = (REPORTS_DIR / "report_verified.html").read_text(encoding="utf-8") if (REPORTS_DIR / "report_verified.html").exists() else "<p>No data yet.</p>"
    eliminated_html = (REPORTS_DIR / "report_eliminated.html").read_text(encoding="utf-8") if (REPORTS_DIR / "report_eliminated.html").exists() else "<p>No data yet.</p>"
    return raw_html, verified_html, eliminated_html


def extract_table(html: str) -> str:
    import re
    match = re.search(r'<table.*?</table>', html, re.DOTALL)
    return match.group(0) if match else "<p>No table found.</p>"


def extract_subtitle(html: str) -> str:
    import re
    match = re.search(r'<p class="sub">(.*?)</p>', html)
    return match.group(1) if match else ""





class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/run":
            self._run_pipeline()
        elif self.path == "/agent":
            self._run_agent()
        elif self.path == "/save":
            self._save_history()
        elif self.path == "/prompt":
            self._get_config("prompt", agent._load_prompt())
        elif self.path == "/queries":
            self._get_config("queries", agent._queries_file.read_text() if agent._queries_file.exists() else "")
        elif self.path == "/timelimit":
            self._get_config("timelimit", "w")
        elif self.path == "/history":
            self._get_history()
        elif self.path == "/reputation":
            self._json({"domains": research.get_reputation()})
        elif self.path.startswith("/research/stream"):
            sid = self.path.split("id=")[-1] if "id=" in self.path else ""
            self._stream_research(sid)
        else:
            self._serve_dashboard()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        if self.path == "/prompt":
            config_store.save("prompt", body.get("value", ""))
            msg = "Prompt saved to MongoDB"
        elif self.path == "/queries":
            config_store.save("queries", body.get("value", ""))
            msg = "Queries saved to MongoDB"
        elif self.path == "/timelimit":
            config_store.save("timelimit", body.get("value", "w"))
            msg = "Time filter saved"
        elif self.path == "/research":
            goal = body.get("goal", "").strip()
            if not goal:
                self._json({"message": "No goal provided"})
                return
            sid = research.start(goal)
            self._json({"session_id": sid})
            return
        elif self.path == "/research/sync":
            goal = body.get("goal", "").strip()
            if not goal:
                self._json({"error": "No goal provided"})
                return
            self._json(research.run_sync(goal))
            return
        else:
            msg = "Unknown endpoint"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"message": msg}).encode())

    def _serve_dashboard(self):
        raw_html, verified_html, eliminated_html = load_reports()
        raw_count = raw_html.count("<tr>") - 1
        verified_count = verified_html.count("<tr>") - 1
        eliminated_count = eliminated_html.count("<tr>") - 1
        rate = round((verified_count / raw_count) * 100) if raw_count > 0 else 0

        values = {
            "{stat_raw}": str(max(raw_count, 0)),
            "{stat_verified}": str(max(verified_count, 0)),
            "{stat_eliminated}": str(max(eliminated_count, 0)),
            "{stat_rate}": str(rate),
            "{sub_raw}": extract_subtitle(raw_html),
            "{sub_verified}": extract_subtitle(verified_html),
            "{sub_eliminated}": extract_subtitle(eliminated_html),
            "{table_raw}": extract_table(raw_html),
            "{table_verified}": extract_table(verified_html),
            "{table_eliminated}": extract_table(eliminated_html),
        }
        page = TEMPLATE.read_text(encoding="utf-8")
        for k, v in values.items():
            page = page.replace(k, v)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(page.encode("utf-8"))

    def _run_pipeline(self):
        try:
            raw_count, verified_count, eliminated_count = pipeline.run()
            if raw_count == 0:
                msg = "raw_queue is empty — run agent.py first"
            else:
                msg = f"Done — {verified_count} verified, {eliminated_count} eliminated from {raw_count} total"
        except Exception as e:
            msg = f"Error: {e}"

        self._json({"message": msg})

    def _run_agent(self):
        try:
            agent.run()
            msg = "Agent done — queue populated. Click Run Pipeline to process."
        except Exception as e:
            msg = f"Error: {e}"
        self._json({"message": msg})

    def _get_config(self, key: str, default: str):
        self._json({"value": config_store.get(key, default)})

    def _save_history(self):
        dest = reporter.save_to_history()
        msg = f"Saved to history/{dest.name}" if dest else "No reports to save"
        self._json({"message": msg})

    def _json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _get_history(self):
        sessions = research.get_history()
        clean = []
        for s in sessions:
            s.pop("_id", None)
            clean.append(s)
        clean.sort(key=lambda s: s.get("ts", ""), reverse=True)
        self._json({"sessions": clean[:50]})

    def _stream_research(self, sid: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        def send(event):
            try:
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                self.wfile.flush()
            except Exception:
                pass
        research.stream(sid, send)


def run(port=int(os.getenv("DASHBOARD_PORT", "8080"))):
    os.chdir(Path(__file__).parent.parent)
    print(f"[DASHBOARD] Running at http://localhost:{port}")
    HTTPServer(("", port), Handler).serve_forever()


if __name__ == "__main__":
    run()
