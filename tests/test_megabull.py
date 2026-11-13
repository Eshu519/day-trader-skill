import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from _load import load, ROOT, FIX

mb = load("trader-megabull", "megabull_connector")
cli = load("trader-megabull", "megabull")
ticket = load("trader-broker", "ticket")

FIXTURE_CSV = os.path.join(FIX, "trader-megabull", "instruments.csv")
CFG_PATH = os.path.join(ROOT, "trader-budget", "config.example.json")
ORDERS_PATH = os.path.join(FIX, "trader-risk", "orders-tsla.json")
NOW = "2026-10-19 10:15"


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class Instruments(unittest.TestCase):
    def test_normalize_symbol_strips_exchange_suffixes(self):
        self.assertEqual(mb.normalize_symbol("HDFCBANK.NS"), "HDFCBANK")
        self.assertEqual(mb.normalize_symbol("reliance.bo"), "RELIANCE")
        self.assertEqual(mb.normalize_symbol("KALYANKJIL"), "KALYANKJIL")

    def test_resolve_token_exact_match(self):
        self.assertEqual(mb.resolve_token("HDFCBANK.NS", cache_path=FIXTURE_CSV), "341249")
        self.assertEqual(mb.resolve_token("RELIANCE", cache_path=FIXTURE_CSV), "738561")

    def test_resolve_token_unknown_symbol_raises(self):
        with self.assertRaises(mb.MegabullError):
            mb.resolve_token("ZZZZ", cache_path=FIXTURE_CSV)

    def test_load_instruments_reads_fixture(self):
        rows = mb.load_instruments(FIXTURE_CSV)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["tradingSymbol"], "RELIANCE")


class Payload(unittest.TestCase):
    def test_market_buy_payload(self):
        p = mb.build_order_payload({"symbol": "HDFCBANK.NS", "qty": "4", "side": "buy",
                                    "type": "market"}, cache_path=FIXTURE_CSV)
        self.assertEqual(p, {"instrumentToken": "341249", "qty": 4, "type": "BUY",
                             "duration": "MIS", "orderType": "MKT"})

    def test_market_order_submission_includes_current_ltp(self):
        ticket_data = {"symbol": "HDFCBANK.NS", "qty": 4, "side": "buy", "type": "market"}
        expected = {"instrumentToken": "341249", "qty": 4, "type": "BUY",
                    "duration": "MIS", "orderType": "MKT", "price": 742.5}
        with patch.object(mb, "get_ltp", return_value={"instrumentToken": "341249", "ltp": 742.5}), \
                patch.object(mb, "_request", return_value={"id": 101}) as request:
            result = mb.place_order(ticket_data, cache_path=FIXTURE_CSV)
        self.assertEqual(result, {"id": 101})
        request.assert_called_once_with("POST", "/api/order/buysell", expected)

    def test_market_order_refuses_invalid_ltp_without_submitting(self):
        ticket_data = {"symbol": "HDFCBANK.NS", "qty": 4, "side": "buy", "type": "market"}
        with patch.object(mb, "get_ltp", return_value={"ltp": None}), \
                patch.object(mb, "_request") as request:
            with self.assertRaises(mb.MegabullError):
                mb.place_order(ticket_data, cache_path=FIXTURE_CSV)
        request.assert_not_called()

    def test_limit_sell_payload(self):
        p = mb.build_order_payload({"symbol": "RELIANCE", "qty": 2, "side": "sell",
                                    "type": "limit", "limit_price": "2500.5"},
                                   product="CNC", cache_path=FIXTURE_CSV)
        self.assertEqual(p["orderType"], "LIMIT")
        self.assertEqual(p["price"], 2500.5)
        self.assertEqual(p["duration"], "CNC")
        self.assertEqual(p["type"], "SELL")

    def test_limit_without_price_refused(self):
        with self.assertRaises(mb.MegabullError):
            mb.build_order_payload({"symbol": "RELIANCE", "qty": 1, "side": "buy",
                                    "type": "limit"}, cache_path=FIXTURE_CSV)

    def test_bracket_legs_are_not_sent(self):
        p = mb.build_order_payload({"symbol": "RELIANCE", "qty": 1, "side": "buy", "type": "market",
                                    "stop_loss_stop_price": "2400", "take_profit_limit_price": "2600"},
                                   cache_path=FIXTURE_CSV)
        self.assertNotIn("stop_loss_stop_price", p)
        self.assertNotIn("take_profit_limit_price", p)
        self.assertNotIn("triggerPrice", p)

    def test_bad_side_refused(self):
        with self.assertRaises(mb.MegabullError):
            mb.build_order_payload({"symbol": "RELIANCE", "qty": 1, "side": "hold"},
                                   cache_path=FIXTURE_CSV)


