---
name: trader-megabull
description: >-
  MegaBull paper trading connector. Places the orders trader-broker has already
  recorded your yes for, on MegaBull's free paper trading API (virtual money,
  NSE/BSE equities, MIS intraday or CNC delivery), and reads back your virtual
  balance, positions, holdings, orders and P&L reports. Use it to rehearse the
  whole day-trader flow on paper before switching trader/config.json back to
  groww or alpaca. Never places an order without trader-risk PASS and your
  explicit yes recorded by ticket.py. Use when the user says "paper trade on
  megabull", "switch to megabull", "try it on paper first", "megabull balance",
  "megabull positions", "place it on megabull", or after /trader-broker records
  a yes and the config broker is megabull.
argument-hint: "[place --index N | balance | positions | orders]"
---

# trader-megabull

MegaBull (https://megabull.in) is a free paper trading platform for India:
Rs5,00,000 of virtual money, live NSE/BSE prices, no real money at risk. This
skill is the extension that lets the whole day-trader pack run against it, so
you can rehearse every feature and signal on paper and switch to Groww when
you trust the results.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/megabull.py" balance                 # virtual money; writes trader/portfolio.json
python3 "${CLAUDE_SKILL_DIR}/megabull.py" instruments --refresh   # re-download the instrument token list
python3 "${CLAUDE_SKILL_DIR}/megabull.py" token HDFCBANK.NS       # symbol -> instrumentToken
python3 "${CLAUDE_SKILL_DIR}/megabull.py" ltp HDFCBANK.NS         # last traded price
python3 "${CLAUDE_SKILL_DIR}/megabull.py" place --index 1         # place an APPROVED order
python3 "${CLAUDE_SKILL_DIR}/megabull.py" orders                  # today's open and executed orders
python3 "${CLAUDE_SKILL_DIR}/megabull.py" positions               # open positions
python3 "${CLAUDE_SKILL_DIR}/megabull.py" holdings                # delivery holdings
python3 "${CLAUDE_SKILL_DIR}/megabull.py" cancel --ids 101,102    # cancel pending orders
python3 "${CLAUDE_SKILL_DIR}/megabull.py" report --month 11 --year 2026
```

`megabull.py` never decides anything. It checks that trader-broker recorded
your yes for that exact order today before it sends anything, and it records
the outcome back with `ticket.py result`.

## Setup

1. Sign up free at https://trade.megabull.in/signup. You get Rs5,00,000 of
   virtual money.
2. Log in, open **Profile**, and generate an **API key**. Keys expire after
   1 month; regenerate anytime.
3. Put the key in the environment, never in the chat and never in a file in
   this repo:

   ```powershell
   $env:MEGABULL_API_KEY = "paste your key here, in this shell only"
   ```

   or set it as a user environment variable. If the user pastes a key into the
   chat anyway, tell them to delete that message and generate a new key.
4. Switch the pack to MegaBull in `trader/config.json`:

   ```json
   "broker": "megabull",
   "paper": true,
   "megabull": { "product": "MIS", "instruments_cache_days": 7 }
   ```

   `product` is `MIS` (intraday, auto squared off at 3:40 PM IST) or `CNC`
   (delivery). `instruments_cache_days` controls how often the instrument
   token list is re-downloaded.
5. Check it: `python3 "${CLAUDE_SKILL_DIR}/megabull.py" balance`. It should
   print your virtual money and write `trader/portfolio.json`.

## Switching back and forth

Only `trader/config.json` changes. Everything else (scanner, news, entry,
exit, timemachine, budget, risk, broker, alerts) reads the same files and
does not care which broker is set.

| to | set |
| --- | --- |
| MegaBull paper | `"broker": "megabull"` |
| Groww | `"broker": "groww"` |
| Alpaca paper | `"broker": "alpaca"` |
| Interactive Brokers | `"broker": "ibkr"` |

Switching does not move money or positions; it only changes where the next
order goes and how `ticket.py` renders it. Keep `"paper": true` until you are
deliberately going live, and going live is the user's own decision.

## The flow, end to end

1. `/trader-scanner`, `/trader-news`, `/trader-entry`, `/trader-exit`,
   `/trader-timemachine` as usual.
2. `/trader-budget` writes the order to `trader/orders.json`.
3. `/trader-risk` checks it. Only a PASS from today makes it READY.
4. `/trader-broker` shows the ticket. With `"broker": "megabull"` it prints
   the MegaBull payload instead of Alpaca's `place_stock_order` JSON. You type
   yes for that one order; `ticket.py approve` records it.
5. `python3 "${CLAUDE_SKILL_DIR}/megabull.py" place --index 1` re-checks that
   approval, resolves the symbol to an instrumentToken (downloading and
   caching the list at `trader/state/megabull-instruments.csv` if needed),
   sends the order, and records the result with `ticket.py result`.
6. `/trader-alerts` watches the stop and the target. MegaBull has **no
   bracket orders**, so the stop-loss and take-profit are never at the
   broker; the alerts are the only thing watching them.
7. By `flat_by`, close anything open: `ticket.py flatten --symbol X --qty N`,
   then `/trader-risk`, then your yes, then `megabull.py place --index 1`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/config.json` | `"broker": "megabull"`, optional `"megabull": {...}` |
| `trader/orders.json` | the proposed orders (trader-budget writes it) |
| `trader/state/risk.json` | trader-risk's verdicts; `place` refuses without a PASS today |
| `trader/state/broker.json` | your yes, and the placed/failed result |
| `trader/state/megabull-instruments.csv` | cached instrument token list |
| `trader/portfolio.json` | cash = `virtualMoneyLeft`, written by `balance` |

## MegaBull API notes (checked 2026-11-12, https://api.megabull.in/api-docs)

- Auth: `api-key` header. Base URL `https://api.megabull.in`.
- Orders: `POST /api/order/buysell` with `instrumentToken`, `qty`, `type`
  (`BUY`/`SELL`), `duration` (`MIS`/`CNC`), `orderType` (`LIMIT`, `MKT`, `SL`),
  `price` for LIMIT, `triggerPrice` for SL.
- MegaBull's published schema says MKT does not need `price`, but the live API
  has returned `Price cannot be Blank` for an MKT order without it. To handle
  that response, the connector fetches the instrument's current LTP and includes
  it as `price` while retaining `orderType: MKT`. If the LTP cannot be fetched,
  the connector refuses to submit the order.
- Fills are all-or-nothing. `status` is `PENDING`, `COMPLETE` or `CANCELLED`.
- MIS positions are squared off automatically at 3:40 PM IST.
- No bracket/OCO orders. Stop-loss and take-profit are not supported as
  attached legs; use `/trader-alerts`.
- Instruments are numeric tokens from `GET /api/marketwatch/instruments`
  (a CSV on S3). The cache is refreshed when older than
  `instruments_cache_days` or with `--refresh`.
- `GET /api/order/my` returns today's orders split into `open` and `executed`;
  there is no single-order GET, so `order_status_by_id` scans both.
- Quantity must be a whole number and a multiple of the instrument's lot size
  (1 for equities).
- Keys expire after 1 month. A 401 means regenerate the key.

## What it never does

- Never places an order without all three gates: trader-risk PASS today, your
  explicit yes recorded by `ticket.py approve`, and the `place` command run by
  you or by Claude in this session.
- Never places orders from a scheduled or background task: nobody is there to
  say yes.
- Never asks for, reads, stores or repeats the API key.
- Never switches `"broker"` or `"paper"` for you. The user does that.
- Never promises a fill price: market orders fill at whatever the market gives.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a
  recommendation.
- Paper trading only. MegaBull has no live mode; going live means switching
  `"broker"` to groww or alpaca yourself, in your own config.
- Nothing in this pack places an order except trader-broker, and only when all
  three hold: trader-risk passed that exact order today, the user typed an
  explicit yes for that one order in the chat, and the order tool is set to
  "Needs approval" where the broker has one.
- No options, margin, short selling or leverage unless the config allows it
  and the user confirms.
- The API key lives in the environment, never in the chat, never in this repo.
