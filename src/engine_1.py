import re
import time
import tracemalloc
from datetime import datetime, timezone

import numpy as np
from sklearn.ensemble import IsolationForest

from log_generator import _normal_line
from db_manager import DatabaseManager

LOG_PATTERN = re.compile(
    r'(?P<ip>[\d.]+) .+ \[.+\] "(?P<method>\w+) .+ HTTP/\S+" (?P<status>\d+) (?P<size>\d+)'
)

METHOD_MAP = {"GET": 0, "POST": 1, "PUT": 2, "DELETE": 3, "PATCH": 4,
              "OPTIONS": 5, "HEAD": 6}


def _parse(line):
    m = LOG_PATTERN.search(line)
    if not m:
        return None
    ip_int = sum(int(o) * (256 ** (3 - i))
                 for i, o in enumerate(m["ip"].split(".")))
    method = METHOD_MAP.get(m["method"], 9)
    status = int(m["status"])
    size = int(m["size"])
    return [ip_int, method, status, size]


def train_gatekeeper(n_samples=500, contamination=0.05):
    samples = [_parse(_normal_line()) for _ in range(n_samples)]
    samples = [s for s in samples if s]
    model = IsolationForest(contamination=contamination, random_state=42, n_jobs=-1)
    model.fit(samples)
    print(f"[E1] Model trained on {len(samples)} normal samples.")
    return model


def stream(log_path, model, db: DatabaseManager, anomaly_handler):
    tracemalloc.start()
    processed = safe = flagged = 0
    start = time.time()

    with open(log_path, "r") as f:
        f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.05)
                continue

            line = line.strip()
            if not line:
                continue

            features = _parse(line)
            processed += 1

            if features is None:
                continue

            score = model.decision_function([features])[0]
            pred = model.predict([features])[0]
            ts = datetime.now(timezone.utc).isoformat()

            if pred == 1:
                safe += 1
                db.insert_one(db.safe_traffic, {"raw": line, "score": score, "ts": ts})
            else:
                flagged += 1
                anomaly_handler(line)

            if processed % 50 == 0:
                mem_mb = tracemalloc.get_traced_memory()[1] / 1024 / 1024
                elapsed = time.time() - start
                rate = processed / elapsed
                print(f"[E1] processed={processed} safe={safe} flagged={flagged} "
                      f"rate={rate:.1f}/s mem_peak={mem_mb:.2f}MB")