class TicketRendering(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cfg = os.path.join(self.d, "config.json")
        with open(CFG_PATH) as fh:
            cfg = json.load(fh)
        cfg["broker"] = "megabull"
        with open(self.cfg, "w") as fh:
            json.dump(cfg, fh)

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_megabull_payload_shape(self):
        order = {"symbol": "HDFCBANK.NS", "side": "buy", "qty": "4", "type": "market",
                 "time_in_force": "day", "order_class": "bracket",
                 "stop_loss_stop_price": "742.95", "take_profit_limit_price": "757.95"}
        p = ticket.megabull_payload(order)
        self.assertEqual(p["symbol"], "HDFCBANK.NS")
        self.assertEqual(p["qty"], 4)
        self.assertNotIn("stop_loss_stop_price", p)

    def test_ticket_json_reports_megabull_tool(self):
        with open(ORDERS_PATH) as fh:
            order = json.load(fh)["orders"][0]
        out = ticket.ticket_json(order, 1, {"broker": "megabull", "paper": True}, None,
                                 {"orders": []}, "2026-10-19")
        self.assertEqual(out["broker"], "megabull")
        self.assertEqual(out["tool"], "megabull_place_order")
        self.assertEqual(out["tool_input"]["symbol"], order["symbol"])

    def test_fingerprint_unchanged_by_broker(self):
        with open(ORDERS_PATH) as fh:
            order = json.load(fh)["orders"][0]
        self.assertEqual(ticket.fingerprint(order), ticket.fingerprint(dict(order)))


class PlaceGate(unittest.TestCase):
    """`megabull.py place` must refuse unless ticket.py recorded a yes today."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.orders = os.path.join(self.d, "orders.json")
        shutil.copy(ORDERS_PATH, self.orders)
        self.cfg = os.path.join(self.d, "config.json")
        with open(CFG_PATH) as fh:
            cfg = json.load(fh)
        cfg["broker"] = "megabull"
        with open(self.cfg, "w") as fh:
            json.dump(cfg, fh)
        self.risk = os.path.join(self.d, "state", "risk.json")
        self.state = os.path.join(self.d, "state", "broker.json")
        self.portfolio = os.path.join(self.d, "portfolio.json")

    def tearDown(self):
        shutil.rmtree(self.d)

    def args(self, *extra):
        return list(extra) + ["--orders", self.orders, "--config", self.cfg, "--risk", self.risk,
                              "--state", self.state, "--portfolio", self.portfolio,
                              "--cache", FIXTURE_CSV, "--now", NOW]

    def test_place_refuses_without_approval(self):
        code, out, err = run_cli(self.args("place", "--index", "1"))
        self.assertEqual(code, 1)
        self.assertIn("not approved", err)

    def test_place_refuses_when_broker_is_not_megabull(self):
        with open(self.cfg) as fh:
            cfg = json.load(fh)
        cfg["broker"] = "groww"
        with open(self.cfg, "w") as fh:
            json.dump(cfg, fh)
        code, out, err = run_cli(self.args("place", "--index", "1"))
        self.assertEqual(code, 1)
        self.assertIn("not \"megabull\"", err)


if __name__ == "__main__":
    unittest.main()
