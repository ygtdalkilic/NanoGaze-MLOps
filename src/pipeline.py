import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import engine_1
import engine_2
import reporter
from db_manager import DatabaseManager


def run() -> tuple[int, int, int]:
    db = DatabaseManager()

    raw = list(db.raw_queue.find({}, {"_id": 0}))
    db.close()

    if not raw:
        print("[PIPELINE] raw_queue is empty — run agent.py first.")
        return 0, 0, 0

    print(f"[PIPELINE] {len(raw)} entries loaded from raw_queue")

    e1_verified, e1_eliminated = engine_1.run(raw)
    print(f"[PIPELINE] Engine 1 — Verified: {len(e1_verified)} | Eliminated: {len(e1_eliminated)}")

    e2_verified, e2_eliminated = engine_2.run(e1_verified)
    print(f"[PIPELINE] Engine 2 — Verified: {len(e2_verified)} | Eliminated: {len(e2_eliminated)}")

    for e in e1_eliminated:
        e["eliminated_by"] = "engine_1"
    for e in e2_eliminated:
        e["eliminated_by"] = "engine_2"

    all_eliminated = e1_eliminated + e2_eliminated
    reporter.generate(raw, e2_verified, all_eliminated)

    return len(raw), len(e2_verified), len(all_eliminated)


if __name__ == "__main__":
    run()
