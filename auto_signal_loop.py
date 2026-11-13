#!/usr/bin/env python3
"""Auto-signal loop: trader-scanner -> trader-news -> trader-exit -> trader-budget -> trader-risk -> broker.
Runs every 10 min until interrupted. Places orders via the broker in trader/config.json
("megabull" paper by default, or "groww") after risk checks. Daily scanner closes select
signals; the broker's current LTP is used for the plan entry and sizing."""
import datetime, time, subprocess, sys, os, json
import math
sys.path.insert(0, os.path.dirname(__file__))

INTERVAL = 600  # 10 min
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable


def current_broker():
    """The broker named in trader/config.json (default: megabull, the paper account)."""
    try:
        with open("trader/config.json", "r") as f:
            return str(json.load(f).get("broker", "megabull")).lower()
    except Exception:
        return "megabull"


def load_connector(name):
    import importlib.util
    path = os.path.join(SKILL_DIR, "trader-megabull" if name == "megabull" else "trader-broker",
                        "megabull_connector.py" if name == "megabull" else "groww_connector.py")
    spec = importlib.util.spec_from_file_location(name + "_connector", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def normalize_symbol(value):
    symbol = str(value or "").strip().upper()
    for suffix in (".NSE", ".BSE", ".NS", ".BO"):
        if symbol.endswith(suffix):
            return symbol[:-len(suffix)]
    return symbol


def response_records(data, keys, description):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            if key not in data:
                continue
            value = data[key]
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return response_records(value, keys, description)
            raise ValueError("%s response field %s is not a list" % (description, key))
        for key in ("data", "result"):
            if isinstance(data.get(key), (dict, list)):
                return response_records(data[key], keys, description)
        if any(data.get(key) for key in ("symbol", "trading_symbol", "tradingSymbol",
                                         "instrumentName", "instrument_name", "ticker")):
            return [data]
        if not data:
            return []
    raise ValueError("unexpected %s response: %r" % (description, data))


def record_symbol(record):
    for key in ("symbol", "trading_symbol", "tradingSymbol", "instrumentName",
                "instrument_name", "ticker", "name"):
        if record.get(key):
            return normalize_symbol(record[key])
    return ""


def record_matches_symbol(record, wanted, instrument_token=None):
    if record_symbol(record) == wanted:
        return True
    token = record.get("instrumentToken") or record.get("instrument_token")
    return instrument_token is not None and str(token) == str(instrument_token)


def order_is_active(order):
    status = str(order.get("status") or order.get("order_status") or order.get("orderStatus") or "").upper()
    terminal = {"COMPLETE", "COMPLETED", "FILLED", "TRADED", "EXECUTED",
                "CANCELLED", "CANCELED", "REJECTED", "EXPIRED", "FAILED"}
    return status not in terminal


def position_is_open(position):
    for key in ("net_quantity", "netQuantity", "net_qty", "netQty", "qty", "quantity"):
        if key in position:
            try:
                return float(position[key] or 0) != 0
            except (TypeError, ValueError):
                return True
    return True


def has_in_progress_order(symbol, broker=None):
    """Return whether the configured broker has an active order or position for this symbol."""
    broker = (broker or current_broker()).lower()
    if broker == "megabull":
        connector = load_connector("megabull")
        instrument_token = connector.resolve_token(symbol)
        orders = connector.get_orders()
        positions = connector.get_positions()
        holdings = connector.get_holdings()
        active_orders = response_records(orders, ("open", "orders", "order_list"), "MegaBull orders")
    elif broker == "groww":
        connector = load_connector("groww")
        instrument_token = None
        orders = connector.get_orders()
        positions = connector.get_positions()
        holdings = connector.get_holdings()
        active_orders = response_records(orders, ("order_list", "orders", "open"), "Groww orders")
    else:
        raise ValueError("duplicate-order check does not support broker %r" % broker)

    wanted = normalize_symbol(symbol)
    for order in active_orders:
        if record_matches_symbol(order, wanted, instrument_token) and order_is_active(order):
            return True, "an active broker order"

    for description, response_name, data, keys in (
            ("position", "positions", positions, ("positions", "position_list", "net_positions")),
            ("holding", "holdings", holdings, ("holdings", "holding_list"))):
        records = response_records(data, keys, "%s %s" % (broker, response_name))
        for record in records:
            if record_matches_symbol(record, wanted, instrument_token) and position_is_open(record):
                return True, "an open broker %s" % description
    return False, ""


def get_broker_ltp(symbol, broker=None):
    broker = (broker or current_broker()).lower()
    if broker == "megabull":
        connector = load_connector("megabull")
        token = connector.resolve_token(symbol)
        return connector.current_ltp_price(token)
    if broker == "groww":
        connector = load_connector("groww")
        return connector.get_ltp(symbol)
    raise ValueError("live price lookup does not support broker %r" % broker)


def record_broker_ltp(symbol, price, broker, path="trader/prices.json"):
    """Merge a broker quote into the prices file as a fresh sizing/risk input."""
    if os.path.exists(path):
        with open(path, "r") as f:
            doc = json.load(f)
    else:
        doc = {}
    if not isinstance(doc, dict):
        raise ValueError("%s must contain a JSON object" % path)
    prices = doc.setdefault("prices", {})
    detail = doc.setdefault("detail", {})
    if not isinstance(prices, dict) or not isinstance(detail, dict):
        raise ValueError("%s must contain object-valued prices and detail fields" % path)

    try:
        price = float(price)
    except (TypeError, ValueError):
        raise ValueError("broker returned an invalid LTP for %s: %r" % (symbol, price))
    if not math.isfinite(price) or price <= 0:
        raise ValueError("broker returned an invalid LTP for %s: %r" % (symbol, price))

    fetched = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    fetched = fetched.replace("+00:00", "Z")
    key = str(symbol).upper()
    has_existing_prices = bool(prices)
    prices[key] = price
    detail[key] = {"time": fetched, "fetched": fetched, "source": broker}
    if not has_existing_prices and "as_of" not in doc:
        doc["as_of"] = fetched
    temp = path + ".tmp"
    with open(temp, "w") as f:
        json.dump(doc, f, indent=2)
    os.replace(temp, path)


def refresh_signal_price(symbol, broker):
    price = get_broker_ltp(symbol, broker)
    record_broker_ltp(symbol, price, broker)
    return price


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

def add_alerts():
    """Add alerts from plan via trader-alerts."""
    cmd = f"{PYTHON} {SKILL_DIR}/trader-alerts/alerts.py add --from-plan"
    result = run(cmd)
    return result.returncode == 0, result.stdout

def fetch_balance():
    """Fetch available balance from the configured broker and write to trader/portfolio.json."""
    broker = current_broker()
    try:
        if broker == "megabull":
            mb = load_connector("megabull")
            bal = mb.get_balance()
            available_cash = float(bal.get("virtualMoneyLeft") or 0)
            source = "megabull"
        else:
            gw = load_connector("groww")
            margin = gw.groww.get_available_margin_details()
            equity_margin = margin.get("equity_margin_details", {})
            available_cash = equity_margin.get("cnc_balance_available", 0)
            source = "groww"

        portfolio = {
            "cash": available_cash,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": source
        }
        os.makedirs("trader", exist_ok=True)
        with open("trader/portfolio.json", "w") as f:
            json.dump(portfolio, f, indent=2)

        print(f"Fetched {source} balance: Rs{available_cash:.2f} available")
        return True, available_cash
    except Exception as e:
        print(f"Failed to fetch {broker} balance: {type(e).__name__}: {e}")
        return False, 0

def run_budget():
    """Run trader-budget to size the position."""
    cmd = f"{PYTHON} {SKILL_DIR}/trader-budget/size.py --write"
    result = run(cmd)
    out = result.stdout.strip()
    if result.returncode != 0:
        # size.py prints its refusal to stdout, but a crash (e.g. a syntax error)
        # only shows up on stderr; surface both so the failure is never blank.
        err = result.stderr.strip()
        if err:
            out = (out + "\n" + err).strip() if out else err
    return result.returncode == 0, out

def run_risk():
    """Run trader-risk check."""
    cmd = f"{PYTHON} {SKILL_DIR}/trader-risk/check.py"
    result = run(cmd)
    return result.returncode == 0, result.stdout

def place_order():
    """Place order via the configured broker (megabull paper or groww)."""
    broker = current_broker()
    try:
        with open("trader/orders.json", "r") as f:
            orders_data = json.load(f)
        orders = orders_data.get("orders", [])
        if not orders:
            return False, "No orders in trader/orders.json"
        order = orders[0]  # Take first order
    except Exception as e:
        return False, f"Failed to read orders: {e}"

    if broker == "megabull":
        ticket = {
            'symbol': order.get('symbol'),
            'qty': int(float(order.get('qty', 0))),
            'side': order.get('side', 'buy').upper(),
            'type': order.get('type', 'market'),
            'limit_price': order.get('limit_price'),
            'trigger_price': order.get('trigger_price') or order.get('stop_price'),
            'product': 'MIS',
        }
        try:
            mb = load_connector("megabull")
            result = mb.place_order(ticket, product='MIS')
            return True, json.dumps(result, indent=2)
        except Exception as e:
            return False, f"MegaBull order failed: {type(e).__name__}: {e}"

    ticket = {
        'symbol': order.get('symbol'),
        'qty': int(float(order.get('qty', 0))),
        'side': order.get('side', 'buy').upper(),
        'order_type': order.get('type', 'market').upper(),
        'price': float(order.get('limit_price', 0)) if order.get('limit_price') else 0,
        'product': 'CNC'
    }
    try:
        gw = load_connector("groww")
        result = gw.place_order(ticket)
        return True, json.dumps(result, indent=2)
    except Exception as e:
        return False, f"Groww order failed: {type(e).__name__}: {e}"

def record_broker_result(success, broker_id, filled_qty=0, filled_price=0):
    """Record order result via ticket.py."""
    status = "placed" if success else "failed"
    cmd = f"{PYTHON} {SKILL_DIR}/trader-broker/ticket.py result --index 1 --status {status}"
    if broker_id:
        cmd += f" --broker-id {broker_id}"
    if filled_qty:
        cmd += f" --filled-qty {filled_qty}"
    if filled_price:
        cmd += f" --filled-price {filled_price}"
    result = run(cmd)
    return result.returncode == 0, result.stdout

def main():
    while True:
        print(f"\n=== Auto-signal loop: {time.strftime('%Y-%m-%d %H:%M')} ===")

        print("Scanning India universe...")
        india_hits = scan_universe("trader/universe_india.txt", limit=500)
        print(f"  India hits: {len(india_hits)}")

        best = pick_best_hit(india_hits)

        if best:
            symbol = best["symbol"]
            price = best["price"]
            rsi = best.get("rsi", 0)
            setups = best.get("setups", [])
            print("\nBest signal: %s (scanner daily close Rs%.2f; RSI %s, setups: %s)"
                  % (symbol, price, rsi, setups))

            broker = current_broker()
            try:
                active, reason = has_in_progress_order(symbol, broker)
            except Exception as e:
                print("Could not verify existing %s orders/positions for %s; skipping this cycle: %s: %s"
                      % (broker, symbol, type(e).__name__, e))
                log_entry = {"t": time.strftime("%Y-%m-%d %H:%M"), "symbol": symbol,
                             "status": "active_order_check_failed"}
                os.makedirs("trader/state", exist_ok=True)
                with open("trader/state/auto.json", "a") as f:
                    f.write(json.dumps(log_entry) + "\n")
                time.sleep(INTERVAL)
                continue
            if active:
                print("Skipping %s: %s already exists." % (symbol, reason))
                log_entry = {"t": time.strftime("%Y-%m-%d %H:%M"), "symbol": symbol,
                             "status": "active_order_skipped", "reason": reason}
                os.makedirs("trader/state", exist_ok=True)
                with open("trader/state/auto.json", "a") as f:
                    f.write(json.dumps(log_entry) + "\n")
                time.sleep(INTERVAL)
                continue

            print("Checking news...")
            news_out, news_ok = check_news(symbol)
            print(news_out.strip())

            signal_price = price
            try:
                price = refresh_signal_price(symbol, broker)
            except Exception as e:
                print("Could not get a fresh %s price for %s; skipping this cycle: %s: %s"
                      % (broker, symbol, type(e).__name__, e))
                log_entry = {"t": time.strftime("%Y-%m-%d %H:%M"), "symbol": symbol,
                             "status": "live_price_check_failed"}
                os.makedirs("trader/state", exist_ok=True)
                with open("trader/state/auto.json", "a") as f:
                    f.write(json.dumps(log_entry) + "\n")
                time.sleep(INTERVAL)
                continue
            print("Scanner daily close: Rs%.2f; current %s LTP: Rs%.2f. Using LTP for plan and sizing."
                  % (signal_price, broker, price))

            print("Creating exit plan...")
            plan_ok, plan_out = create_plan(symbol, price)
            if plan_ok:
                print(plan_out.strip())
            else:
                print(f"Plan failed: {plan_out}")
                log_entry = {"t": time.strftime("%Y-%m-%d %H:%M"), "symbol": symbol,
                             "status": "plan_failed"}
                os.makedirs("trader/state", exist_ok=True)
                with open("trader/state/auto.json", "a") as f:
                    f.write(json.dumps(log_entry) + "\n")
                time.sleep(INTERVAL)
                continue

            print("Adding alerts...")
            alerts_ok, alerts_out = add_alerts()
            if alerts_ok:
                print(alerts_out.strip())

            print(f"Fetching {broker} balance...")
            balance_ok, balance = fetch_balance()
            if not balance_ok:
                print("Failed to fetch balance, using config budget")

            print("Running budget sizing...")
            budget_ok, budget_out = run_budget()
            if budget_ok:
                print(budget_out.strip())
            else:
                print(f"Budget failed: {budget_out}")
                log_entry = {"t": time.strftime("%Y-%m-%d %H:%M"), "symbol": symbol,
                             "status": "budget_failed"}
                os.makedirs("trader/state", exist_ok=True)
                with open("trader/state/auto.json", "a") as f:
                    f.write(json.dumps(log_entry) + "\n")
                time.sleep(INTERVAL)
                continue

            print("Running risk check...")
            risk_ok, risk_out = run_risk()
            if risk_ok:
                print(risk_out.strip())
            else:
                print(f"Risk check blocked: {risk_out}")
                log_entry = {"t": time.strftime("%Y-%m-%d %H:%M"), "symbol": symbol,
                             "status": "risk_blocked"}
                os.makedirs("trader/state", exist_ok=True)
                with open("trader/state/auto.json", "a") as f:
                    f.write(json.dumps(log_entry) + "\n")
                time.sleep(INTERVAL)
                continue

            print(f"Placing order via {broker}...")
            order_ok, order_out = place_order()
            if order_ok:
                print(f"{broker} order placed: {order_out}")
                try:
                    order_result = json.loads(order_out)
                    broker_id = order_result.get("groww_order_id") or order_result.get("id") or ""
                except Exception:
                    broker_id = ""
                record_ok, record_out = record_broker_result(True, broker_id)
                if record_ok:
                    print("Order recorded in broker log")
            else:
                print(f"{broker} order failed: {order_out}")
                record_broker_result(False, "")

            log_entry = {
                "t": time.strftime("%Y-%m-%d %H:%M"),
                "symbol": symbol,
                "price": price,
                "signal_price": signal_price,
                "rsi": rsi,
                "setups": setups,
                "news_checked": news_ok,
                "plan_created": plan_ok,
                "alerts_added": alerts_ok,
                "budget_done": budget_ok,
                "risk_passed": risk_ok,
                "order_placed": order_ok
            }
        else:
            print("No signals found")
            log_entry = {"t": time.strftime("%Y-%m-%d %H:%M"), "status": "no_signals"}

        os.makedirs("trader/state", exist_ok=True)
        with open("trader/state/auto.json", "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        print(f"Sleeping {INTERVAL}s...")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()