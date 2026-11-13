#!/usr/bin/env python3
"""MegaBull paper trading CLI for the day-trader pack.

This is the only tool in the pack that talks to MegaBull. It never places an
order on its own: `place` refuses unless trader-broker has recorded your yes
for that exact order today (ticket.py approve), and it records the outcome
back with ticket.py result.

    python3 megabull.py balance                      # virtual money, writes trader/portfolio.json
    python3 megabull.py instruments [--refresh]      # download/cache the instrument token list
    python3 megabull.py token HDFCBANK.NS            # resolve a symbol to its instrumentToken
    python3 megabull.py ltp HDFCBANK.NS              # last traded price
    python3 megabull.py place --index 1              # place an APPROVED order (asks nothing, checks the log)
    python3 megabull.py orders                       # today's open and executed orders
    python3 megabull.py positions                    # open positions
    python3 megabull.py holdings                     # delivery holdings
    python3 megabull.py cancel --ids 101,102         # cancel pending orders
    python3 megabull.py report --month 11 --year 2026

Credentials: MEGABULL_API_KEY in the environment (never in the chat).
Config: trader/config.json, "broker": "megabull", optional "megabull": {"product": "MIS", "instruments_cache_days": 7}.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import megabull_connector as mb  # noqa: E402

TICKET = os.path.join(HERE, os.pardir, "trader-broker", "ticket.py")


class CliError(Exception):
    pass


def read_json(path, what, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise CliError("no %s at %s" % (what, path))
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def megabull_cfg(cfg):
    section = (cfg or {}).get("megabull") or {}
    return {
        "product": str(section.get("product", "MIS")).upper(),
        "instruments_cache_days": int(section.get("instruments_cache_days", mb.CACHE_DAYS)),
    }


def check_broker(cfg, force):
    broker = str((cfg or {}).get("broker", "")).lower()
    if broker != "megabull" and not force:
        raise CliError('trader/config.json has "broker": "%s", not "megabull". '
                       'Switch it (or pass --force if you really mean to use MegaBull now).' % (broker or "unset"))


def run_ticket(args):
    cmd = [sys.executable, TICKET] + args
    return subprocess.run(cmd, capture_output=True, text=True)


def ticket_status(index, orders, config, risk, state, now):
    args = ["show", "--index", str(index), "--json", "--orders", orders, "--config", config,
            "--risk", risk, "--state", state]
    if now:
        args += ["--now", now]
    res = run_ticket(args)
    if res.returncode not in (0, 1):
        raise CliError("ticket.py show failed: %s" % (res.stderr.strip() or res.stdout.strip()))
    try:
        doc = json.loads(res.stdout)
    except ValueError:
        raise CliError("could not parse ticket.py output: %s" % res.stdout.strip())
    return doc


def cmd_balance(a):
    cfg = read_json(a.config, "config", required=False) or {}
    bal = mb.get_balance()
    left = bal.get("virtualMoneyLeft")
    portfolio = {
        "cash": float(left) if left is not None else None,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "megabull",
        "virtual_money": bal.get("virtualMoney"),
        "virtual_money_blocked": bal.get("virtualMoneyBlocked"),
        "brokerage_per_order": bal.get("brokerage"),
    }
    write_json(a.portfolio, portfolio)
    print("MegaBull virtual money: total %s, blocked %s, left %s (brokerage Rs%s per order)" % (
        bal.get("virtualMoney"), bal.get("virtualMoneyBlocked"), bal.get("virtualMoneyLeft"),
        bal.get("brokerage")))
    print("Wrote %s (cash = virtualMoneyLeft)." % a.portfolio)
    return 0


def cmd_instruments(a):
    cfg = read_json(a.config, "config", required=False) or {}
    mc = megabull_cfg(cfg)
    path = mb.ensure_instruments(a.cache, max_age_days=mc["instruments_cache_days"], refresh=a.refresh)
    rows = mb.load_instruments(path)
    print("%d instruments cached at %s" % (len(rows), path))
    return 0


def cmd_token(a):
    cfg = read_json(a.config, "config", required=False) or {}
    mc = megabull_cfg(cfg)
    print(mb.resolve_token(a.symbol, cache_path=a.cache, refresh=a.refresh,
                           max_age_days=mc["instruments_cache_days"]))
    return 0


def cmd_ltp(a):
    cfg = read_json(a.config, "config", required=False) or {}
    mc = megabull_cfg(cfg)
    token = mb.resolve_token(a.symbol, cache_path=a.cache, refresh=a.refresh,
                             max_age_days=mc["instruments_cache_days"])
    print(json.dumps(mb.get_ltp(token), indent=2))
    return 0


def cmd_place(a):
    cfg = read_json(a.config, "config", required=False) or {}
    check_broker(cfg, a.force)
    mc = megabull_cfg(cfg)
    doc = read_json(a.orders, "orders file (run trader-budget first)")
    orders = doc.get("orders", doc) if isinstance(doc, dict) else doc
    if not isinstance(orders, list) or not orders:
        raise CliError("no orders in %s" % a.orders)
    if not 1 <= a.index <= len(orders):
        raise CliError("there is no order %d (there are %d)" % (a.index, len(orders)))
    order = orders[a.index - 1]

    status = ticket_status(a.index, a.orders, a.config, a.risk, a.state, a.now)
    label = status.get("status", "")
    if not str(label).upper().startswith("APPROVED"):
        raise CliError("order %d is not approved yet: %s\nRun ticket.py show, get the user's yes, "
                       "then ticket.py approve --index %d --reply \"yes\" first." % (a.index, label, a.index))

    ticket = {
        "symbol": order.get("symbol"),
        "qty": order.get("qty"),
        "side": order.get("side"),
        "type": order.get("type", "market"),
        "limit_price": order.get("limit_price"),
        "trigger_price": order.get("trigger_price") or order.get("stop_price"),
        "product": a.product or mc["product"],
    }
    payload = mb.build_order_payload(ticket, product=ticket["product"], cache_path=a.cache,
                                     refresh=a.refresh, max_age_days=mc["instruments_cache_days"])
    if payload["orderType"] == "MKT":
        ticket["price"] = mb.current_ltp_price(payload["instrumentToken"])
        payload = mb.build_order_payload(ticket, product=ticket["product"], cache_path=a.cache,
                                         refresh=False, max_age_days=mc["instruments_cache_days"])
    print("Placing on MegaBull (paper): %s" % json.dumps(payload))
    resp = mb.place_order(ticket, product=ticket["product"], cache_path=a.cache,
                          refresh=False, max_age_days=mc["instruments_cache_days"])
    print(json.dumps(resp, indent=2))

    broker_id = str(resp.get("id")) if isinstance(resp, dict) and resp.get("id") is not None else ""
    filled = isinstance(resp, dict) and str(resp.get("status", "")).upper() == "COMPLETE"
    args = ["result", "--index", str(a.index), "--status", "placed",
            "--orders", a.orders, "--config", a.config, "--risk", a.risk, "--state", a.state,
            "--portfolio", a.portfolio]
    if a.now:
        args += ["--now", a.now]
    if broker_id:
        args += ["--broker-id", broker_id]
    if filled:
        args += ["--filled-qty", str(resp.get("qty") or order.get("qty")),
                 "--filled-price", str(resp.get("price"))]
    res = run_ticket(args)
    sys.stdout.write(res.stdout)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        raise CliError("the order was placed but ticket.py result failed; record it by hand")
    if not filled:
        print("Order is %s. When it fills, record it: ticket.py fill --symbol %s --side %s --qty Q --price P" % (
            resp.get("status") if isinstance(resp, dict) else "placed",
            str(order.get("symbol", "")).upper(), str(order.get("side", "")).lower()))
    print("Note: MegaBull has no bracket orders. The stop-loss and take-profit are NOT at the broker; "
          "trader-alerts watches them.")
    return 0


def cmd_orders(a):
    print(json.dumps(mb.get_orders(), indent=2))
    return 0


def cmd_positions(a):
    print(json.dumps(mb.get_positions(), indent=2))
    return 0


def cmd_holdings(a):
    print(json.dumps(mb.get_holdings(), indent=2))
    return 0


def cmd_cancel(a):
    ids = [s for s in a.ids.replace(" ", "").split(",") if s]
    print(json.dumps(mb.cancel_orders(ids), indent=2))
    return 0


def cmd_report(a):
    if a.month and a.year:
        print(json.dumps(mb.get_report_monthly(a.month, a.year), indent=2))
    elif a.start and a.end:
        print(json.dumps(mb.get_report_virtual(a.start, a.end), indent=2))
    else:
        raise CliError("pass --month M --year Y, or --start YYYY-MM-DD --end YYYY-MM-DD")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="MegaBull paper trading (never places without a recorded yes).")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--config", default="trader/config.json")
        p.add_argument("--cache", default=mb.CACHE_PATH, help="instruments CSV cache")
        p.add_argument("--refresh", action="store_true", help="re-download the instruments CSV")

    p = sub.add_parser("balance", help="virtual money; writes trader/portfolio.json")
    common(p)
    p.add_argument("--portfolio", default="trader/portfolio.json")
    p.set_defaults(fn=cmd_balance)

    p = sub.add_parser("instruments", help="download/cache the instrument token list")
    common(p)
    p.set_defaults(fn=cmd_instruments)

    p = sub.add_parser("token", help="resolve a symbol to its instrumentToken")
    common(p)
    p.add_argument("symbol")
    p.set_defaults(fn=cmd_token)

    p = sub.add_parser("ltp", help="last traded price for a symbol")
    common(p)
    p.add_argument("symbol")
    p.set_defaults(fn=cmd_ltp)

    p = sub.add_parser("place", help="place an order that trader-broker recorded a yes for today")
    common(p)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--orders", default="trader/orders.json")
    p.add_argument("--risk", default="trader/state/risk.json")
    p.add_argument("--state", default="trader/state/broker.json")
    p.add_argument("--portfolio", default="trader/portfolio.json")
    p.add_argument("--product", choices=["MIS", "CNC"], help="override the config's megabull.product")
    p.add_argument("--now", help="pin the clock for ticket.py, e.g. \"2026-10-19 10:15\" (IST)")
    p.add_argument("--force", action="store_true", help="place even if config broker is not megabull")
    p.set_defaults(fn=cmd_place)

    p = sub.add_parser("orders", help="today's open and executed orders")
    common(p)
    p.set_defaults(fn=cmd_orders)

    p = sub.add_parser("positions", help="open positions")
    common(p)
    p.set_defaults(fn=cmd_positions)

    p = sub.add_parser("holdings", help="delivery holdings")
    common(p)
    p.set_defaults(fn=cmd_holdings)

    p = sub.add_parser("cancel", help="cancel pending orders by id")
    common(p)
    p.add_argument("--ids", required=True, help="comma separated order ids, e.g. 101,102")
    p.set_defaults(fn=cmd_cancel)

    p = sub.add_parser("report", help="monthly P&L or virtual money report")
    common(p)
    p.add_argument("--month", type=int)
    p.add_argument("--year", type=int)
    p.add_argument("--start", help="YYYY-MM-DD")
    p.add_argument("--end", help="YYYY-MM-DD")
    p.set_defaults(fn=cmd_report)

    a = ap.parse_args(argv)
    if not getattr(a, "fn", None):
        ap.print_help()
        return 1
    try:
        return a.fn(a)
    except (CliError, mb.MegabullError) as e:
        print("megabull.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
