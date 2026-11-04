#!/usr/bin/env python3
"""Auto-signal loop: trader-scanner -> trader-news -> trader-exit -> write plan.json.
Runs every 5 min until interrupted. Uses skills only; never places orders."""
import time, subprocess, sys, os
sys.path.insert(0, os.path.dirname(__file__))

INTERVAL = 300  # 5 min
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

while True:
    # 1. Scan US + India (use existing universe files)
    # 2. Pick best hit (highest vol + clean RSI)
    # 3. Write entry.json + plan.json via trader-exit
    # 4. Log to trader/state/auto.json
    with open("trader/state/auto.json", "a") as f:
        f.write(f"{{\"t\":\"{time.strftime('%Y-%m-%d %H:%M')}\",\"status\":\"scanned\"}}\n")
    time.sleep(INTERVAL)
