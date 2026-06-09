import sys
import os
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, os.path.dirname(__file__))

from http.server import HTTPServer, BaseHTTPRequestHandler
import pipeline
import reporter

REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "reports"))


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


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>NanoGaze MLOps Dashboard</title>
<style>
  :root {{
    --black: #0a0a0a;
    --dark: #111111;
    --card: #1a1a1a;
    --border: #2a2a2a;
    --yellow: #f5c518;
    --yellow-dim: #c9a614;
    --yellow-glow: rgba(245, 197, 24, 0.15);
    --text: #e8e8e8;
    --muted: #888;
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    background: var(--black);
    color: var(--text);
    font-family: 'Segoe UI', Arial, sans-serif;
    min-height: 100vh;
  }}

  header {{
    background: var(--dark);
    border-bottom: 2px solid var(--yellow);
    padding: 24px 40px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}

  header h1 {{
    font-size: 24px;
    color: var(--yellow);
    letter-spacing: 2px;
    text-transform: uppercase;
  }}

  header span {{
    color: var(--muted);
    font-size: 13px;
  }}

  .stats {{
    display: flex;
    gap: 16px;
    padding: 24px 40px;
    background: var(--dark);
    border-bottom: 1px solid var(--border);
  }}

  .stat-card {{
    flex: 1;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    text-align: center;
    transition: border-color 0.2s;
  }}

  .stat-card:hover {{ border-color: var(--yellow); }}

  .stat-card .number {{
    font-size: 32px;
    font-weight: bold;
    color: var(--yellow);
  }}

  .stat-card .label {{
    font-size: 12px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 4px;
  }}

  .tabs {{
    display: flex;
    gap: 0;
    padding: 24px 40px 0;
    border-bottom: 2px solid var(--border);
  }}

  .tab {{
    padding: 12px 28px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    transition: all 0.2s;
    background: none;
    border-top: none;
    border-left: none;
    border-right: none;
  }}

  .tab:hover {{ color: var(--yellow); }}
  .tab.active {{ color: var(--yellow); border-bottom: 2px solid var(--yellow); }}

  .content {{
    padding: 32px 40px;
  }}

  .panel {{ display: none; }}
  .panel.active {{ display: block; }}

  .panel-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
  }}

  .panel-header h2 {{
    font-size: 18px;
    color: var(--yellow);
  }}

  .panel-header p {{
    color: var(--muted);
    font-size: 13px;
  }}

  .run-btn {{
    background: var(--yellow);
    color: var(--black);
    border: none;
    padding: 10px 24px;
    font-weight: bold;
    font-size: 13px;
    border-radius: 6px;
    cursor: pointer;
    letter-spacing: 1px;
    text-transform: uppercase;
    transition: background 0.2s;
  }}

  .run-btn:hover {{ background: var(--yellow-dim); }}
  .run-btn:disabled {{ background: #444; color: #888; cursor: not-allowed; }}

  .table-wrap {{
    overflow-x: auto;
    border-radius: 8px;
    border: 1px solid var(--border);
  }}

  table {{
    border-collapse: collapse;
    width: 100%;
    background: var(--card);
  }}

  th {{
    background: #1e1e1e;
    color: var(--yellow);
    padding: 12px 16px;
    text-align: left;
    font-size: 12px;
    letter-spacing: 1px;
    text-transform: uppercase;
    border-bottom: 2px solid var(--yellow);
  }}

  td {{
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
    color: var(--text);
    vertical-align: top;
  }}

  tr:hover td {{ background: var(--yellow-glow); }}

  a {{ color: var(--yellow); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  .toast {{
    position: fixed;
    bottom: 32px;
    right: 32px;
    background: var(--yellow);
    color: var(--black);
    padding: 12px 24px;
    border-radius: 6px;
    font-weight: bold;
    font-size: 13px;
    display: none;
    z-index: 999;
  }}
</style>
</head>
<body>

<header>
  <h1>&#9650; NanoGaze MLOps</h1>
  <span>MLOps Hallucination Filter Pipeline</span>
</header>

<div class="stats">
  <div class="stat-card">
    <div class="number" id="stat-raw">{stat_raw}</div>
    <div class="label">Total Entries</div>
  </div>
  <div class="stat-card">
    <div class="number" id="stat-verified" style="color:#2ecc71">{stat_verified}</div>
    <div class="label">Verified</div>
  </div>
  <div class="stat-card">
    <div class="number" id="stat-eliminated" style="color:#e74c3c">{stat_eliminated}</div>
    <div class="label">Eliminated</div>
  </div>
  <div class="stat-card">
    <div class="number" id="stat-rate">{stat_rate}%</div>
    <div class="label">Pass Rate</div>
  </div>
</div>

<div class="tabs">
  <button class="tab active" onclick="showTab('raw', this)">Raw Data</button>
  <button class="tab" onclick="showTab('verified', this)">Verified</button>
  <button class="tab" onclick="showTab('eliminated', this)">Eliminated</button>
</div>

<div class="content">
  <div class="panel active" id="panel-raw">
    <div class="panel-header">
      <div>
        <h2>Raw Dump</h2>
        <p>{sub_raw}</p>
      </div>
      <div style="display:flex;gap:10px;">
        <button class="run-btn" onclick="runPipeline(this)">Run Pipeline</button>
        <button class="run-btn" style="background:var(--card);color:var(--yellow);border:1px solid var(--yellow);" onclick="saveHistory(this)">Save to History</button>
      </div>
    </div>
    <div class="table-wrap">{table_raw}</div>
  </div>

  <div class="panel" id="panel-verified">
    <div class="panel-header">
      <div>
        <h2>Verified Entries</h2>
        <p>{sub_verified}</p>
      </div>
    </div>
    <div class="table-wrap">{table_verified}</div>
  </div>

  <div class="panel" id="panel-eliminated">
    <div class="panel-header">
      <div>
        <h2>Eliminated Entries</h2>
        <p>{sub_eliminated}</p>
      </div>
    </div>
    <div class="table-wrap">{table_eliminated}</div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
  function showTab(name, el) {{
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById('panel-' + name).classList.add('active');
    el.classList.add('active');
  }}

  function runPipeline(btn) {{
    btn.disabled = true;
    btn.textContent = 'Running...';
    fetch('/run').then(r => r.json()).then(data => {{
      showToast(data.message + ' — reloading...');
      setTimeout(() => location.reload(), 2000);
    }}).catch(() => {{
      showToast('Error running pipeline');
      btn.disabled = false;
      btn.textContent = 'Run Pipeline';
    }});
  }}

  function saveHistory(btn) {{
    btn.disabled = true;
    btn.textContent = 'Saving...';
    fetch('/save').then(r => r.json()).then(data => {{
      showToast(data.message);
      btn.disabled = false;
      btn.textContent = 'Save to History';
    }}).catch(() => {{
      showToast('Error saving');
      btn.disabled = false;
      btn.textContent = 'Save to History';
    }});
  }}

  function showToast(msg) {{
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.style.display = 'block';
    setTimeout(() => t.style.display = 'none', 4000);
  }}
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/run":
            self._run_pipeline()
        elif self.path == "/save":
            self._save_history()
        else:
            self._serve_dashboard()

    def _serve_dashboard(self):
        raw_html, verified_html, eliminated_html = load_reports()
        raw_count = raw_html.count("<tr>") - 1
        verified_count = verified_html.count("<tr>") - 1
        eliminated_count = eliminated_html.count("<tr>") - 1
        rate = round((verified_count / raw_count) * 100) if raw_count > 0 else 0

        page = DASHBOARD_HTML.format(
            stat_raw=max(raw_count, 0),
            stat_verified=max(verified_count, 0),
            stat_eliminated=max(eliminated_count, 0),
            stat_rate=rate,
            sub_raw=extract_subtitle(raw_html),
            sub_verified=extract_subtitle(verified_html),
            sub_eliminated=extract_subtitle(eliminated_html),
            table_raw=extract_table(raw_html),
            table_verified=extract_table(verified_html),
            table_eliminated=extract_table(eliminated_html),
        )
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

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"message": msg}).encode())

    def _save_history(self):
        dest = reporter.save_to_history()
        msg = f"Saved to history/{dest.name}" if dest else "No reports to save"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"message": msg}).encode())


def run(port=int(os.getenv("DASHBOARD_PORT", "8080"))):
    os.chdir(Path(__file__).parent.parent)
    print(f"[DASHBOARD] Running at http://localhost:{port}")
    HTTPServer(("", port), Handler).serve_forever()


if __name__ == "__main__":
    run()
