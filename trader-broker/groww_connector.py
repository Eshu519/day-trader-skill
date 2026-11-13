#!/usr/bin/env python3
"""Groww broker connector using growwapi SDK.
Uses environment variables: GROWW_API_KEY, GROWW_SECRET_KEY, GROWW_API_TOKEN, GROWW_TOTP."""
import os
import json
import math
from growwapi import GrowwAPI

# Load credentials from environment
GROWW_API_KEY = os.getenv("GROWW_API_KEY")
GROWW_SECRET_KEY = os.getenv("GROWW_SECRET_KEY")
GROWW_API_TOKEN = os.getenv("GROWW_API_TOKEN")
GROWW_TOTP = os.getenv("GROWW_TOTP")

# Initialize Groww API client
groww = None
_token = None

def _get_token():
    """Get or refresh access token."""
    global _token, groww
    
    if GROWW_API_TOKEN:
        _token = GROWW_API_TOKEN
    elif GROWW_API_KEY and GROWW_SECRET_KEY:
        # Use API key + secret (requires daily approval on Groww Cloud)
        result = GrowwAPI.get_access_token(api_key=GROWW_API_KEY, secret=GROWW_SECRET_KEY)
        _token = result
    elif GROWW_API_KEY and GROWW_TOTP:
        # Use API key + TOTP (no expiry)
        result = GrowwAPI.get_access_token(api_key=GROWW_API_KEY, totp=GROWW_TOTP)
        _token = result
    else:
        raise ValueError(
            "Groww credentials not found. Set one of:\n"
            "  - GROWW_API_TOKEN (pre-generated token)\n"
            "  - GROWW_API_KEY + GROWW_SECRET_KEY (daily approval needed)\n"
            "  - GROWW_API_KEY + GROWW_TOTP (no expiry)"
        )
    
    groww = GrowwAPI(_token)
    return _token

# Initialize on import
try:
    _get_token()
except Exception as e:
    print(f"Warning: Groww client not initialized: {e}")

# Constants from growwapi
EXCHANGE_NSE = GrowwAPI.EXCHANGE_NSE
SEGMENT_CASH = GrowwAPI.SEGMENT_CASH
PRODUCT_CNC = GrowwAPI.PRODUCT_CNC
ORDER_TYPE_LIMIT = GrowwAPI.ORDER_TYPE_LIMIT
ORDER_TYPE_MARKET = GrowwAPI.ORDER_TYPE_MARKET
TRANSACTION_TYPE_BUY = GrowwAPI.TRANSACTION_TYPE_BUY
TRANSACTION_TYPE_SELL = GrowwAPI.TRANSACTION_TYPE_SELL
VALIDITY_DAY = GrowwAPI.VALIDITY_DAY

def place_order(ticket_json):
    """Place order via Groww API from trader-broker ticket format.
    
    ticket_json should contain:
    - symbol: e.g. "HDFCBANK.NS" (will be converted to "HDFCBANK")
    - qty: integer quantity
    - side: "BUY" or "SELL"
    - order_type: "LIMIT" or "MARKET"
    - price: float (required for LIMIT orders)
    - product: "CNC" (delivery) or "MIS" (intraday)
    - trigger_price: float (optional, for stop-loss orders)
    """
    global groww
    if not groww:
        _get_token()
    
    # Convert symbol from Yahoo format (HDFCBANK.NS) to Groww format (HDFCBANK)
    symbol = ticket_json.get("symbol", "").replace(".NS", "")
    qty = int(ticket_json.get("qty", 0))
    side = ticket_json.get("side", "BUY").upper()
    order_type = ticket_json.get("order_type", "LIMIT").upper()
    price = float(ticket_json.get("price", 0))
    product = ticket_json.get("product", "CNC").upper()
    trigger_price = ticket_json.get("trigger_price")
    
    if qty <= 0:
        raise ValueError("Quantity must be positive")
    
    # Map side
    transaction_type = TRANSACTION_TYPE_BUY if side == "BUY" else TRANSACTION_TYPE_SELL
    
    # Map order type
    if order_type == "MARKET":
        ot = ORDER_TYPE_MARKET
        price = 0.0  # Market orders ignore price
    else:
        ot = ORDER_TYPE_LIMIT
        if price <= 0:
            raise ValueError("Price required for LIMIT orders")
    
    # Map product
    product_map = {
        "CNC": PRODUCT_CNC,
        "MIS": GrowwAPI.PRODUCT_MIS,
        "NRML": GrowwAPI.PRODUCT_NRML,
    }
    prod = product_map.get(product, PRODUCT_CNC)
    
    # Place order
    response = groww.place_order(
        trading_symbol=symbol,
        quantity=qty,
        validity=VALIDITY_DAY,
        exchange=EXCHANGE_NSE,
        segment=SEGMENT_CASH,
        product=prod,
        order_type=ot,
        transaction_type=transaction_type,
        price=price,
        trigger_price=trigger_price,
    )
    
    return response

def get_order_status(order_id):
    """Get order status by order ID."""
    global groww
    if not groww:
        _get_token()
    return groww.get_order_status(order_id)

def get_orders():
    """Get cash-segment orders for checking pending orders."""
    global groww
    if not groww:
        _get_token()
    return groww.get_order_list(segment=SEGMENT_CASH)

def get_ltp(symbol):
    """Fetch and validate the current NSE cash-segment last traded price."""
    global groww
    if not groww:
        _get_token()
    symbol = str(symbol or "").strip().upper()
    if symbol.endswith((".BSE", ".BO")):
        raise ValueError("Groww LTP lookup supports NSE symbols only: %s" % symbol)
    for suffix in (".NSE", ".NS"):
        if symbol.endswith(suffix):
            symbol = symbol[:-len(suffix)]
            break
    quote = groww.get_quote(exchange=EXCHANGE_NSE, segment=SEGMENT_CASH, trading_symbol=symbol)
    try:
        price = float(quote["last_price"])
    except (TypeError, KeyError, ValueError):
        raise ValueError("Groww quote response has no valid last_price: %r" % (quote,))
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Groww returned an invalid last_price: %r" % (quote,))
    return price

def get_positions():
    """Get current positions."""
    global groww
    if not groww:
        _get_token()
    return groww.get_positions_for_user()

def get_holdings():
    """Get holdings."""
    global groww
    if not groww:
        _get_token()
    return groww.get_holdings_for_user()

def refresh_token():
    """Force token refresh."""
    global groww
    groww = None
    return _get_token()