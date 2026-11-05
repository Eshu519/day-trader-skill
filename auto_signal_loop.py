#!/usr/bin/env python3
"""Auto-signal loop: trader-scanner -> trader-news -> trader-exit -> write plan.json.
Runs every 10 min until interrupted. Uses skills only; never places orders."""
import time, subprocess, sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

INTERVAL = 600  # 10 min
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def scan_universe(universe_file, limit=500):
    """Run daily scan on a universe file and return hits."""
    cmd = f"{PYTHON} {SKILL_DIR}/trader-scanner/scan.py daily --watchlist {universe_file} --limit {limit}"
    result = run(cmd)
    if result.returncode not in (0, 1):
        print(f"Scan failed: {result.stderr}")
        return []
    
    # Read watchlist.json
    try:
        with open("trader/watchlist.json", "r") as f:
            data = json.load(f)
        return data.get("hits", [])
    except Exception as e:
        print(f"Failed to read watchlist: {e}")
        return []

def pick_best_hit(hits):
    """Pick the best hit based on volume and RSI."""
    if not hits:
        return None
    # Sort by volume descending, prefer RSI 30-70 (not oversold/overbought)
    def score(h):
        vol = h.get("volume", 0)
        rsi = h.get("rsi", 50)
        # Penalize extreme RSI
        rsi_penalty = abs(rsi - 50) / 50
        return vol * (1 - rsi_penalty * 0.5)
    return max(hits, key=score)

def check_news(symbol):
    """Run trader-news on a symbol."""
    cmd = f"{PYTHON} {SKILL_DIR}/trader-news/news.py --tickers {symbol}"
    result = run(cmd)
    return result.stdout, result.returncode == 0

def create_plan(symbol, entry_price):
    """Create exit plan via trader-exit."""
    # Use a simple percentage stop (1% below entry) and 1R target
    stop_price = round(entry_price * 0.99, 2)
    cmd = f"{PYTHON} {SKILL_DIR}/trader-exit/exit.py plan --symbol {symbol} --entry {entry_price} --stop price:{stop_price} --target 1R --write trader/plan.json"
    result = run(cmd)
    return result.returncode == 0, result.stdout

while True:
    print(f"\n=== Auto-signal loop: {time.strftime('%Y-%m-%d %H:%M')} ===")
    
    # 1. Scan US universe
    print("Scanning US universe...")
    us_hits = scan_universe("trader/universe.txt", limit=1000)
    print(f"  US hits: {len(us_hits)}")
    
    # 2. Scan India universe
    print("Scanning India universe...")
    india_hits = scan_universe("trader/universe_india.txt", limit=500)
    print(f"  India hits: {len(india_hits)}")
    
    # 3. Combine and pick best
    all_hits = us_hits + india_hits
    best = pick_best_hit(all_hits)
    
    if best:
        symbol = best["symbol"]
        price = best["price"]
        rsi = best.get("rsi", 0)
        setups = best.get("setups", [])
        print(f"\nBest signal: {symbol} @ {price} (RSI {rsi}, setups: {setups})")
        
        # 4. Check news
        print("Checking news...")
        news_out, news_ok = check_news(symbol)
        print(news_out.strip())
        
        # 5. Create plan
        print("Creating exit plan...")
        plan_ok, plan_out = create_plan(symbol, price)
        if plan_ok:
            print(plan_out.strip())
        else:
            print(f"Plan failed: {plan_out}")
        
        # 6. Log
        log_entry = {
            "t": time.strftime("%Y-%m-%d %H:%M"),
            "symbol": symbol,
            "price": price,
            "rsi": rsi,
            "setups": setups,
            "news_checked": news_ok,
            "plan_created": plan_ok
        }
    else:
        print("No signals found")
        log_entry = {
            "t": time.strftime("%Y-%m-%d %H:%M"),
            "status": "no_signals"
        }
    
    # Write log
    os.makedirs("trader/state", exist_ok=True)
    with open("trader/state/auto.json", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    print(f"Sleeping {INTERVAL}s...")
    time.sleep(INTERVAL)
