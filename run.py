from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))

import dashboard

if __name__ == "__main__":
    print("[RUN] Starting dashboard...")
    dashboard.run()
