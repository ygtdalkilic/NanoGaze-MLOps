import re
import time
import requests

CVE_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"
CVE_PATTERN = re.compile(r'CVE-\d{4}-\d+', re.IGNORECASE)
IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')

_cve_cache: dict[str, bool] = {}


def _is_public_ip(ip: str) -> bool:
    try:
        parts = [int(p) for p in ip.split(".")]
        if len(parts) != 4 or any(p > 255 for p in parts):
            return False
        a, b = parts[0], parts[1]
        if a in (0, 10, 127):
            return False
        if a == 172 and 16 <= b <= 31:
            return False
        if a == 192 and b == 168:
            return False
        if a in (169, 240, 255):
            return False
        return True
    except Exception:
        return False


def _check_cve(cve_id: str) -> bool:
    cve_id = cve_id.upper()
    if cve_id in _cve_cache:
        return _cve_cache[cve_id]
    try:
        resp = requests.get(CVE_API, params={"cveId": cve_id}, timeout=8)
        exists = resp.json().get("totalResults", 0) > 0
    except Exception:
        exists = True  # inconclusive — don't penalize
    _cve_cache[cve_id] = exists
    time.sleep(0.7)  # NVD: 5 req/30s without API key
    return exists


def _check_url(url: str) -> bool:
    try:
        resp = requests.head(url, timeout=6, allow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
        return resp.status_code < 400
    except Exception:
        return True  # network errors are inconclusive — don't penalize


def _fact_check(entry: dict) -> dict:
    text = f"{entry.get('title', '')} {entry.get('body', '')}"
    signals = entry.get("signals", {})
    failed = []
    details = {}

    # CVE validation — verify each CVE exists in NVD
    cves = list(set(signals.get("cves", []) + CVE_PATTERN.findall(text)))
    if cves:
        bad = [c for c in cves if not _check_cve(c)]
        if bad:
            failed.append("cve")
            details["cve"] = f"Unverified CVEs: {', '.join(bad)}"

    # IP validation — all-private IPs in a threat report is a hallucination signal
    ips = list(set(signals.get("ips", []) + IP_PATTERN.findall(text)))
    if ips:
        public = [ip for ip in ips if _is_public_ip(ip)]
        if not public:
            failed.append("ip")
            details["ip"] = "Only private/loopback IPs found — likely hallucinated"

    # URL reachability — definitive HTTP errors only
    url = entry.get("url", "")
    if url:
        if not _check_url(url):
            failed.append("url")
            details["url"] = "URL returned an error response"

    # Threat consistency — high threat with zero signals is suspicious
    llm = entry.get("llm_analysis", {})
    threat = llm.get("threat_level", "unknown")
    has_exploit = signals.get("has_exploit", False)
    if threat == "high" and not has_exploit and not cves and not [ip for ip in ips if _is_public_ip(ip)]:
        failed.append("threat_consistency")
        details["threat_consistency"] = "High threat level claimed but no exploit keywords, CVEs, or public IPs found"

    return {"passed": len(failed) == 0, "failed": failed, "details": details}


def run(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    verified, eliminated = [], []
    for entry in entries:
        result = _fact_check(entry)
        annotated = {**entry, "fact_check": result}
        if result["passed"]:
            verified.append(annotated)
        else:
            eliminated.append(annotated)
    return verified, eliminated
