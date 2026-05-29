import random
import time
from datetime import datetime, timezone
from pathlib import Path

NORMAL_PATHS = ["/", "/home", "/about", "/api/v1/users", "/api/v1/products",
                "/static/main.js", "/static/style.css", "/favicon.ico"]
NORMAL_METHODS = ["GET", "GET", "GET", "POST"]
NORMAL_STATUS = [200, 200, 200, 304]
ANOMALY_PATHS = [
    "/api/v1/users?id=1' OR '1'='1",
    "/api/v1/products?search=<script>alert(1)</script>",
    "/admin/config",
    "/etc/passwd",
    "/api/v1/data",
]
ANOMALY_METHODS = ["GET", "POST", "DELETE", "PATCH", "OPTIONS"]
ANOMALY_STATUS = [500, 500, 503, 403, 401]

IPS = [f"192.168.1.{i}" for i in range(1, 50)] + \
      [f"10.0.0.{i}" for i in range(1, 20)]
ANOMALY_IPS = [f"45.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}"
               for _ in range(10)]


def _normal_line():
    ip = random.choice(IPS)
    method = random.choice(NORMAL_METHODS)
    path = random.choice(NORMAL_PATHS)
    status = random.choice(NORMAL_STATUS)
    size = random.randint(200, 5000)
    ts = datetime.now(timezone.utc).strftime("%d/%b/%Y:%H:%M:%S +0000")
    return f'{ip} - - [{ts}] "{method} {path} HTTP/1.1" {status} {size}'


def _anomaly_line():
    ip = random.choice(ANOMALY_IPS)
    method = random.choice(ANOMALY_METHODS)
    path = random.choice(ANOMALY_PATHS)
    status = random.choice(ANOMALY_STATUS)
    size = random.choice([0, random.randint(50000, 500000)])
    ts = datetime.now(timezone.utc).strftime("%d/%b/%Y:%H:%M:%S +0000")
    return f'{ip} - - [{ts}] "{method} {path} HTTP/1.1" {status} {size}'


def run(output_path="data/live_stream.log", delay=0.1):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    print(f"[GEN] Writing logs to {output_path} — Ctrl+C to stop")
    with open(output_path, "a") as f:
        while True:
            line = _anomaly_line() if random.random() < 0.05 else _normal_line()
            f.write(line + "\n")
            f.flush()
            time.sleep(delay)


if __name__ == "__main__":
    run()
