import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "reports"))
HISTORY_DIR = REPORTS_DIR / "history"

REPORT_FILES = ["report_raw.html", "report_verified.html", "report_eliminated.html"]


def save_to_history():
    if not any((REPORTS_DIR / f).exists() for f in REPORT_FILES):
        return None
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    dest = HISTORY_DIR / ts
    dest.mkdir(parents=True, exist_ok=True)
    for f in REPORT_FILES:
        src = REPORTS_DIR / f
        if src.exists():
            shutil.copy2(src, dest / f)
    return dest


def _trust_color(score: float) -> str:
    if score >= 75:
        return "#2ecc71"
    if score >= 50:
        return "#f39c12"
    return "#e74c3c"


def _scores_breakdown(entry: dict) -> str:
    scores = entry.get("scores", {})
    return " | ".join(f"{k}: {v}%" for k, v in scores.items())


def _table_rows(entries: list[dict], show_scores: bool = True) -> str:
    rows = []
    for e in entries:
        score = e.get("trust_score", 0)
        color = _trust_color(score)
        breakdown = _scores_breakdown(e) if show_scores else ""
        row = f"""
        <tr>
            <td>{e.get("title", "-")}</td>
            <td><a href="{e.get("url", "#")}" target="_blank">{e.get("url", "-")[:60]}...</a></td>
            <td>{e.get("body", "-")[:150]}...</td>
            <td style="color:{color}; font-weight:bold;">{score}%</td>
            {"<td>" + breakdown + "</td>" if show_scores else ""}
        </tr>"""
        rows.append(row)
    return "\n".join(rows)


def _eliminated_rows(entries: list[dict]) -> str:
    rows = []
    for e in entries:
        score = e.get("trust_score", 0)
        breakdown = _scores_breakdown(e)
        if e.get("eliminated_by") == "engine_2":
            fc = e.get("fact_check", {})
            details = fc.get("details", {})
            reason = "Engine 2 — " + "; ".join(details.values()) if details else "Engine 2 — Credibility check failed"
        else:
            low = [k for k, v in e.get("scores", {}).items() if v < 50]
            reason = f"Engine 1 — Low scores in: {', '.join(low)}" if low else "Engine 1 — Below threshold"
        row = f"""
        <tr>
            <td>{e.get("title", "-")}</td>
            <td><a href="{e.get("url", "#")}" target="_blank">{e.get("url", "-")[:60]}...</a></td>
            <td style="color:#e74c3c; font-weight:bold;">{score}%</td>
            <td>{reason}</td>
            <td>{breakdown}</td>
        </tr>"""
        rows.append(row)
    return "\n".join(rows)


def _html(title: str, subtitle: str, headers: list[str], body: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    headers_html = "".join(f"<th>{h}</th>" for h in headers)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 40px; background: #f9f9f9; color: #222; }}
  h1 {{ color: #2c3e50; }}
  p.sub {{ color: #666; margin-top: -10px; }}
  table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }}
  th {{ background: #2c3e50; color: white; padding: 12px 16px; text-align: left; }}
  td {{ padding: 10px 16px; border-bottom: 1px solid #eee; vertical-align: top; font-size: 13px; }}
  tr:hover {{ background: #f0f4f8; }}
  a {{ color: #2980b9; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="sub">{subtitle} — Generated {ts}</p>
<table>
  <thead><tr>{headers_html}</tr></thead>
  <tbody>{body}</tbody>
</table>
</body>
</html>"""


def generate(raw: list[dict], verified: list[dict], eliminated: list[dict]):
    REPORTS_DIR.mkdir(exist_ok=True)
    for f in REPORT_FILES:
        (REPORTS_DIR / f).unlink(missing_ok=True)

    Path(REPORTS_DIR / "report_raw.html").write_text(_html(
        "Raw Report",
        f"{len(raw)} total entries — unfiltered LLM dump",
        ["Title", "URL", "Body", "Trust Score", "Score Breakdown"],
        _table_rows(raw, show_scores=True)
    ), encoding="utf-8")

    Path(REPORTS_DIR / "report_verified.html").write_text(_html(
        "Verified Report",
        f"{len(verified)} entries passed the trust threshold (≥50%)",
        ["Title", "URL", "Body", "Trust Score", "Score Breakdown"],
        _table_rows(verified, show_scores=True)
    ), encoding="utf-8")

    Path(REPORTS_DIR / "report_eliminated.html").write_text(_html(
        "Eliminated Report",
        f"{len(eliminated)} entries removed — below 50% trust score",
        ["Title", "URL", "Trust Score", "Reason", "Score Breakdown"],
        _eliminated_rows(eliminated)
    ), encoding="utf-8")

    dest = save_to_history()
    print(f"[REPORT] Raw: {len(raw)} | Verified: {len(verified)} | Eliminated: {len(eliminated)}")
    print(f"[REPORT] Saved to {REPORTS_DIR.resolve()} | History: {dest}")
