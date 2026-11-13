import unittest
import json
import os
import sys
import tempfile
import types
from unittest.mock import patch

from _load import load

auto_loop = load("", "auto_signal_loop")


class ActiveOrderGuard(unittest.TestCase):
    def test_megabull_pending_order_blocks_same_symbol(self):
        connector = type("Connector", (), {
            "resolve_token": lambda self, symbol: "123",
            "get_orders": lambda self: {"open": [{"instrumentName": "IDEA", "status": "PENDING"}],
                                        "executed": []},
            "get_positions": lambda self: [],
            "get_holdings": lambda self: [],
        })()
        with patch.object(auto_loop, "load_connector", return_value=connector):
            active, reason = auto_loop.has_in_progress_order("IDEA.NS", "megabull")
        self.assertTrue(active)
        self.assertEqual(reason, "an active broker order")

    def test_groww_open_position_blocks_same_symbol(self):
        connector = type("Connector", (), {
            "get_orders": lambda self: {"order_list": []},
            "get_positions": lambda self: {"positions": [{"trading_symbol": "IDEA", "quantity": 9999}]},
            "get_holdings": lambda self: {"holdings": []},
        })()
        with patch.object(auto_loop, "load_connector", return_value=connector):
            active, reason = auto_loop.has_in_progress_order("IDEA.NS", "groww")
        self.assertTrue(active)
        self.assertEqual(reason, "an open broker position")

    def test_refresh_signal_price_returns_and_records_broker_quote(self):
        with patch.object(auto_loop, "get_broker_ltp", return_value=12.55), \
             patch.object(auto_loop, "record_broker_ltp") as record:
            price = auto_loop.refresh_signal_price("IDEA.NS", "megabull")
        self.assertEqual(price, 12.55)
        record.assert_called_once_with("IDEA.NS", 12.55, "megabull")

    def test_broker_price_update_preserves_other_prices_and_their_age(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "prices.json")
            original = {
                "as_of": "2026-11-05T10:00:00Z",
                "prices": {"RELIANCE.NS": 1500.0},
                "detail": {"RELIANCE.NS": {"time": "2026-11-05T10:00:00Z"}},
            }
            with open(path, "w") as f:
                json.dump(original, f)

            auto_loop.record_broker_ltp("IDEA.NS", 12.55, "megabull", path)

            with open(path, "r") as f:
                updated = json.load(f)
            self.assertEqual(updated["prices"]["RELIANCE.NS"], 1500.0)
            self.assertEqual(updated["as_of"], original["as_of"])
            self.assertEqual(updated["prices"]["IDEA.NS"], 12.55)
            self.assertEqual(updated["detail"]["IDEA.NS"]["source"], "megabull")
            self.assertTrue(updated["detail"]["IDEA.NS"]["time"].endswith("Z"))

    def test_invalid_live_price_is_refused(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "prices.json")
            with self.assertRaisesRegex(ValueError, "invalid LTP"):
                auto_loop.record_broker_ltp("IDEA.NS", 0, "megabull", path)
            self.assertFalse(os.path.exists(path))

    def test_groww_ltp_uses_quote_last_price_and_exchange_symbol(self):
        class FakeGrowwAPI:
            EXCHANGE_NSE = "NSE"
            SEGMENT_CASH = "CASH"
            PRODUCT_CNC = "CNC"
            ORDER_TYPE_LIMIT = "LIMIT"
            ORDER_TYPE_MARKET = "MARKET"
            TRANSACTION_TYPE_BUY = "BUY"
            TRANSACTION_TYPE_SELL = "SELL"
            VALIDITY_DAY = "DAY"
            PRODUCT_MIS = "MIS"
            PRODUCT_NRML = "NRML"

        sdk = types.ModuleType("growwapi")
        sdk.GrowwAPI = FakeGrowwAPI

        class FakeClient:
            def get_quote(self, **kwargs):
                self.request = kwargs
                return {"last_price": 12.55}

        fake_client = FakeClient()
        empty_credentials = {
            "GROWW_API_KEY": "",
            "GROWW_SECRET_KEY": "",
            "GROWW_API_TOKEN": "",
            "GROWW_TOTP": "",
        }
        with patch.dict(os.environ, empty_credentials), patch.dict(sys.modules, {"growwapi": sdk}):
            connector = load("trader-broker", "groww_connector")
            connector.groww = fake_client
            price = connector.get_ltp("IDEA.NS")

        self.assertEqual(price, 12.55)
        self.assertEqual(fake_client.request, {
            "exchange": "NSE", "segment": "CASH", "trading_symbol": "IDEA"
        })

    def test_different_instrument_is_not_blocked(self):
        connector = type("Connector", (), {
            "resolve_token": lambda self, symbol: "123",
            "get_orders": lambda self: {"open": [{"instrumentName": "IDEA", "status": "PENDING"}]},
            "get_positions": lambda self: [],
            "get_holdings": lambda self: [],
        })()
        with patch.object(auto_loop, "load_connector", return_value=connector):
            active, reason = auto_loop.has_in_progress_order("RELIANCE.NS", "megabull")
        self.assertFalse(active)
        self.assertEqual(reason, "")

    def test_broker_check_errors_propagate(self):
        connector = type("Connector", (), {
            "resolve_token": lambda self, symbol: "123",
            "get_orders": lambda self: (_ for _ in ()).throw(RuntimeError("API unavailable")),
        })()
        with patch.object(auto_loop, "load_connector", return_value=connector):
            with self.assertRaisesRegex(RuntimeError, "API unavailable"):
                auto_loop.has_in_progress_order("IDEA.NS", "megabull")

    def test_megabull_matches_positions_by_instrument_token(self):
        connector = type("Connector", (), {
            "resolve_token": lambda self, symbol: "123",
            "get_orders": lambda self: {"open": [], "executed": []},
            "get_positions": lambda self: [{"instrumentToken": "123", "qty": 9999}],
            "get_holdings": lambda self: [],
        })()
        with patch.object(auto_loop, "load_connector", return_value=connector):
            active, reason = auto_loop.has_in_progress_order("IDEA.NS", "megabull")
        self.assertTrue(active)
        self.assertEqual(reason, "an open broker position")


if __name__ == "__main__":
    unittest.main()
