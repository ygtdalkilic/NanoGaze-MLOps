import sys
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, str(Path(__file__).parent / "src"))

import agent
import dashboard

if __name__ == "__main__":
    skip_agent = "--skip-agent" in sys.argv

    if not skip_agent:
        print("[RUN] Starting agent...")
        agent.run()

    print("[RUN] Starting dashboard...")
    dashboard.run()
