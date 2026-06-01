from collections import Counter
from urllib.parse import urlparse

DISCARD_THRESHOLD = 50


def _detect_criteria(entries: list[dict]) -> tuple[list[str], list[str], float, float]:
    field_counts = Counter()
    domain_counts = Counter()
    title_lengths = []
    body_lengths = []

    for entry in entries:
        for key, val in entry.items():
            if isinstance(val, str) and val.strip():
                field_counts[key] += 1
        try:
            domain = urlparse(entry.get("url", "")).netloc.replace("www.", "")
            if domain:
                domain_counts[domain] += 1
        except Exception:
            pass
        if entry.get("title"):
            title_lengths.append(len(entry["title"]))
        if entry.get("body"):
            body_lengths.append(len(entry["body"]))

    total = len(entries) or 1
    expected_fields = [f for f, c in field_counts.items() if c / total >= 0.5]
    trusted_domains = [d for d, c in domain_counts.items() if c >= 2]
    avg_title = sum(title_lengths) / len(title_lengths) if title_lengths else 20
    avg_body = sum(body_lengths) / len(body_lengths) if body_lengths else 100

    return expected_fields, trusted_domains, avg_title, avg_body


def _score_validity(entry: dict, fields: list[str]) -> float:
    valid = sum(
        1 for f in fields
        if isinstance(entry.get(f), str) and entry.get(f).strip()
    )
    return round((valid / len(fields)) * 100, 1) if fields else 0.0


def _score_completeness(entry: dict, fields: list[str]) -> float:
    filled = sum(1 for f in fields if entry.get(f))
    return round((filled / len(fields)) * 100, 1) if fields else 0.0


def _score_popularity(entry: dict, trusted_domains: list[str]) -> float:
    try:
        domain = urlparse(entry.get("url", "")).netloc.replace("www.", "")
    except Exception:
        return 40.0
    return 100.0 if any(d in domain for d in trusted_domains) else 40.0


def _score_discoverability(entry: dict, avg_title: float, avg_body: float) -> float:
    title = entry.get("title", "")
    body = entry.get("body", "")
    title_score = min(len(title) / avg_title, 1.0) if avg_title else 0.0
    body_score = min(len(body) / avg_body, 1.0) if avg_body else 0.0
    return round(((title_score + body_score) / 2) * 100, 1)


def _score_usage(entries: list[dict], entry: dict) -> float:
    try:
        domain = urlparse(entry.get("url", "")).netloc.replace("www.", "")
    except Exception:
        return 0.0
    count = sum(
        1 for e in entries
        if urlparse(e.get("url", "")).netloc.replace("www.", "") == domain
    )
    return min(count * 20, 100.0)


def score_entry(entry: dict, all_entries: list[dict], criteria: tuple) -> dict:
    fields, trusted_domains, avg_title, avg_body = criteria

    validity        = _score_validity(entry, fields)
    completeness    = _score_completeness(entry, fields)
    popularity      = _score_popularity(entry, trusted_domains)
    discoverability = _score_discoverability(entry, avg_title, avg_body)
    usage           = _score_usage(all_entries, entry)

    trust_score = round(
        (validity + completeness + popularity + discoverability + usage) / 5, 1
    )
    return {**entry, "trust_score": trust_score, "scores": {
        "validity": validity,
        "completeness": completeness,
        "popularity": popularity,
        "discoverability": discoverability,
        "usage": usage,
    }}


def run(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    criteria = _detect_criteria(entries)
    scored = [score_entry(e, entries, criteria) for e in entries]
    verified  = [e for e in scored if e["trust_score"] >= DISCARD_THRESHOLD]
    eliminated = [e for e in scored if e["trust_score"] <  DISCARD_THRESHOLD]
    return verified, eliminated
