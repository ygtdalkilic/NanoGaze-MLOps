import os
from urllib.parse import urlparse

DISCARD_THRESHOLD = int(os.getenv("ENGINE1_THRESHOLD", "50"))

REQUIRED_FIELDS = ["url", "title", "body", "source"]

TRUSTED_DOMAINS = {
    "github.com", "nvd.nist.gov", "cve.mitre.org", "exploit-db.com",
    "thehackernews.com", "bleepingcomputer.com", "krebsonsecurity.com",
    "nist.gov", "cisa.gov", "microsoft.com", "google.com", "cloudflare.com",
    "reddit.com", "stackoverflow.com", "medium.com", "arxiv.org",
    "sec.gov", "reuters.com", "techcrunch.com", "wired.com",
}

REPUTABLE_TLDS = {".com", ".org", ".edu", ".gov", ".io", ".net", ".co.uk", ".ac.uk"}


def _dedup(entries: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for e in entries:
        key = e.get("url", "").strip().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _score_completeness(entry: dict) -> float:
    filled = sum(1 for f in REQUIRED_FIELDS if entry.get(f) and str(entry[f]).strip())
    return round((filled / len(REQUIRED_FIELDS)) * 100, 1)


def _score_validity(entry: dict) -> float:
    checks = 0

    url = entry.get("url", "")
    if url.startswith(("http://", "https://")) and "." in url[8:]:
        checks += 1

    if len(entry.get("title", "").split()) >= 3:
        checks += 1

    if len(entry.get("body", "").split()) >= 10:
        checks += 1

    return round((checks / 3) * 100, 1)


def _score_reputation(entry: dict) -> float:
    try:
        domain = urlparse(entry.get("url", "")).netloc.lower().replace("www.", "")
    except Exception:
        return 0.0

    if not domain:
        return 0.0

    if any(domain == d or domain.endswith("." + d) for d in TRUSTED_DOMAINS):
        return 100.0

    for tld in REPUTABLE_TLDS:
        if domain.endswith(tld):
            return 65.0

    if "." in domain and not domain.replace(".", "").isdigit():
        return 40.0

    return 10.0


def _score_richness(entry: dict) -> float:
    title_score = min(len(entry.get("title", "").split()) / 10, 1.0)
    body_score = min(len(entry.get("body", "").split()) / 50, 1.0)
    return round(((title_score + body_score) / 2) * 100, 1)


def _score(entry: dict) -> dict:
    completeness = _score_completeness(entry)
    validity     = _score_validity(entry)
    reputation   = _score_reputation(entry)
    richness     = _score_richness(entry)

    trust_score = round(
        completeness * 0.35 +
        validity     * 0.30 +
        reputation   * 0.20 +
        richness     * 0.15,
        1
    )
    return {**entry, "trust_score": trust_score, "scores": {
        "completeness": completeness,
        "validity":     validity,
        "reputation":   reputation,
        "richness":     richness,
    }}


def run(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    unique = _dedup(entries)
    scored = [_score(e) for e in unique]
    verified  = [e for e in scored if e["trust_score"] >= DISCARD_THRESHOLD]
    eliminated = [e for e in scored if e["trust_score"] <  DISCARD_THRESHOLD]
    return verified, eliminated
