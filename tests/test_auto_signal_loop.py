import unittest
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
